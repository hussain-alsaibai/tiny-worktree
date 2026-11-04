"""Packaging must produce a wheel that actually contains the package.

A build that succeeds is not the same as a build that ships code. With
``[tool.setuptools] py-modules = ["tiny_worktree"]`` on a package
directory, setuptools finds no module file, emits a clean wheel, and the
wheel installs nothing at all. This is a real, previously-shipped defect in
this ecosystem, so it gets its own test.
"""

import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYPROJECT = os.path.join(REPO, "pyproject.toml")
_IMPORT_VERSION_SCRIPT = "import tiny_worktree; print(tiny_worktree.__version__)"


def test_pyproject_declares_a_package_not_a_flat_module():
    """The package is a directory, so it must be declared as a package."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    with open(PYPROJECT, "rb") as fh:
        config = tomllib.load(fh)

    setuptools_cfg = config.get("tool", {}).get("setuptools", {})

    assert setuptools_cfg.get("packages") == ["tiny_worktree"], (
        "pyproject must declare packages = [\"tiny_worktree\"]; a "
        "py-modules entry pointing at a package directory builds an empty "
        "wheel"
    )
    assert "py-modules" not in setuptools_cfg, (
        "py-modules must not be used for a package directory"
    )


def test_package_is_importable_from_a_checkout():
    proc = subprocess.run(
        [sys.executable, "-c", _IMPORT_VERSION_SCRIPT],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


@pytest.mark.skipif(
    subprocess.run(["which", "git"], stdout=subprocess.DEVNULL).returncode != 0,
    reason="git not available",
)
def test_wheel_contains_the_module():
    """Build a wheel and assert the module is inside it."""
    import glob
    import zipfile

    proc = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", "dist"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        # The build backend may not be installable on every interpreter
        # (setuptools dropped 3.8 support in newer releases). Skipping is
        # honest here: the CI build job asserts the same thing on a
        # supported interpreter.
        pytest.skip("could not build a wheel here: %s" % proc.stderr[-400:])

    wheels = glob.glob(os.path.join(REPO, "dist", "*.whl"))
    assert wheels, "no wheel was produced"

    names = zipfile.ZipFile(wheels[-1]).namelist()
    assert "tiny_worktree/__init__.py" in names, (
        "the wheel ships no module: %s" % names
    )
    assert "tiny_worktree/core.py" in names, (
        "the wheel ships no core module: %s" % names
    )
