"""Benchmark tiny-worktree against the equivalent raw git commands.

Run: python benchmark.py
"""

import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tiny_worktree import list_worktrees, new_worktree, remove_worktree


def sh(args, cwd=None):
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def make_repo(root):
    path = os.path.join(root, "bench")
    os.makedirs(path)
    sh(["init", "-q"], cwd=path)
    sh(["config", "user.email", "b@example.com"], cwd=path)
    sh(["config", "user.name", "B"], cwd=path)
    with open(os.path.join(path, "f.txt"), "w") as fh:
        fh.write("x")
    sh(["add", "f.txt"], cwd=path)
    sh(["commit", "-q", "-m", "i"], cwd=path)
    return path


def timeit(fn, n):
    start = time.perf_counter()
    for i in range(n):
        fn(i)
    return (time.perf_counter() - start) / n * 1000.0


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    with tempfile.TemporaryDirectory() as root:
        repo = make_repo(root)

        # 1. raw git worktree add
        def raw_add(i):
            branch = "raw-%d" % i
            target = os.path.join(root, "raw-%d" % i)
            sh(["worktree", "add", "-q", "-b", branch, target], cwd=repo)
            sh(["worktree", "remove", "--force", target], cwd=repo)

        raw_ms = timeit(raw_add, n)

        # 2. tiny-worktree new + remove
        def tiny_add(i):
            branch = "tiny-%d" % i
            wt = new_worktree(branch, repo=repo)
            remove_worktree(wt, repo=repo, force=True)

        tiny_ms = timeit(tiny_add, n)

        # 3. listing
        list_ms = timeit(lambda i: list_worktrees(repo), n * 5)

        print("tiny-worktree benchmark (n=%d)" % n)
        print("  raw git worktree add+remove : %8.3f ms" % raw_ms)
        print("  tiny-worktree new+remove     : %8.3f ms" % tiny_ms)
        print("  overhead                     : %8.3f ms" % (tiny_ms - raw_ms))
        print("  list_worktrees()             : %8.3f ms" % list_ms)


if __name__ == "__main__":
    main()
