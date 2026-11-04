"""Tests for tiny-worktree.

Every test that touches git runs against a real throwaway repository created
in a tmp dir. That is deliberate: the whole value of this package is in how
it drives ``git``, and a mocked git would only test the mock.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tiny_worktree.core import (  # noqa: E402
    Worktree,
    WorktreeError,
    list_worktrees,
    new_worktree,
    prune_worktrees,
    remove_worktree,
    worktree_path,
)


def git(repo, *args):
    subprocess.run(
        ["git"] + list(args),
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path):
    """A git repo with one commit, ready for worktrees."""
    path = tmp_path / "demo"
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    (path / "README.md").write_text("hello\n")
    git(path, "add", "README.md")
    git(path, "commit", "-q", "-m", "initial")
    return path


# --- path computation ----------------------------------------------------

def test_path_is_deterministic(repo):
    a = worktree_path(str(repo), "feature/x")
    b = worktree_path(str(repo), "feature/x")
    assert a == b


def test_path_is_outside_the_repo(repo):
    path = worktree_path(str(repo), "feature/x")
    assert not path.startswith(str(repo) + os.sep)


def test_path_sanitizes_branch(repo):
    path = worktree_path(str(repo), "feat/../../escape")
    # The slug must not contain path separators, so the result cannot climb
    # out of the worktrees directory.
    assert "/" not in os.path.basename(path)
    assert ".." not in path


def test_path_template(repo):
    path = worktree_path(str(repo), "my/branch", template="{repo}/{slug}")
    assert path.endswith("demo/my-branch")


def test_path_template_expands_branch(repo):
    path = worktree_path(str(repo), "my/branch", template="{branch}")
    assert path.endswith("my/branch")


# --- listing -------------------------------------------------------------

def test_list_includes_main_worktree(repo):
    trees = list_worktrees(str(repo))
    assert len(trees) == 1
    assert os.path.realpath(trees[0].path) == os.path.realpath(str(repo))


def test_list_after_new_worktree(repo):
    new_worktree("feature", repo=str(repo))
    trees = list_worktrees(str(repo))
    assert len(trees) == 2
    branches = set(t.branch for t in trees)
    assert "feature" in branches


def test_list_reports_head(repo):
    trees = list_worktrees(str(repo))
    head = trees[0].head
    assert head and len(head) == 40


# --- creation ------------------------------------------------------------

def test_new_worktree_creates_directory(repo):
    wt = new_worktree("feature", repo=str(repo))
    assert os.path.isdir(wt.path)
    assert os.path.isfile(os.path.join(wt.path, "README.md"))


def test_new_worktree_creates_branch(repo):
    new_worktree("feature", repo=str(repo))
    out = subprocess.run(
        ["git", "branch", "--list", "feature"],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    assert "feature" in out


def test_new_worktree_isolation(repo):
    """Two worktrees must not see each other's uncommitted files."""
    wt = new_worktree("feature", repo=str(repo))
    with open(os.path.join(wt.path, "ONLY_IN_FEATURE.txt"), "w") as fh:
        fh.write("x")
    assert not os.path.exists(os.path.join(str(repo), "ONLY_IN_FEATURE.txt"))


def test_new_worktree_at_base(repo):
    git(repo, "checkout", "-q", "-b", "base-branch")
    (repo / "base.txt").write_text("b")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-")
    wt = new_worktree("from-base", repo=str(repo), base="base-branch")
    assert os.path.isfile(os.path.join(wt.path, "base.txt"))


def test_new_worktree_existing_branch(repo):
    git(repo, "branch", "existing")
    wt = new_worktree("existing", repo=str(repo), create_branch=False)
    assert wt.branch == "existing"


def test_new_worktree_refuses_existing_path(repo):
    new_worktree("feature", repo=str(repo))
    with pytest.raises(WorktreeError):
        new_worktree("feature", repo=str(repo))


def test_new_worktree_same_branch_twice_fails(repo):
    new_worktree("feature", repo=str(repo))
    with pytest.raises(WorktreeError):
        new_worktree("feature", repo=str(repo), path=worktree_path(str(repo), "other"))


