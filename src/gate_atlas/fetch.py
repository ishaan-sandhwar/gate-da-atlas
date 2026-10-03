"""Download official PDFs into data/raw and record their provenance."""

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from gate_atlas.config import MANIFEST_PATH, RAW_DIR
from gate_atlas.sources import SOURCES, Source

log = logging.getLogger(__name__)

USER_AGENT = "gate-da-atlas/0.1 (+research dataset; contact repo owner)"
TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2.0
PDF_MAGIC = b"%PDF"


class MirrorMismatchError(RuntimeError):
    """Raised when official mirrors serve different bytes for one document."""


def sha256_hex(payload: bytes) -> str:
    """Return the SHA-256 hex digest of a byte string."""
    return hashlib.sha256(payload).hexdigest()


def download(url: str) -> bytes:
    """Download a URL with retries and return the body."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            log.warning("attempt %d/%d failed for %s: %s", attempt, MAX_ATTEMPTS, url, error)
            time.sleep(RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError(f"Could not download {url}") from last_error


def fetch_source(source: Source) -> dict:
    """Fetch every URL of one source, check they agree, and save the file."""
    checks = []
    payload: bytes | None = None
    for url in source.urls:
        try:
            body = download(url)
        except RuntimeError as error:
            checks.append({"url": url, "ok": False, "error": str(error.__cause__ or error)})
            continue
        if not body.startswith(PDF_MAGIC):
            checks.append({"url": url, "ok": False, "error": "response is not a PDF"})
            continue
        checks.append({"url": url, "ok": True, "sha256": sha256_hex(body), "bytes": len(body)})
        payload = payload or body

    good = [check for check in checks if check["ok"]]
    if payload is None:
        raise RuntimeError(f"No official URL served {source.filename}: {checks}")
    if len({check["sha256"] for check in good}) > 1:
        raise MirrorMismatchError(f"Official copies of {source.filename} differ: {good}")

    target = RAW_DIR / source.filename
    target.write_bytes(payload)
    log.info("saved %s (%d bytes, %d/%d URLs agree)", target.name, len(payload), len(good), len(checks))
    return {
        "filename": source.filename,
        "kind": source.kind,
        "year": source.year,
        "subject": source.subject,
        "sha256": good[0]["sha256"],
        "bytes": len(payload),
        "primary_url": source.urls[0],
        "url_checks": checks,
        "note": source.note,
    }


def fetch_all() -> list[dict]:
    """Fetch every registered source and write data/raw/MANIFEST.json."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    entries = [fetch_source(source) for source in SOURCES]
    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": entries,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log.info("wrote %s with %d documents", MANIFEST_PATH.name, len(entries))
    return entries


def verify_raw_files() -> list[str]:
    """Return a list of problems where files in data/raw differ from the manifest."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    problems = []
    for entry in manifest["documents"]:
        path = RAW_DIR / entry["filename"]
        if not path.exists():
            problems.append(f"missing {entry['filename']}")
        elif sha256_hex(path.read_bytes()) != entry["sha256"]:
            problems.append(f"checksum mismatch {entry['filename']}")
    return problems
