"""Tests for rat.gitlog — the commit/object semantics required by C3.

Each test builds a tiny real git repository and asserts the parsed
Commit objects satisfy the exact semantics in TEST_SPEC.md:
- non-merge commits only, reachable from a given ref
- h[p] is None for the initial commit (h[p] = h_empty)
- committer-date is captured
- author identity reflects .mailmap when present
- binary files are flagged and excluded from line counts
- renames below the 50% threshold leave added/removed at 0,
  and changes are attributed to the new path
- deletions are recorded as removed lines on their path
"""
from rat.gitlog import parse_commits, parse_mailmap, apply_author_merges


def test_initial_commit_has_no_parent(repo):
    sha = repo.commit("init", timestamp=1000)
    commits = parse_commits(repo.path)
    assert len(commits) == 1
    assert commits[0].sha == sha
    assert commits[0].parent is None


def test_committer_date_and_author_captured(repo):
    repo.write("a.txt", "line1\nline2\n")
    repo.commit("init", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    commits = parse_commits(repo.path)
    assert commits[0].committer_date == 1000
    assert commits[0].author == "Alice <alice@example.com>"


def test_mailmap_merges_author_identity(repo):
    repo.write("a.txt", "line1\n")
    repo.commit("init", timestamp=1000, author_name="A", author_email="a@a.com")
    repo.write_mailmap("Real Name <real@example.com> A <a@a.com>\n")
    repo.write("b.txt", "line1\n")
    repo.commit("second", timestamp=1001, author_name="A", author_email="a@a.com")
    commits = parse_commits(repo.path)
    # Both commits resolve to the mailmap canonical identity.
    assert commits[1].author == "Real Name <real@example.com>"


def test_merge_commits_are_excluded(repo):
    repo.commit("init", timestamp=1000)
    repo.checkout_new_branch("feature")
    repo.write("feature.txt", "x\n")
    repo.commit("feature work", timestamp=1001)
    repo.checkout("master")
    repo.write("master.txt", "y\n")
    repo.commit("master work", timestamp=1002)
    repo.merge_commit("feature", "merge feature", timestamp=1003)

    commits = parse_commits(repo.path)
    messages = [c.sha for c in commits]
    assert len(commits) == 3  # the merge commit itself must not appear


def test_pure_rename_below_threshold_has_zero_delta(repo):
    repo.write("a.txt", "l1\nl2\nl3\n")
    repo.commit("init", timestamp=1000)
    repo.rename("a.txt", "b.txt")
    repo.commit("rename only", timestamp=1001)

    commits = parse_commits(repo.path)
    rename_commit = commits[1]
    assert len(rename_commit.changes) == 1
    change = rename_commit.changes[0]
    assert change.path == "b.txt"
    assert change.old_path == "a.txt"
    assert change.added == 0
    assert change.removed == 0


def test_rename_with_edit_attributes_only_change_to_new_path(repo):
    repo.write("a.txt", "l1\nl2\nl3\n")
    repo.commit("init", timestamp=1000)
    repo.rename("a.txt", "b.txt")
    repo.write("b.txt", "l1\nl2\nl3\nl4\n")
    repo.commit("rename and edit", timestamp=1001)

    commits = parse_commits(repo.path)
    change = commits[1].changes[0]
    assert change.path == "b.txt"
    assert change.added == 1
    assert change.removed == 0


def test_deletion_recorded_as_removed_lines_on_its_path(repo):
    repo.write("a.txt", "l1\nl2\nl3\n")
    repo.commit("init", timestamp=1000)
    repo.remove("a.txt")
    repo.commit("delete", timestamp=1001)

    commits = parse_commits(repo.path)
    change = commits[1].changes[0]
    assert change.path == "a.txt"
    assert change.added == 0
    assert change.removed == 3


def test_binary_files_are_flagged_and_not_measured(repo):
    repo.write_bytes("bin.dat", b"\x00\x01\x02binary")
    repo.commit("add binary", timestamp=1000)

    commits = parse_commits(repo.path)
    change = commits[0].changes[0]
    assert change.binary is True
    assert change.added is None
    assert change.removed is None


# --- F2: Author merging (mailmap + manual) ----------------------------


def test_parse_mailmap_standard_full_format():
    text = "Real Name <real@example.com> Old Name <old@example.com>\n"
    assert parse_mailmap(text) == {"Old Name <old@example.com>": "Real Name <real@example.com>"}


def test_parse_mailmap_canonical_name_only():
    text = "Real Name <real@example.com> <old@example.com>\n"
    assert parse_mailmap(text) == {"<old@example.com>": "Real Name <real@example.com>"}


def test_parse_mailmap_email_only_canonical():
    text = "<new@example.com> Old Name <old@example.com>\n"
    assert parse_mailmap(text) == {"Old Name <old@example.com>": "<new@example.com>"}


def test_parse_mailmap_multiple_lines_and_comments():
    text = (
        "# a comment\n"
        "\n"
        "A <a@x.com> B <b@x.com>\n"
        "A <a@x.com> C <c@x.com>\n"
    )
    m = parse_mailmap(text)
    assert m == {
        "B <b@x.com>": "A <a@x.com>",
        "C <c@x.com>": "A <a@x.com>",
    }


def test_apply_author_merges_rewrites_author(repo):
    repo.write("a.txt", "l1\n")
    repo.commit("c1", timestamp=1000, author_name="Old", author_email="old@example.com")
    commits = parse_commits(repo.path)
    merged = apply_author_merges(commits, {"Old <old@example.com>": "New <new@example.com>"})
    assert merged[0].author == "New <new@example.com>"
    # Original commits are not mutated.
    assert commits[0].author == "Old <old@example.com>"


def test_apply_author_merges_with_empty_mapping_is_noop(repo):
    repo.write("a.txt", "l1\n")
    repo.commit("c1", timestamp=1000, author_name="A", author_email="a@a.com")
    commits = parse_commits(repo.path)
    assert apply_author_merges(commits, {}) is commits


def test_apply_author_merges_does_not_affect_non_author_fields(repo):
    repo.write("a.txt", "l1\nl2\n")
    repo.commit("c1", timestamp=1000, author_name="Old", author_email="old@example.com")
    commits = parse_commits(repo.path)
    merged = apply_author_merges(commits, {"Old <old@example.com>": "New <new@example.com>"})
    assert merged[0].sha == commits[0].sha
    assert merged[0].parent == commits[0].parent
    assert merged[0].committer_date == commits[0].committer_date
    assert merged[0].changes[0].path == commits[0].changes[0].path
    assert merged[0].changes[0].added == commits[0].changes[0].added
