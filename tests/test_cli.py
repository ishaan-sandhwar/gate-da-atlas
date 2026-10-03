"""The CLI's light commands must work with only the core and analysis dependencies installed."""

import subprocess
import sys

# Run in a fresh interpreter with the ML and LLM packages blocked, as on the CI runner that
# builds the web atlas (pip install -e ".[analysis]").
SCRIPT = """
import sys

class BlockHeavyPackages:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"sklearn", "sentence_transformers", "torch", "groq", "dotenv"}:
            raise ImportError(f"blocked {name}")
        return None

sys.meta_path.insert(0, BlockHeavyPackages())

import gate_atlas.__main__ as cli
import gate_atlas.analysis.run
import gate_atlas.planner.render
import gate_atlas.validate
import gate_atlas.web_export

for command in ("build", "analyze", "plan", "export-web"):
    try:
        cli.main([command, "--help"])
    except SystemExit as stop:
        assert stop.code == 0, (command, stop.code)
"""


def test_light_commands_do_not_need_ml_or_llm_packages() -> None:
    """build, analyze, plan and export-web parse and import without scikit-learn, torch or Groq."""
    result = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
