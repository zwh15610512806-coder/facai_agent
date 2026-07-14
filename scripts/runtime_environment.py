"""Load project-local runtime configuration before startup policy checks."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_project_environment(project_root: Path) -> None:
    """Load ``.env`` without overriding explicit service-level environment."""

    load_dotenv(project_root / ".env", override=False)
