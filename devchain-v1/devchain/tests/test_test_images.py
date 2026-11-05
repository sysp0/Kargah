"""Test entry points must refresh dependency images before running containers."""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("target", ["test-db", "test", "test-fast", "test-unit", "test-dev", "demo-test"])
def test_test_targets_build_images_before_running_containers(target):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["make", "-n", "-C", str(root / "project-a"), target],
        capture_output=True, text=True, check=True,
    )
    commands = result.stdout.splitlines()
    for image in (["app", "api"] if target == "demo-test" else ["app"]):
        runs = [i for i, line in enumerate(commands) if " run " in line and f" {image} " in line]
        builds = [i for i, line in enumerate(commands) if " build " in line and image in line.split()]
        assert runs, f"{target} must exercise {image}"
        assert builds and min(builds) < min(runs), f"{target} runs a potentially stale {image} image"
