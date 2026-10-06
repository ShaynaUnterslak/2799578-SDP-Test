"""Parse git history into Commit/FileChange objects per TEST_SPEC.md C3.

Semantics implemented here (see TEST_SPEC.md "C3 - Commit/object semantics"):
- H-bar is the set of non-merge commits reachable from a reference commit
  (default HEAD) -> achieved with `git log --no-merges <ref>`.
- h[p] is the commit's single parent, or None for the initial commit
  (h[p] = h_empty).
- h[committer-date] is the committer date as a unix timestamp.
- h[a] is the commit author identity *after* mailmap resolution
  (git's %aN/%aE honour .mailmap automatically when present).
- Rename detection is enabled at a 50% threshold (-M50%); a pure rename
  therefore produces a change with added=removed=0 attributed to the new
  path, and a changed+renamed file attributes only the content change to
  the new path.
- A deleted file (exists in h[p] but not h) is recorded as removed lines
  on its (old) path.
- Binary files are flagged and have added/removed set to None, since
  "binary files are not measured".
"""
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

_NUMSTAT_FORMAT = "COMMIT\t%H\t%P\t%cd\t%aN\t%aE"


@dataclass
class FileChange:
    path: str
    old_path: Optional[str]
    added: Optional[int]
    removed: Optional[int]
    binary: bool = False


@dataclass
class Commit:
    sha: str
    parent: Optional[str]
    committer_date: int
    author: str
    changes: List[FileChange] = field(default_factory=list)


class GitCommandError(RuntimeError):
    """Raised when the underlying git command fails."""


def _run_git(args, cwd):
    result = subprocess.run(
        ["git", "-C", cwd] + args,
        capture_output=True,
    )
    if result.returncode != 0:
        raise GitCommandError(result.stderr.decode(errors="replace"))
    return result.stdout


def parse_commits(repo_path: str, ref: str = "HEAD") -> List[Commit]:
    """Return H-bar: non-merge commits reachable from `ref`, oldest first,
    each with its per-file numstat changes (added/removed lines, renames,
    binary flags) relative to its parent.
    """
    raw = _run_git(
        [
            "log",
            "--no-merges",
            "--reverse",
            "--date=unix",
            "--numstat",
            "-M50%",
            "-z",
            f"--pretty=format:{_NUMSTAT_FORMAT}",
            ref,
        ],
        cwd=repo_path,
    )
    return _parse_numstat_z(raw.decode("utf-8", errors="replace"))


def _parse_numstat_z(text: str) -> List[Commit]:
    tokens = text.split("\x00")
    commits: List[Commit] = []
    cur: Optional[Commit] = None
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        i += 1
        if tok == "":
            continue
        if tok.startswith("COMMIT\t"):
            if cur is not None:
                commits.append(cur)
            header_line, _, rest = tok.partition("\n")
            fields = header_line.split("\t")
            # fields: COMMIT, sha, parents, date, authorName, authorEmail
            _, sha, parents_str, date_str, author_name, author_email = fields
            parents = parents_str.split()
            cur = Commit(
                sha=sha,
                parent=parents[0] if parents else None,
                committer_date=int(date_str),
                author=f"{author_name} <{author_email}>",
            )
            tok = rest
            if tok == "":
                continue
        # tok is a numstat line: "<added>\t<removed>\t<path-or-empty>"
        added_str, removed_str, path = tok.split("\t", 2)
        if path == "":
            old_path = tokens[i]
            i += 1
            new_path = tokens[i]
            i += 1
            cur.changes.append(_make_change(new_path, old_path, added_str, removed_str))
        else:
            cur.changes.append(_make_change(path, None, added_str, removed_str))
    if cur is not None:
        commits.append(cur)
    return commits


def _make_change(path, old_path, added_str, removed_str) -> FileChange:
    if added_str == "-" or removed_str == "-":
        return FileChange(path=path, old_path=old_path, added=None, removed=None, binary=True)
    return FileChange(path=path, old_path=old_path, added=int(added_str), removed=int(removed_str))


# --- F2: Author merging (mailmap + manual) ----------------------------


def parse_mailmap(text: str) -> dict:
    """Parse a git .mailmap file and return a mapping
    {old_identity -> canonical_identity}, where each identity is the
    standard "Name <email>" string.

    Supports the four standard .mailmap line formats:
        <new-email>
        New Name <new-email>  Old Name <old-email>
        New Name <new-email>  <old-email>
        New Name <new-email>  Old Name <old-email>
    Lines that cannot be parsed are ignored.
    """
    mapping: dict = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Find the canonical identity: the first <...> block in the line.
        first_open = line.find("<")
        first_close = line.find(">", first_open)
        if first_open < 0 or first_close < 0:
            continue
        canonical_email = line[first_open + 1 : first_close].strip()
        canonical_name = line[:first_open].strip()
        canonical_identity = (
            f"{canonical_name} <{canonical_email}>" if canonical_name else f"<{canonical_email}>"
        )
        # Everything after the canonical <email> is the old identity.
        rest = line[first_close + 1 :].strip()
        if not rest:
            continue
        if "<" in rest:
            old_name, _, old_email = rest.rpartition("<")
            old_name = old_name.strip()
            old_email = old_email.strip().rstrip(">")
            old_identity = f"{old_name} <{old_email}>" if old_name else f"<{old_email}>"
        else:
            old_identity = rest
        if old_identity and old_identity != canonical_identity:
            mapping[old_identity] = canonical_identity
    return mapping


def apply_author_merges(commits: List[Commit], mapping: dict) -> List[Commit]:
    """Return a new list of commits with each commit's author replaced
    by its canonical form under `mapping` (if present). Commits whose
    author is not in the mapping are unchanged. The original list is
    not mutated.
    """
    if not mapping:
        return commits
    out: List[Commit] = []
    for c in commits:
        new_author = mapping.get(c.author, c.author)
        out.append(
            Commit(
                sha=c.sha,
                parent=c.parent,
                committer_date=c.committer_date,
                author=new_author,
                changes=c.changes,
            )
        )
    return out
