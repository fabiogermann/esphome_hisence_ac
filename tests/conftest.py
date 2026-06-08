"""Shared pytest fixtures for the Hisense protocol test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


DATA_DIR = Path(__file__).parent / "data"
FRAMES_FILE = DATA_DIR / "frames.json"


@pytest.fixture(scope="session")
def frames_data() -> dict:
    """Load the captured-frames fixture once per test session."""
    with FRAMES_FILE.open() as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def frames(frames_data) -> list[dict]:
    """All captured frames, in declaration order."""
    return frames_data["frames"]


@pytest.fixture(scope="session")
def well_formed_frames(frames) -> list[dict]:
    """Frames that have a known-good checksum (excludes truncated/bug cases)."""
    return [f for f in frames if f.get("expected_checksum") is not None]
