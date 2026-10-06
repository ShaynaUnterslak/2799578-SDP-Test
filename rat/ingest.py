"""Repository ingestion per TEST_SPEC.md C2:
- a zip file of the repo with the .git file or directory
- a remote repository URL that is then deeply cloned

Both forms must work without authentication for public repositories, and
the clone must be a full (deep) clone so complete history is available
for metric computation.
"""
import os
import shutil
import subprocess
import zipfile


class IngestError(Exception):
    """Raised when a repository cannot be ingested (bad zip, missing
    .git, unsafe zip contents, or a failed clone)."""


def _find_repo_root(extract_dir: str) -> str:
    """Locate the directory containing a `.git` file or directory inside
    the extracted zip (it may be nested one level, e.g. my-repo/.git)."""
    for root, dirs, _files in os.walk(extract_dir):
        if ".git" in dirs or ".git" in _files:
            return root
    raise IngestError("Zip file does not contain a .git file or directory")


def _safe_extract(zf: zipfile.ZipFile, dest_dir: str) -> None:
    dest_abs = os.path.abspath(dest_dir)
    for member in zf.infolist():
        member_path = os.path.abspath(os.path.join(dest_abs, member.filename))
        if not (member_path == dest_abs or member_path.startswith(dest_abs + os.sep)):
            raise IngestError(f"Unsafe path in zip file: {member.filename}")
    zf.extractall(dest_abs)


def ingest_zip(zip_path: str, dest_dir: str) -> str:
    """Extract `zip_path` into `dest_dir` and return the path to the
    repository root (the directory containing .git). Raises IngestError
    if the zip is invalid, unsafe, or does not contain a .git entry.
    """
    if not zipfile.is_zipfile(zip_path):
        raise IngestError("Uploaded file is not a valid zip archive")

    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        _safe_extract(zf, dest_dir)

    return _find_repo_root(dest_dir)


# Default ceiling on how long a clone may run before we give up and
# report a clean error instead of blocking the request forever.
DEFAULT_CLONE_TIMEOUT_SECONDS = 120


def ingest_clone(url: str, dest_dir: str, timeout: int = DEFAULT_CLONE_TIMEOUT_SECONDS) -> str:
    """Deep-clone `url` into `dest_dir` and return the repository path.
    A plain `git clone` (no --depth) fetches full history, satisfying
    the "deeply cloned" requirement.

    Interactive credential/terminal prompts are disabled (a web request
    has no terminal to answer them, so git would otherwise hang
    indefinitely on a bad or private URL), and the process is bounded by
    `timeout` seconds so an unreachable host or hung network also fails
    cleanly instead of blocking forever.
    """
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",  # never prompt for username/password
        "GIT_ASKPASS": "echo",  # belt-and-braces: any askpass call returns empty
        "GIT_SSH_COMMAND": "ssh -oBatchMode=yes",  # never prompt over SSH either
    }
    try:
        result = subprocess.run(
            ["git", "clone", "--no-local", url, dest_dir],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise IngestError(
            f"Cloning timed out after {timeout}s. Check the URL is correct, public, "
            "and reachable without authentication."
        )
    if result.returncode != 0:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise IngestError(f"Failed to clone repository: {result.stderr.strip()}")
    return dest_dir
