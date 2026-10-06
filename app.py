"""Flask web-app dashboard for the Repo Analysis Tool (RAT) — C1.

Scope for this pass: CORE only.
- C1: a runnable web-app dashboard.
- C2: ingest a repository via zip (with .git) or a deep-cloned remote URL.
- C3-C8: file / directory / repository / commit-set / author metrics,
  computed over the full non-merge history reachable from a reference
  commit (default HEAD).

Filtering, author merging UI, and multi-repo switching are FEATURE
BACKLOG (F1-F3) and are intentionally not implemented here.
"""
import json
import os
import tempfile
import uuid

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from rat.gitlog import parse_commits
from rat.ingest import IngestError, ingest_clone, ingest_zip
from rat.metrics import author_ownership, build_object_table, commit_set_metrics

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def create_app(data_dir: str = DATA_DIR) -> Flask:
    app = Flask(__name__)
    app.secret_key = "rat-dev-secret"  # not a secret: no auth, local dev dashboard only
    app.config["DATA_DIR"] = data_dir
    os.makedirs(data_dir, exist_ok=True)

    @app.route("/")
    def index():
        return render_template("index.html", repos=_list_repos(app.config["DATA_DIR"]))

    @app.route("/ingest/zip", methods=["POST"])
    def ingest_zip_route():
        upload = request.files.get("zipfile")
        if not upload or upload.filename == "":
            return _ingest_failed("Please choose a .zip file to upload.")

        repo_id = uuid.uuid4().hex[:12]
        repo_dir = os.path.join(app.config["DATA_DIR"], repo_id)
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                upload.save(tmp.name)
                tmp_path = tmp.name
            try:
                repo_root = ingest_zip(tmp_path, repo_dir)
            finally:
                os.remove(tmp_path)
        except IngestError as exc:
            return _ingest_failed(f"Could not ingest zip: {exc}")

        _save_meta(repo_dir, {"name": upload.filename, "source": "zip", "repo_root": repo_root})
        return _ingest_succeeded(repo_id, upload.filename, "zip", f"Successfully ingested '{upload.filename}'.")

    @app.route("/ingest/clone", methods=["POST"])
    def ingest_clone_route():
        url = (request.form.get("url") or "").strip()
        if not url:
            return _ingest_failed("Please provide a repository URL to clone.")

        repo_id = uuid.uuid4().hex[:12]
        repo_dir = os.path.join(app.config["DATA_DIR"], repo_id)
        try:
            repo_root = ingest_clone(url, repo_dir)
        except IngestError as exc:
            return _ingest_failed(f"Could not clone repository: {exc}")

        _save_meta(repo_dir, {"name": url, "source": "clone", "repo_root": repo_root})
        return _ingest_succeeded(repo_id, url, "clone", f"Successfully cloned '{url}'.")

    def _is_ajax():
        return request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def _ingest_failed(message):
        if _is_ajax():
            return jsonify({"ok": False, "message": message}), 400
        flash(message)
        return redirect(url_for("index"))

    def _ingest_succeeded(repo_id, name, source, message):
        if _is_ajax():
            return jsonify(
                {
                    "ok": True,
                    "message": message,
                    "repo": {
                        "id": repo_id,
                        "name": name,
                        "source": source,
                        "url": url_for("repo_view", repo_id=repo_id),
                    },
                }
            )
        flash(message, "success")
        return redirect(url_for("repo_view", repo_id=repo_id))

    @app.route("/repo/<repo_id>")
    def repo_view(repo_id):
        repo_dir = os.path.join(app.config["DATA_DIR"], repo_id)
        meta = _load_meta(repo_dir)
        if meta is None:
            flash("Unknown repository.")
            return redirect(url_for("index"))

        ref = request.args.get("ref", "HEAD")
        try:
            commits = parse_commits(meta["repo_root"], ref=ref)
        except Exception as exc:  # pragma: no cover - defensive, surfaced to user
            flash(f"Could not read repository history: {exc}")
            return redirect(url_for("index"))

        table = build_object_table(commits)
        authors = sorted({c.author for c in commits})

        repo_metrics = commit_set_metrics(commits, "")
        file_paths = {change.path for commit in commits for change in commit.changes}
        is_dir = {path: (path == "" or path not in file_paths) for path in table}
        file_rows = [
            {"path": path, **commit_set_metrics(commits, path)}
            for path in sorted(table) if not is_dir[path]
        ]
        directory_rows = [
            {"path": path if path else "/", **commit_set_metrics(commits, path)}
            for path in sorted(table) if is_dir[path]
        ]
        author_rows = [
            {"author": a, "ownership_root": author_ownership(commits, "", a)}
            for a in authors
        ]

        return render_template(
            "repo.html",
            repo_id=repo_id,
            meta=meta,
            ref=ref,
            commit_count=len(commits),
            repo_metrics=repo_metrics,
            file_rows=file_rows,
            directory_rows=directory_rows,
            author_rows=author_rows,
        )

    @app.route("/repo/<repo_id>/commits")
    def repo_commits(repo_id):
        repo_dir = os.path.join(app.config["DATA_DIR"], repo_id)
        meta = _load_meta(repo_dir)
        if meta is None:
            flash("Unknown repository.")
            return redirect(url_for("index"))
        ref = request.args.get("ref", "HEAD")
        commits = parse_commits(meta["repo_root"], ref=ref)
        return render_template("commits.html", repo_id=repo_id, meta=meta, commits=commits)

    @app.route("/repo/<repo_id>/commit/<sha>")
    def repo_commit_detail(repo_id, sha):
        """Strict single-commit File/Directory metrics (C4/C5): added,
        removed, growth, churn for every object touched by exactly this
        commit h, relative to its parent h[p].
        """
        repo_dir = os.path.join(app.config["DATA_DIR"], repo_id)
        meta = _load_meta(repo_dir)
        if meta is None:
            flash("Unknown repository.")
            return redirect(url_for("index"))
        commits = parse_commits(meta["repo_root"])
        table = build_object_table(commits)
        rows = []
        for obj, by_sha in table.items():
            if sha in by_sha:
                added, removed = by_sha[sha]
                rows.append(
                    {
                        "path": obj if obj else "/",
                        "added": added,
                        "removed": removed,
                        "growth": added - removed,
                        "churn": added + removed,
                    }
                )
        rows.sort(key=lambda r: r["path"])
        return render_template("commit_detail.html", repo_id=repo_id, meta=meta, sha=sha, rows=rows)

    return app


def _save_meta(repo_dir, meta):
    with open(os.path.join(repo_dir, "meta.json"), "w") as fh:
        json.dump(meta, fh)


def _load_meta(repo_dir):
    meta_path = os.path.join(repo_dir, "meta.json")
    if not os.path.isfile(meta_path):
        return None
    with open(meta_path) as fh:
        return json.load(fh)


def _list_repos(data_dir):
    repos = []
    if not os.path.isdir(data_dir):
        return repos
    for repo_id in sorted(os.listdir(data_dir)):
        meta = _load_meta(os.path.join(data_dir, repo_id))
        if meta:
            repos.append({"id": repo_id, **meta})
    return repos


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
