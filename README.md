# 2799578-SDP-Test — Repo Analysis Tool (RAT)

A web-app dashboard that computes File, Directory, Repository, Commit-set
and Author metrics (added/removed lines, growth, churn, modifications,
modification frequency, churn rate, author ownership) for a git
repository, per `TEST_SPEC.md`.

## Requirements

- Python 3.9+
- `git` available on `PATH`

No environment variables, database credentials, API keys, tokens, or
external services are required. There is nothing secret to configure.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 app.py
```

The dashboard is served at http://127.0.0.1:5000/ (set `PORT` to use a
different port). Open it in a browser and either:

- upload a `.zip` of a repository that includes its `.git` file/directory, or
- paste a public remote repository URL to be deep-cloned (e.g.
  `https://github.com/DaveGamble/cJSON.git`).

## Tests

```bash
python3 -m pytest tests/ -q
```

Tests build small, real git repositories on the fly (via the `repo`
fixture in `tests/conftest.py`) to verify the metric formulas, ingestion,
and the web routes end-to-end.

## Project layout

- `rat/gitlog.py` — parses `git log --numstat` into commit/change objects
  (non-merge commits, mailmap-resolved authors, renames, deletions, binary
  file exclusion).
- `rat/metrics.py` — File/Directory/Repository/Commit-set/Author metrics.
- `rat/ingest.py` — zip ingestion (with `.git`) and remote URL deep clone.
- `app.py` — Flask dashboard routes and templates in `templates/`.

## Current scope

This implementation covers all CORE/MUST-WORK requirements in
`TEST_SPEC.md` (ingestion via zip and remote URL, and all five metric
categories over the full non-merge history) plus all three tier-3
features from the FEATURE BACKLOG:

- **F1 — Filtering**: by repository, author, file/directory, and commit
  set (time period `[start, end)` or manually selected commits).
- **F2 — Author merging**: via `.mailmap` and manual merge UI.
- **F3 — Multi-repository support**: ingest and switch between multiple
  repositories in the dashboard.