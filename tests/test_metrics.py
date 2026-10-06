"""Tests for rat.metrics — File/Directory/Repository/Commit-set/Author
metrics (C4-C8), computed from hand-worked expected values matching the
formulas in TEST_SPEC.md section 2.
"""
from rat.gitlog import parse_commits
from rat.metrics import (
    build_object_table,
    commit_set_metrics,
    author_ownership,
    H_t,
    H_ij,
)


def test_file_metrics_added_removed_growth_churn(repo):
    # commit1: a.txt added with 3 lines (l+=3, l-=0)
    repo.write("a.txt", "l1\nl2\nl3\n")
    repo.commit("init", timestamp=1000)
    # commit2: a.txt -> 2 lines removed, 1 added (l+=1, l-=2)
    repo.write("a.txt", "l1\nl4\n")
    repo.commit("edit", timestamp=1001)

    commits = parse_commits(repo.path)
    table = build_object_table(commits)

    c1, c2 = commits[0].sha, commits[1].sha
    assert table["a.txt"][c1] == (3, 0)
    assert table["a.txt"][c2] == (1, 2)
    # growth = l+ - l- ; churn = l+ + l-
    added, removed = table["a.txt"][c2]
    assert added - removed == -1  # growth
    assert added + removed == 3  # churn


def test_directory_metrics_aggregate_immediate_children_recursively(repo):
    repo.write("foo/bar.txt", "l1\nl2\n")
    repo.write("foo/baz/beef.py", "l1\n")
    repo.commit("init", timestamp=1000)

    commits = parse_commits(repo.path)
    table = build_object_table(commits)
    c1 = commits[0].sha

    # foo/baz aggregates beef.py (1,0); foo aggregates bar.txt + foo/baz (3,0)
    assert table["foo/baz"][c1] == (1, 0)
    assert table["foo"][c1] == (3, 0)
    # repository root aggregates everything
    assert table[""][c1] == (3, 0)


def test_repository_metrics_is_directory_metrics_on_root(repo):
    repo.write("a.txt", "l1\nl2\n")
    repo.write("dir/b.txt", "l1\n")
    repo.commit("init", timestamp=1000)

    commits = parse_commits(repo.path)
    table = build_object_table(commits)
    c1 = commits[0].sha
    assert table[""][c1] == (3, 0)


def test_commit_set_metrics_sum_added_removed_growth_churn(repo):
    repo.write("a.txt", "l1\nl2\n")
    repo.commit("init", timestamp=1000)
    repo.write("a.txt", "l1\nl2\nl3\n")
    repo.commit("edit", timestamp=1001)

    commits = parse_commits(repo.path)
    H = commits  # full history
    metrics = commit_set_metrics(H, "a.txt")
    assert metrics["added"] == 3  # 2 + 1
    assert metrics["removed"] == 0
    assert metrics["growth"] == 3
    assert metrics["churn"] == 3
    assert metrics["modifications"] == 2
    assert metrics["modification_frequency"] == 1.0  # 2/2
    assert metrics["churn_rate"] == 1.5  # 3/2


def test_commit_set_metrics_zero_division_guards_on_empty_set():
    metrics = commit_set_metrics([], "a.txt")
    assert metrics["modification_frequency"] == 0
    assert metrics["churn_rate"] == 0


def test_H_t_filters_by_committer_date_inclusive(repo):
    repo.write("a.txt", "1\n")
    c1 = repo.commit("c1", timestamp=1000)
    repo.write("a.txt", "1\n2\n")
    c2 = repo.commit("c2", timestamp=2000)
    commits = parse_commits(repo.path)

    filtered = H_t(commits, 2000)
    assert [c.sha for c in filtered] == [c2]


def test_H_ij_inclusive_start_exclusive_end(repo):
    repo.write("a.txt", "1\n")
    c1 = repo.commit("c1", timestamp=1000)
    repo.write("a.txt", "1\n2\n")
    c2 = repo.commit("c2", timestamp=2000)
    repo.write("a.txt", "1\n2\n3\n")
    c3 = repo.commit("c3", timestamp=3000)
    commits = parse_commits(repo.path)

    filtered = H_ij(commits, 1000, 3000)
    assert [c.sha for c in filtered] == [c1, c2]


def test_author_ownership_fraction_of_churn(repo):
    repo.write("a.txt", "l1\nl2\n")
    repo.commit("init", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    repo.write("a.txt", "l1\nl2\nl3\n")
    repo.commit("edit", timestamp=1001, author_name="Bob", author_email="bob@example.com")

    commits = parse_commits(repo.path)
    H = commits
    ownership = author_ownership(H, "a.txt", "Alice <alice@example.com>")
    # Alice contributed churn=2 (l+2,l-0), Bob contributed churn=1 (l+1,l-0); total churn=3
    assert ownership == 2 / 3


def test_author_ownership_zero_when_object_has_zero_churn(repo):
    repo.commit("init", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    commits = parse_commits(repo.path)
    ownership = author_ownership(commits, "nonexistent.txt", "Alice <alice@example.com>")
    assert ownership == 0