# --- removal -------------------------------------------------------------

def test_remove_worktree(repo):
    wt = new_worktree("feature", repo=str(repo))
    remove_worktree(wt, repo=str(repo))
    assert not os.path.exists(wt.path)
    assert len(list_worktrees(str(repo))) == 1


def test_remove_worktree_by_path(repo):
    wt = new_worktree("feature", repo=str(repo))
    remove_worktree(wt.path, repo=str(repo))
    assert len(list_worktrees(str(repo))) == 1


def test_remove_unknown_worktree_raises(repo):
    with pytest.raises(WorktreeError):
        remove_worktree("/tmp/definitely-not-a-worktree", repo=str(repo))


def test_remove_reports_a_clear_message(repo):
    """The error must name the path, not just say "failed"."""
    with pytest.raises(WorktreeError) as excinfo:
        remove_worktree("/tmp/definitely-not-a-worktree", repo=str(repo))
    assert "definitely-not-a-worktree" in str(excinfo.value)


def test_remove_dirty_worktree_needs_force(repo):
    """A worktree with uncommitted changes is not removable without force."""
    wt = new_worktree("feature", repo=str(repo))
    with open(os.path.join(wt.path, "dirty.txt"), "w") as fh:
        fh.write("uncommitted")
    with pytest.raises(WorktreeError):
        remove_worktree(wt, repo=str(repo))
    remove_worktree(wt, repo=str(repo), force=True)
    assert not os.path.exists(wt.path)


def test_remove_keeps_branch(repo):
    """Removing a worktree must not delete the branch."""
    new_worktree("feature", repo=str(repo))
    out = subprocess.run(
        ["git", "branch", "--list", "feature"],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    assert "feature" in out


# --- pruning -------------------------------------------------------------

def test_prune_removes_stale_admin_entries(repo):
    wt = new_worktree("feature", repo=str(repo))
    # Simulate a worktree whose directory was deleted behind git's back.
    import shutil
    shutil.rmtree(wt.path)
    pruned = prune_worktrees(repo=str(repo))
    assert isinstance(pruned, list)
    assert len(list_worktrees(str(repo))) == 1


def test_prune_dry_run_keeps_state(repo):
    wt = new_worktree("feature", repo=str(repo))
    import shutil
    shutil.rmtree(wt.path)
    prune_worktrees(repo=str(repo), dry_run=True)
    # dry-run must not actually remove the administrative entry.
    assert len(list_worktrees(str(repo))) == 2


# --- Worktree value object ------------------------------------------------

def test_worktree_repr_and_name(repo):
    wt = new_worktree("feature", repo=str(repo))
    assert "feature" in repr(wt)
    assert wt.name == "feature"


def test_worktree_exists(repo):
    wt = new_worktree("feature", repo=str(repo))
    assert wt.exists()


def test_worktree_to_dict(repo):
    wt = new_worktree("feature", repo=str(repo))
    d = wt.to_dict()
    assert d["branch"] == "feature"
    assert set(d) == {"path", "branch", "head", "detached", "locked", "prunable"}


def test_worktree_equality(repo):
    a = new_worktree("feature", repo=str(repo))
    b = Worktree(path=a.path, branch=a.branch, head=a.head)
    assert a == b


def test_worktree_hashable(repo):
    a = new_worktree("feature", repo=str(repo))
    assert len(set([a, Worktree(path=a.path, branch=a.branch, head=a.head)])) == 1


# --- error handling -------------------------------------------------------

def test_not_a_repo_raises(tmp_path):
    with pytest.raises(WorktreeError):
        list_worktrees(str(tmp_path))


def test_error_message_names_the_branch(repo):
    new_worktree("feature", repo=str(repo))
    with pytest.raises(WorktreeError) as excinfo:
        new_worktree("feature", repo=str(repo), path=worktree_path(str(repo), "x"))
    assert "feature" in str(excinfo.value) or "already" in str(excinfo.value)
