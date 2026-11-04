"""tiny-worktree -- zero-dependency git worktree management for parallel agents.

One job: give every concurrent agent its own checkout of the same repo,
without the three-branch-name-typo dance that plain ``git worktree`` requires.
"""

from tiny_worktree.core import (
    Worktree,
    WorktreeError,
    list_worktrees,
    new_worktree,
    prune_worktrees,
    remove_worktree,
    worktree_path,
)

__all__ = [
    "Worktree",
    "WorktreeError",
    "list_worktrees",
    "new_worktree",
    "prune_worktrees",
    "remove_worktree",
    "worktree_path",
]

__version__ = "0.1.0"
