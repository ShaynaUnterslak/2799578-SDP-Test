"""Shared pytest fixtures for building small, deterministic git repositories
used to verify the metric formulas defined in TEST_SPEC.md (C3-C8).
"""
import os
import subprocess

import pytest


def _run(args, cwd):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_AUTHOR_DATE": "", "GIT_COMMITTER_DATE": ""},
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.stdout


class RepoBuilder:
    """Small helper to script a git repository commit-by-commit with
    deterministic committer dates and authors, for use in tests.
    """

    def __init__(self, path):
        self.path = str(path)
        os.makedirs(self.path, exist_ok=True)
        _run(["init", "-q", "-b", "master"], self.path)
        _run(["config", "user.email", "default@example.com"], self.path)
        _run(["config", "user.name", "Default"], self.path)

    def write(self, relpath, content):
        full = os.path.join(self.path, relpath)
        os.makedirs(os.path.dirname(full) or self.path, exist_ok=True)
        with open(full, "w") as fh:
            fh.write(content)

    def write_bytes(self, relpath, content: bytes):
        full = os.path.join(self.path, relpath)
        os.makedirs(os.path.dirname(full) or self.path, exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(content)

    def remove(self, relpath):
        os.remove(os.path.join(self.path, relpath))

    def rename(self, src, dst):
        full_dst = os.path.join(self.path, dst)
        os.makedirs(os.path.dirname(full_dst) or self.path, exist_ok=True)
        os.rename(os.path.join(self.path, src), full_dst)

    def commit(self, message, timestamp, author_name="Default", author_email="default@example.com"):
        _run(["add", "-A"], self.path)
        date = f"@{timestamp} +0000"
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
            "GIT_COMMITTER_DATE": date,
        }
        result = subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", message],
            cwd=self.path,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git commit failed: {result.stderr}")
        sha = _run(["rev-parse", "HEAD"], self.path).strip()
        return sha

    def merge_commit(self, other_sha, message, timestamp):
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Default",
            "GIT_AUTHOR_EMAIL": "default@example.com",
            "GIT_AUTHOR_DATE": f"@{timestamp} +0000",
            "GIT_COMMITTER_NAME": "Default",
            "GIT_COMMITTER_EMAIL": "default@example.com",
            "GIT_COMMITTER_DATE": f"@{timestamp} +0000",
        }
        result = subprocess.run(
            ["git", "merge", "-q", "--no-ff", "-m", message, other_sha],
            cwd=self.path,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git merge failed: {result.stderr}")
        return _run(["rev-parse", "HEAD"], self.path).strip()

    def checkout_new_branch(self, name):
        _run(["checkout", "-q", "-b", name], self.path)

    def checkout(self, name):
        _run(["checkout", "-q", name], self.path)

    def write_mailmap(self, content):
        self.write(".mailmap", content)


@pytest.fixture
def repo(tmp_path):
    return RepoBuilder(tmp_path / "repo")
