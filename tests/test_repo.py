"""Checks of the repo itself: the licence, and the files that git must not take."""

import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_typokiller_and_keybr_are_both_under_the_agpl():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    keybr_package = json.loads((ROOT / "keybr" / "package.json").read_text())
    assert pyproject["project"]["license"] == keybr_package["license"] == "AGPL-3.0-or-later"
    for licence in (ROOT / "LICENSE", ROOT / "keybr" / "LICENSE"):
        assert licence.read_text().lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")


def test_git_ignores_keybr_installs_and_builds_macos_folder_settings_and_output():
    paths = ["keybr/node_modules/x", "keybr/root/public/assets/x", "keybr/root/lib/x"]
    paths += ["assets/.DS_Store", "output/x"]
    # Without the user's own ignore file, so that only the repo's rules count.
    git = ["git", "-c", "core.excludesFile=/dev/null", "check-ignore", *paths]
    ignored = subprocess.run(git, cwd=ROOT, capture_output=True, text=True)
    assert ignored.stdout.split() == paths
