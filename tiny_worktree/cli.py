"""Command-line interface for tiny-worktree.

Usage:
    tiny-worktree new <branch>      create a worktree for a branch
    tiny-worktree list              list worktrees
    tiny-worktree rm <branch>       remove a worktree
    tiny-worktree path <branch>     print the path a branch would get
    tiny-worktree prune             prune stale worktree admin files
    tiny-worktree exec <branch> ... run a command inside a worktree
"""

import argparse
import json
import subprocess
import sys

from tiny_worktree.core import (
    WorktreeError,
    list_worktrees,
    new_worktree,
    prune_worktrees,
    remove_worktree,
    worktree_path,
)


def _find_by_branch(branch):
    """Find the worktree whose branch matches, or None."""
    for wt in list_worktrees():
        if wt.branch and wt.branch.split("/")[-1] == branch:
            return wt
    return None


def cmd_new(args):
    wt = new_worktree(
        args.branch,
        base=args.base,
        create_branch=not args.no_branch,
        force=args.force,
    )
    if args.json:
        print(json.dumps(wt.to_dict(), indent=2))
    else:
        print(wt.path)
    return 0


def cmd_list(args):
    trees = list_worktrees()
    if args.json:
        print(json.dumps([w.to_dict() for w in trees], indent=2))
        return 0
    for wt in trees:
        flags = []
        if wt.detached:
            flags.append("detached")
        if wt.locked:
            flags.append("locked")
        if wt.prunable:
            flags.append("prunable")
        suffix = " (%s)" % ", ".join(flags) if flags else ""
        print("%-28s %s%s" % (wt.name, wt.path, suffix))
    return 0


def cmd_rm(args):
    wt = _find_by_branch(args.branch)
    if wt is None:
        print("no worktree for branch: %s" % args.branch, file=sys.stderr)
        return 1
    remove_worktree(wt, force=args.force)
    if not args.quiet:
        print("removed %s" % wt.path)
    return 0


def cmd_path(args):
    print(worktree_path(None, args.branch))
    return 0


def cmd_prune(args):
    pruned = prune_worktrees(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(pruned, indent=2))
    else:
        for path in pruned:
            print(path)
    return 0


def cmd_exec(args):
    wt = _find_by_branch(args.branch)
    if wt is None:
        print("no worktree for branch: %s" % args.branch, file=sys.stderr)
        return 1
    if not wt.exists():
        print("worktree path is gone: %s" % wt.path, file=sys.stderr)
        return 1
    proc = subprocess.run(args.command, cwd=wt.path)
    return proc.returncode


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tiny-worktree",
        description="Zero-dependency git worktree management for parallel agents.",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd")

    p_new = sub.add_parser("new", help="create a worktree for a branch")
    p_new.add_argument("branch")
    p_new.add_argument("--base", help="base ref for the new branch")
    p_new.add_argument("--no-branch", action="store_true",
                       help="check out an existing branch instead of creating one")
    p_new.add_argument("--force", action="store_true")
    p_new.set_defaults(func=cmd_new)

    p_list = sub.add_parser("list", help="list worktrees")
    p_list.set_defaults(func=cmd_list)

    p_rm = sub.add_parser("rm", help="remove a worktree")
    p_rm.add_argument("branch")
    p_rm.add_argument("--force", action="store_true")
    p_rm.add_argument("--quiet", action="store_true")
    p_rm.set_defaults(func=cmd_rm)

    p_path = sub.add_parser("path", help="print the path for a branch")
    p_path.add_argument("branch")
    p_path.set_defaults(func=cmd_path)

    p_prune = sub.add_parser("prune", help="prune stale worktree admin files")
    p_prune.add_argument("--dry-run", action="store_true")
    p_prune.set_defaults(func=cmd_prune)

    p_exec = sub.add_parser("exec", help="run a command inside a worktree")
    p_exec.add_argument("branch")
    p_exec.add_argument("command", nargs=argparse.REMAINDER)
    p_exec.set_defaults(func=cmd_exec)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except WorktreeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
