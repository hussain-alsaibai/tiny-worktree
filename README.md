# tiny-worktree

[![CI](https://github.com/hussain-alsaibai/tiny-worktree/actions/workflows/ci.yml/badge.svg)](https://github.com/hussain-alsaibai/tiny-worktree/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Deps](https://img.shields.io/badge/dependencies-0-orange.svg)](pyproject.toml)

**Zero-dependency git worktree management for parallel AI agents.**

One branch, one checkout, one command. No dependencies beyond the Python
standard library and `git` itself.

---

## Why

Plain `git worktree` works. It is just easy to misuse.

```bash
git worktree add -b feat/issue-42 ../myrepo.feat-42
cd ../myrepo.feat-42
```

You typed the branch name twice and the path once, and if the two disagree
you get a worktree on a branch you did not expect. Now multiply that by six
agents working the same repo overnight.

`tiny-worktree` takes the branch name and derives everything else:

```python
from tiny_worktree import new_worktree

wt = new_worktree("feat/issue-42")
# -> /path/to/myrepo-worktrees/feat-issue-42
```

Same repo, same branch, same path. Every time. That determinism is the
whole point: six agents can each ask for their own worktree without
coordinating, and nobody has to remember where anything went.

## Install

```bash
pip install git+https://github.com/hussain-alsaibai/tiny-worktree.git
```

Not on PyPI yet — the PyPI name `tiny-worktree` is claimed by another
project, and shipping to a name someone else owns would install their code
into your project. The GitHub URL above is the supported install.

## Usage

### Python

```python
from tiny_worktree import (
    new_worktree,
    list_worktrees,
    remove_worktree,
    worktree_path,
)

# Create a worktree on a new branch (created at HEAD).
wt = new_worktree("feat/issue-42")
print(wt.path)          # /path/to/myrepo-worktrees/feat-issue-42
print(wt.branch)        # feat/issue-42

# Create it from a different base.
wt = new_worktree("fix/urgent", base="main")

# Check out a branch that already exists.
wt = new_worktree("release/2.0", create_branch=False)

# See everything.
for wt in list_worktrees():
    print(wt.name, wt.path, wt.detached)

# Clean up.
remove_worktree(wt)
```

### CLI

```bash
tiny-worktree new feat/issue-42        # create; prints the path
tiny-worktree new feat/issue-42 --base main
tiny-worktree list                     # name + path for every worktree
tiny-worktree path feat/issue-42       # print the path it would get
tiny-worktree rm feat/issue-42         # remove it
tiny-worktree exec feat/issue-42 pytest # run a command inside it
tiny-worktree prune                    # clean up stale admin entries
```

Add `--json` to `new`, `list`, or `prune` for machine-readable output.

## API

| Function | What it does |
|---|---|
| `new_worktree(branch, ...)` | Create a worktree; returns a `Worktree` |
| `list_worktrees(repo=None)` | Every worktree including the main one |
| `remove_worktree(target, force=False)` | Remove a worktree by path or object |
| `worktree_path(repo, branch, template=None)` | The path a branch would get |
| `prune_worktrees(dry_run=False)` | Drop admin files for deleted worktrees |

`Worktree` exposes `path`, `branch`, `head`, `detached`, `locked`,
`prunable`, `name`, `exists()`, and `to_dict()`.

All failures raise `WorktreeError` with git's own message attached — the
stderr text is the only useful diagnostic when git refuses an operation.

## Behavior worth knowing

**Paths are sanitized.** A branch named `feat/../../escape` becomes
`feat-..-..-escape`, and dot runs are collapsed. A branch can never
resolve to a directory outside the worktrees directory.

**Removal refuses to lose work.** A worktree with uncommitted changes is
not removable unless you pass `force=True`. git enforces this too; the
library does not paper over it.

**`prune(dry_run=True)` really is a dry run.** It passes git's `-n`
flag. Without `-n`, `git worktree prune --verbose` still prunes — a
caller who believed they were previewing would have silently deleted the
stale entries. This was a real bug found by the test suite.

**`new_worktree` does not re-list after creating.** It already knows the
path and the branch, and a second `git worktree list` subprocess roughly
doubled the cost of the operation.

## Benchmark

Measured on this machine with `python benchmark.py 25`, comparing
`new_worktree()` + `remove_worktree()` against the equivalent raw
`git worktree add` + `git worktree remove`:

| Operation | Time |
|---|---|
| raw `git worktree add` + remove | 12.6 ms |
| `tiny-worktree` new + remove | 17.5 ms |
| overhead | 4.9 ms |
| `list_worktrees()` | 3.5 ms |

The overhead is the Python-side path computation and error handling, and it
is the same order as the git calls themselves. For the use case — setting up
a worktree once, then running a long agent task in it — that is not the
bottleneck. If you are creating thousands of worktrees in a tight loop,
use raw git.

## Agent workflow

The pattern this exists for:

```python
import subprocess
from tiny_worktree import new_worktree, remove_worktree

def run_task(branch, task):
    wt = new_worktree(branch)
    try:
        return subprocess.run(
            ["claude", "-p", task],
            cwd=wt.path,
            check=False,
        ).returncode
    finally:
        remove_worktree(wt, force=True)
```

Each task gets a clean checkout. Uncommitted work in one task cannot be
seen by another. Cleanup happens even if the agent crashes.

## Tests

```bash
python -m pytest tests/ -v
```

30 tests. Every test that touches git runs against a real throwaway
repository created in a temp directory — the value of this package is in how
it drives git, and a mocked git would only test the mock.

## Requirements

- Python 3.8+
- `git` on PATH

No runtime dependencies. Tested on Python 3.8, 3.9, 3.10, 3.11 and 3.12.

## Part of the tiny-* ecosystem

- [`tiny-router`](https://github.com/hussain-alsaibai/tiny-router) — HTTP router
- [`tiny-log`](https://github.com/hussain-alsaibai/tiny-log) — structured logging
- [`tiny-validator`](https://github.com/hussain-alsaibai/tiny-validator) — input validation
- [`tiny-config`](https://github.com/hussain-alsaibai/tiny-config) — configuration loader
- [`tiny-cli`](https://github.com/hussain-alsaibai/tiny-cli) — CLI builder
- [`fast-cache`](https://github.com/hussain-alsaibai/fast-cache) — LRU + TTL cache
- [`snapdb`](https://github.com/hussain-alsaibai/snapdb) — in-memory database

## License

MIT
