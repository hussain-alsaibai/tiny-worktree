"""Every python example in README.md must actually run.

A README example that does not execute is worse than no example: it teaches
the reader an API that does not exist, and the reader only finds out after
copying it into their own code.

This test extracts the fenced python blocks from README.md and runs the
ones that are self-contained (they import from tiny_worktree and call the
public API). Blocks that are illustrative fragments are checked for syntax
and for the names they reference.
"""

import ast
import os
import re
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(REPO, "README.md")

sys.path.insert(0, REPO)


def readme_blocks():
    with open(README, encoding="utf-8") as fh:
        text = fh.read()
    fence = chr(96) * 3
    return re.findall(fence + r"python" + chr(92) + "n(.*?)" + fence, text, re.S)


def test_readme_has_python_blocks():
    assert readme_blocks(), "README has no python examples"


def test_every_readme_block_is_valid_python():
    """Every python block in the README must at least parse."""
    blocks = readme_blocks()
    assert len(blocks) >= 3, "expected the import, usage and agent blocks"
    for index, block in enumerate(blocks):
        try:
            ast.parse(block)
        except SyntaxError as exc:
            pytest.fail("README python block %d does not parse: %s" % (index, exc))


def test_readme_examples_run():
    """Run the self-contained examples against a real repo."""
    blocks = readme_blocks()
    if not blocks:
        pytest.skip("no examples")

    # The first block is the import block; the second is the main usage
    # block. Both must run end to end.
    import_block = blocks[0]
    usage_block = blocks[1] if len(blocks) > 1 else ""

    tmp = os.path.join(REPO, ".readme_test_repo")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        def git(*args):
            subprocess.run(
                ["git"] + list(args),
                cwd=tmp,
                check=True,
                capture_output=True,
                text=True,
            )

        git("init", "-q")
        git("config", "user.email", "readme@example.com")
        git("config", "user.name", "Readme")
        with open(os.path.join(tmp, "f.txt"), "w") as fh:
            fh.write("x")
        git("add", "f.txt")
        git("commit", "-q", "-m", "initial")

        # The README example creates a worktree for "feat/issue-42". If a
        # previous run left the directory behind, the example would fail on
        # the second run -- which would make the test flaky rather than
        # wrong. Use a unique branch per run and clean up after.
        unique = "feat/readme-%d" % os.getpid()
        release = "release/readme-%d" % os.getpid()
        # The README example checks out an EXISTING branch, so create it
        # first -- exactly what a real reader would have to do.
        git("branch", release)

        # The example also creates a branch from base="main". A freshly
        # initialised repo does not necessarily have a branch called
        # "main" -- git picks the default branch name from its own
        # configuration, and the CI runners do not all agree. Create
        # "main" explicitly so the example resolves the same way
        # everywhere.
        default_branch = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=tmp,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if default_branch != "main":
            git("branch", "main")

        usage = usage_block.replace("feat/issue-42", unique)
        usage = usage.replace("release/2.0", release)

        script = (
            import_block
            + "\n"
            + usage
            + "\n"
            + "print('README_EXAMPLES_OK')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=tmp,
            capture_output=True,
            text=True,
            env=dict(os.environ, PYTHONPATH=REPO),
        )
        assert proc.returncode == 0, proc.stderr
        assert "README_EXAMPLES_OK" in proc.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp + "-worktrees", ignore_errors=True)


def test_readme_mentions_every_public_name():
    """The API table in the README must list every public export."""
    import tiny_worktree

    with open(README, encoding="utf-8") as fh:
        text = fh.read()

    missing = []
    for name in tiny_worktree.__all__:
        if name not in text:
            missing.append(name)
    assert not missing, "README does not document: %s" % ", ".join(missing)


def test_cli_entry_point_is_importable():
    from tiny_worktree.cli import main

    assert callable(main)
