"""Compile-only validation of the sample ESPHome YAML.

We only check that ``esphome config`` accepts the file - no flashing, no
network calls. If the ``esphome`` CLI is not installed, the test is skipped
with a helpful message; install with ``make venv`` to enable it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CONFIG = REPO_ROOT / "esphome" / "sampleconfig.yaml"


@pytest.fixture(scope="module")
def esphome_cli() -> str:
    cli = shutil.which("esphome")
    if cli is None:
        pytest.skip(
            "esphome CLI not installed - run 'make venv' to enable this test"
        )
    return cli


def test_sample_config_exists():
    assert SAMPLE_CONFIG.exists(), f"missing {SAMPLE_CONFIG}"


def test_sample_config_validates(esphome_cli):
    """``esphome config`` must accept the sample YAML."""
    result = subprocess.run(
        [esphome_cli, "config", str(SAMPLE_CONFIG)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"esphome config failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
