"""Metric computation for File, Directory, Repository, Commit-set and
Author metrics, per TEST_SPEC.md section 2 ("Metrics") and C4-C8.

Design note: a directory's metric at a commit is, by definition, the sum
over its *immediate* children (files and subdirectories). Because that
definition unwinds recursively down to leaf files, it is mathematically
equivalent -- and far simpler/faster to compute -- to add every file
change directly onto *all* of its ancestor directories (including the
root, path ""), rather than summing bottom-up per directory level. Both
approaches yield identical totals; this module uses the ancestor-fan-out
approach.
"""
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from rat.gitlog import Commit

# object_path -> commit_sha -> (added, removed)
ObjectTable = Dict[str, Dict[str, Tuple[int, int]]]


def _ancestors(file_path: str) -> List[str]:
    """Return every ancestor directory path of a file, including the
    root ("") and the file's immediate parent directory.
    """
    parts = file_path.split("/")[:-1]
    result = [""]
    cur = ""
    for part in parts:
        cur = f"{cur}/{part}" if cur else part
        result.append(cur)
    return result


def build_object_table(commits: List[Commit]) -> ObjectTable:
    """Build the (object, commit) -> (added, removed) table for files and
    directories (including the root) from a list of commits. Binary file
    changes are skipped entirely, since they are not measured.
    """
    table: ObjectTable = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for commit in commits:
        for change in commit.changes:
            if change.binary:
                continue
            added, removed = change.added, change.removed
            targets = [change.path] + _ancestors(change.path)
            for obj in targets:
                entry = table[obj][commit.sha]
                entry[0] += added
                entry[1] += removed
    # Freeze inner lists to tuples for a stable public return type.
    return {obj: {sha: tuple(v) for sha, v in shas.items()} for obj, shas in table.items()}


def H_t(commits: List[Commit], t: int) -> List[Commit]:
    """H_t := {h in H-bar | t <= h[committer-date]}."""
    return [c for c in commits if c.committer_date >= t]


def H_ij(commits: List[Commit], i: int, j: int) -> List[Commit]:
    """H_{i,j} := {h in H-bar | i <= h[committer-date] < j}."""
    return [c for c in commits if i <= c.committer_date < j]


def _per_commit_deltas(commits: List[Commit], obj: str):
    """Yield (commit, added, removed) for every commit in `commits` that
    touches `obj` (file or directory), honouring the ancestor fan-out.
    """
    table = build_object_table(commits)
    obj_entries = table.get(obj, {})
    by_sha = {c.sha: c for c in commits}
    for sha, (added, removed) in obj_entries.items():
        commit = by_sha.get(sha)
        if commit is not None:
            yield commit, added, removed


def commit_set_metrics(commits: List[Commit], obj: str) -> dict:
    """Aggregate added/removed/growth/churn/modifications/modification
    frequency/churn rate for `obj` over the commit set `commits` (C7).
    """
    added_total = 0
    removed_total = 0
    modifications = 0
    for _commit, added, removed in _per_commit_deltas(commits, obj):
        added_total += added
        removed_total += removed
        if added + removed > 0:
            modifications += 1

    size = len(commits)
    growth = added_total - removed_total
    churn = added_total + removed_total
    return {
        "added": added_total,
        "removed": removed_total,
        "growth": growth,
        "churn": churn,
        "modifications": modifications,
        "modification_frequency": (modifications / size) if size else 0,
        "churn_rate": (churn / size) if size else 0,
    }


def author_modifications(commits: List[Commit], obj: str, author: str) -> int:
    """n_{H,o,a}: commits by `author` that have at least one change on `obj`."""
    count = 0
    for commit, added, removed in _per_commit_deltas(commits, obj):
        if commit.author == author and (added + removed) > 0:
            count += 1
    return count


def author_churn(commits: List[Commit], obj: str, author: str) -> int:
    """lambda_{H,o,a}: total churn on `obj` contributed by `author`."""
    total = 0
    for commit, added, removed in _per_commit_deltas(commits, obj):
        if commit.author == author:
            total += added + removed
    return total


def author_ownership(commits: List[Commit], obj: str, author: str) -> float:
    """omega_{H,o,a}: fraction of total churn on `obj` from `author`,
    0 when the object has zero total churn.
    """
    total_churn = sum(added + removed for _c, added, removed in _per_commit_deltas(commits, obj))
    if total_churn == 0:
        return 0
    return author_churn(commits, obj, author) / total_churn
