"""Registry of official GATE documents used by the pipeline.

Every file comes from a GATE organising-institute website. The first URL is the
organiser of that year's exam; later URLs are official mirrors kept by later
organisers. `fetch` downloads all of them and refuses to continue if the copies
differ, so the dataset never depends on a single unverified download.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    """One official document and the URLs it can be fetched from."""

    filename: str
    kind: str  # paper | key | syllabus
    year: int
    subject: str  # DA | GA
    urls: tuple[str, ...]
    note: str = ""


IISC_2024 = "https://gate2024.iisc.ac.in/wp-content/uploads"
IITR_2025 = "https://gate2025.iitr.ac.in/doc"
IITG_2026 = "https://gate2026.iitg.ac.in/doc"
IITM_2027 = "https://gate2027.iitm.ac.in/static/doc"

SOURCES: tuple[Source, ...] = (
    # ---- Question papers (master papers, the order used by the answer keys) ----
    Source(
        "2024_DA_paper.pdf", "paper", 2024, "DA",
        (
            f"{IISC_2024}/2024/DA24S1.pdf",
            f"{IITR_2025}/download/2024/DA24S1.pdf",
            f"{IITG_2026}/download/2024/DA24S1.pdf",
            f"{IITM_2027}/download/2024/DA24S1.pdf",
        ),
    ),
    Source(
        "2025_DA_paper.pdf", "paper", 2025, "DA",
        (
            f"{IITR_2025}/2025/2025_QP/DA.pdf",
            f"{IITG_2026}/download/2025/DA2025.pdf",
            f"{IITM_2027}/download/2025/DA2025.pdf",
        ),
    ),
    Source(
        "2026_DA_paper.pdf", "paper", 2026, "DA",
        (
            f"{IITG_2026}/download/2026/QPs/DA.pdf",
            f"{IITM_2027}/download/2026/QPs/DA.pdf",
        ),
    ),
    # ---- Answer keys ----
    Source(
        "2024_DA_key.pdf", "key", 2024, "DA",
        (
            f"{IISC_2024}/2024/DAFinalAnswerKey.pdf",
            f"{IITR_2025}/download/2024/DAFinalAnswerKey.pdf",
            f"{IITG_2026}/download/2024/DAFinalAnswerKey.pdf",
            f"{IITM_2027}/download/2024/DAFinalAnswerKey.pdf",
        ),
        note="Final answer key (released 2024-03-14).",
    ),
    Source(
        "2025_DA_key.pdf", "key", 2025, "DA",
        (
            f"{IITR_2025}/2025/2025_Key/DA_Keys.pdf",
            f"{IITG_2026}/download/2025_Key/DA_Keys.pdf",
            f"{IITM_2027}/download/2025_Key/DA_Keys.pdf",
        ),
    ),
    Source(
        "2026_DA_key.pdf", "key", 2026, "DA",
        (
            f"{IITG_2026}/download/2026/Keys/DA_Keys.pdf",
            f"{IITM_2027}/download/2026/Keys/DA_Keys.pdf",
        ),
    ),
    # ---- Syllabi ----
    Source(
        "2024_DA_syllabus.pdf", "syllabus", 2024, "DA",
        (f"{IISC_2024}/2023/08/GATE2024DataScienceAIsyllabus.pdf",),
    ),
    Source(
        "2025_DA_syllabus.pdf", "syllabus", 2025, "DA",
        (f"{IITR_2025}/2025/GATE%20_DA_2025_Syllabus.pdf",),
    ),
    Source(
        "2026_DA_syllabus.pdf", "syllabus", 2026, "DA",
        (f"{IITG_2026}/GATE2026_Syllabus/DA_2026_Syllabus.pdf",),
    ),
    Source(
        "2027_DA_syllabus.pdf", "syllabus", 2027, "DA",
        (f"{IITM_2027}/GATE2027_Syllabus/DA_GATE2027_Syllabus.pdf",),
    ),
    Source(
        "2024_GA_syllabus.pdf", "syllabus", 2024, "GA",
        (f"{IISC_2024}/2023/08/GA2024Syllabus.pdf",),
    ),
    Source(
        "2025_GA_syllabus.pdf", "syllabus", 2025, "GA",
        (f"{IITR_2025}/2024/GATE%20_GA_2025_Syllabus.pdf",),
    ),
    Source(
        "2026_GA_syllabus.pdf", "syllabus", 2026, "GA",
        (f"{IITG_2026}/GATE2026_Syllabus/GA_2026_Syllabus.pdf",),
    ),
    Source(
        "2027_GA_syllabus.pdf", "syllabus", 2027, "GA",
        (f"{IITM_2027}/GATE2027_Syllabus/GA_GATE2027_Syllabus.pdf",),
    ),
)


def get_source(kind: str, year: int, subject: str = "DA") -> Source:
    """Return the registered source for a document kind, year and subject."""
    for source in SOURCES:
        if (source.kind, source.year, source.subject) == (kind, year, subject):
            return source
    raise KeyError(f"No source registered for {kind=} {year=} {subject=}")
