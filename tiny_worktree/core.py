"""Core worktree operations.

Everything here shells out to ``git`` -- there is no pure-Python
implementation of the worktree file format, and reimplementing it would be
exactly the kind of thing that breaks on a git upgrade. The job of this
module is to make the *git* interface safe and hard to misuse.
"""

import os
import re
import subprocess

__all__ = [
    "Worktree",
    "WorktreeError",
    "list_worktrees",
    "new_worktree",
    "prune_worktrees",
    "remove_worktree",
    "worktree_path",
]

# A branch name that is safe to turn into a directory name. Git allows far
# more characters in a branch name than are safe in a path (notably "/" is
# what separates ref components, but "~", ":" and leading dots are worse).
_SAFE_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


class WorktreeError(RuntimeError):
    """Raised when a worktree operation cannot be completed."""


def _run_git(args, cwd=None, check=True):
    """Run git and return stdout as text.

    Raises WorktreeError with git's own stderr attached, because git's error
    text is the only useful diagnostic here ("branch is already checked out",
    "path already exists", ...).
    """
    try:
        proc = subprocess.run(
            ["git"] + list(args),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except OSError as exc:
        raise WorktreeError("could not run git: %s" % exc)

    if check and proc.returncode != 0:
        raise WorktreeError(
            "git %s failed (exit %d): %s"
            % (" ".join(args), proc.returncode, (proc.stderr or proc.stdout).strip())
        )
    return proc


def _repo_root(start=None):
    """Return the absolute path of the git repository containing ``start``."""
    start = os.path.abspath(start or os.getcwd())
    proc = _run_git(["rev-parse", "--show-toplevel"], cwd=start)
    root = proc.stdout.strip()
    if not root:
        raise WorktreeError("not inside a git repository: %s" % start)
    return root


def worktree_path(repo, branch, root=None, template=None):
    """Compute the on-disk path for a branch's worktree.

    The path is deterministic: same repo + same branch -> same path. That
    property is what makes the tool safe to call from several agents at once.

    ``template`` may contain ``{branch}``, ``{slug}`` and ``{repo}``; the
    default is ``<root>/../<repo>-worktrees/{slug}``.
    """
    root = _repo_root(root or repo)
    repo_name = os.path.basename(root)
    slug = _SAFE_SLUG.sub("-", branch).strip("-") or "worktree"
    # Collapse runs of dots. A single dot is legal in a branch name (v1.2.3),
    # but ".." is a parent-directory reference, and a slug made only of dots
    # would resolve outside the worktrees directory entirely.
    slug = re.sub(r"\.{2,}", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-") or "worktree"

    if template:
        return os.path.abspath(
            template.format(branch=branch, slug=slug, repo=repo_name, root=root)
        )
    return os.path.abspath(
        os.path.join(os.path.dirname(root), "%s-worktrees" % repo_name, slug)
    )


class Worktree(object):
    """One worktree: a branch checked out at its own path."""

    __slots__ = ("path", "branch", "head", "detached", "locked", "prunable")

    def __init__(self, path, branch, head=None, detached=False, locked=False,
                 prunable=False):
        self.path = path
        self.branch = branch
        self.head = head
        self.detached = detached
        self.locked = locked
        self.prunable = prunable

    @property
    def name(self):
        """The branch name, or the short commit id when detached."""
        return self.branch or (self.head[:8] if self.head else "")

    def exists(self):
        return os.path.isdir(self.path)

    def to_dict(self):
        return {
            "path": self.path,
            "branch": self.branch,
            "head": self.head,
            "detached": self.detached,
            "locked": self.locked,
            "prunable": self.prunable,
        }

    def __repr__(self):
        return "Worktree(branch=%r, path=%r)" % (self.branch, self.path)

    def __eq__(self, other):
        if not isinstance(other, Worktree):
            return NotImplemented
        return (self.path, self.branch, self.head) == (
            other.path,
            other.branch,
            other.head,
        )

    def __hash__(self):
        return hash((self.path, self.branch, self.head))


def list_worktrees(repo=None):
    """List every worktree of the repository, including the main one.

    Uses ``git worktree list --porcelain``, which is the machine-readable
    form. The default human format is not stable across git versions and
    truncates long paths.
    """
    root = _repo_root(repo)
    proc = _run_git(["worktree", "list", "--porcelain"], cwd=root)
    return _parse_porcelain(proc.stdout)


def _short_branch(ref):
    """Strip the refs/heads/ prefix from a branch ref.

    git reports "refs/heads/feature"; callers almost always want "feature",
    and a bare branch name is what you can pass back to git.
    """
    if not ref:
        return None
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/"):]
    return ref


def _parse_porcelain(text):
    """Parse ``git worktree list --porcelain`` output into Worktree objects.

    The format is a series of blank-line-separated records, each with
    ``key value`` lines. ``detached`` and ``locked`` are flag lines with no
    value; ``prunable`` carries a reason after it.
    """
    trees = []
    record = {}

    def flush():
        if not record:
            return
        path = record.get("worktree")
        if path:
            trees.append(
                Worktree(
                    path=path,
                    branch=_short_branch(record.get("branch")),
                    head=record.get("HEAD"),
                    detached="detached" in record,
                    locked="locked" in record,
                    prunable="prunable" in record,
                )
            )
        record.clear()

    for line in text.splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            flush()
            continue
        key, _, value = line.partition(" ")
        record[key] = value
    flush()
    return trees


def new_worktree(branch, repo=None, path=None, base=None, create_branch=True,
                 force=False, detach=False):
    """Create a worktree for ``branch`` and return it.

    By default a new branch is created at ``base`` (default: the current
    HEAD). Pass ``create_branch=False`` to check out an existing branch.

    If the branch is already checked out in another worktree, git refuses --
    that is the single most common failure in agent workflows, so it is
    reported with a message that names the other worktree.
    """
    root = _repo_root(repo)
    target = os.path.abspath(path) if path else worktree_path(root, branch)

    if os.path.exists(target) and not force:
        raise WorktreeError("path already exists: %s" % target)

    # git's argument order is: worktree add [-b <new-branch>] <path> [<commit-ish>]
    # The path comes BEFORE the commit-ish. Getting this backwards produces
    # "fatal: not a valid object name: <path>", which is git's way of saying
    # it tried to resolve your path as a revision.
    args = ["worktree", "add"]
    if force:
        args.append("--force")
    if detach:
        args.append("--detach")
    if create_branch:
        args += ["-b", branch]
        args.append(target)
        if base:
            args.append(base)
    else:
        args.append(target)
        args.append(branch)

    _run_git(args, cwd=root)

    # Do NOT call list_worktrees() here to find what we just created. That
    # is a second git subprocess, and it roughly doubles the cost of the
    # operation for no new information: we already know the path and the
    # branch. The head is filled in lazily by list_worktrees().
    return Worktree(path=target, branch=branch)


def remove_worktree(target, repo=None, force=False):
    """Remove a worktree. Returns True if something was removed."""
    root = _repo_root(repo)
    path = target.path if isinstance(target, Worktree) else target
    path = os.path.abspath(path)

    # Let git do the validation. "git worktree remove" already refuses to
    # remove a path that is not a worktree of this repository, so listing
    # every worktree first would be a second subprocess spent on a check
    # git already performs.
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(path)
    proc = _run_git(args, cwd=root, check=False)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        if "not a working tree" in message or "is not a working tree" in message:
            raise WorktreeError("not a worktree of this repository: %s" % path)
        raise WorktreeError(
            "git worktree remove failed (exit %d): %s" % (proc.returncode, message)
        )
    return True

    return True


def prune_worktrees(repo=None, dry_run=False):
    """Prune administrative files for worktrees whose directory is gone.

    Returns the list of paths that were (or would be) pruned.
    """
    root = _repo_root(repo)
    args = ["worktree", "prune"]
    if dry_run:
        # --verbose alone still PRUNES; only -n makes it a dry run. Without
        # the -n the caller would believe nothing changed while the stale
        # administrative entries were silently deleted.
        args += ["-n", "--verbose"]
    proc = _run_git(args, cwd=root, check=False)

    pruned = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # --verbose prints "Removing worktrees/foo: gitdir file points to
        # non-existent location" -- the path is the first token.
        match = re.search(r"Removing worktrees/(.+?):", line)
        if match:
            pruned.append(os.path.join(root, ".git", "worktrees", match.group(1)))
        elif line.startswith("Removing"):
            pruned.append(line[len("Removing"):].strip())
    return pruned
