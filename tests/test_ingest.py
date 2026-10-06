"""Tests for rat.ingest — repository ingestion via zip (with .git) and
remote URL deep clone, per TEST_SPEC.md C2.
"""
import os
import zipfile

import pytest

from rat.ingest import IngestError, ingest_zip, ingest_clone


def _make_zip_with_git_repo(repo, zip_path):
    """Zip up a real git repo directory (including its .git dir)."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, _dirs, files in os.walk(repo.path):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, os.path.dirname(repo.path))
                zf.write(full, rel)


def test_ingest_zip_with_git_dir_succeeds(repo, tmp_path):
    repo.write("a.txt", "hello\n")
    repo.commit("init", timestamp=1000)
    zip_path = tmp_path / "repo.zip"
    _make_zip_with_git_repo(repo, zip_path)

    dest = tmp_path / "ingested"
    result_path = ingest_zip(str(zip_path), str(dest))

    assert os.path.isdir(os.path.join(result_path, ".git"))


def test_ingest_zip_without_git_dir_is_rejected(tmp_path):
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    (plain_dir / "a.txt").write_text("hello\n")
    zip_path = tmp_path / "plain.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(plain_dir / "a.txt", "plain/a.txt")

    with pytest.raises(IngestError):
        ingest_zip(str(zip_path), str(tmp_path / "dest"))


def test_ingest_zip_rejects_path_traversal(tmp_path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")

    with pytest.raises(IngestError):
        ingest_zip(str(zip_path), str(tmp_path / "dest"))


def test_ingest_clone_deep_clones_full_history(repo, tmp_path):
    repo.write("a.txt", "1\n")
    repo.commit("c1", timestamp=1000)
    repo.write("a.txt", "1\n2\n")
    repo.commit("c2", timestamp=1001)

    dest = tmp_path / "cloned"
    result_path = ingest_clone(repo.path, str(dest))

    from rat.gitlog import parse_commits
    commits = parse_commits(result_path)
    assert len(commits) == 2  # full history present, not a shallow clone


def test_ingest_clone_invalid_repo_fails_cleanly(tmp_path):
    # A path that is not a git repository at all must fail fast with a
    # readable IngestError, not hang or crash the caller.
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()
    with pytest.raises(IngestError):
        ingest_clone(str(not_a_repo), str(tmp_path / "dest1"))


def test_ingest_clone_times_out_instead_of_hanging_forever(monkeypatch):
    """If the underlying git process hangs (e.g. network issue or an
    interactive credential prompt), ingest_clone must not block the
    caller forever -- it should raise IngestError once the timeout is
    hit.
    """
    import subprocess

    from rat import ingest

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(ingest.subprocess, "run", fake_run)

    with pytest.raises(IngestError):
        ingest_clone("https://example.invalid/does-not-exist.git", "/tmp/unused-dest", timeout=1)


def test_ingest_clone_disables_interactive_prompts(monkeypatch):
    """git must never attempt an interactive username/password or
    credential-helper prompt -- that would hang a non-interactive web
    request indefinitely.
    """
    from rat import ingest

    captured = {}

    class FakeResult:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        return FakeResult()

    monkeypatch.setattr(ingest.subprocess, "run", fake_run)

    ingest_clone("https://example.invalid/repo.git", "/tmp/unused-dest2")

    assert captured["env"] is not None
    assert captured["env"].get("GIT_TERMINAL_PROMPT") == "0"
