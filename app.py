"""Flask web-app dashboard for the Repo Analysis Tool (RAT).

The dashboard implements C1-C8 plus repository, author, object, commit-set,
author-merging, multi-repository, and usability features from TEST_SPEC.md.
"""
import json
import os
import tempfile
import uuid
from dataclasses import replace

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from rat.gitlog import apply_author_merges, parse_commits
from rat.ingest import IngestError, ingest_clone, ingest_zip
from rat.metrics import H_ij, H_t, author_metrics, build_object_table, commit_set_metrics

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

        # F2: apply author merges (mailmap + manual) so h[a] and all
        # author metrics reflect the merged identities.
        all_commits = apply_author_merges(commits, _effective_author_mapping(meta))
        all_authors = sorted({c.author for c in all_commits})
        object_options = _dashboard_object_options(all_commits)

        # F1: form one active H by combining the commit, author, and object
        # dimensions. The repository dimension is the selected repo_id.
        commit_mode = request.args.get("commit_mode", "all")
        start = _optional_timestamp(request.args.get("start"))
        end = _optional_timestamp(request.args.get("end"))
        selected_commits = request.args.getlist("commit")
        commits = list(all_commits)
        if commit_mode == "period":
            if start is not None and end is not None:
                commits = H_ij(commits, start, end)
            elif start is not None:
                commits = H_t(commits, start)
            elif end is not None:
                commits = [c for c in commits if c.committer_date < end]
        elif commit_mode == "manual":
            selected_shas = set(selected_commits)
            commits = [c for c in commits if c.sha in selected_shas]
        else:
            commit_mode = "all"

        selected_author = request.args.get("author", "")
        if selected_author in all_authors:
            commits = [c for c in commits if c.author == selected_author]
        else:
            selected_author = ""

        option_by_path = {option["path"]: option for option in object_options}
        selected_path = request.args.get("path", "")
        if selected_path in option_by_path:
            commits = _scope_commits_to_object(
                commits,
                selected_path,
                option_by_path[selected_path]["kind"],
            )
        else:
            selected_path = ""

        # Build the active (object, commit) table ONCE per request and reuse
        # it for every file/directory/author row (F5 performance).
        table = build_object_table(commits)
        by_sha = {c.sha: c for c in commits}

        repo_metrics = commit_set_metrics(commits, "", table=table, by_sha=by_sha)
        file_paths = {change.path for commit in commits for change in commit.changes}
        is_dir = {path: (path == "" or path not in file_paths) for path in table}
        file_rows = [
            {"path": path, **commit_set_metrics(commits, path, table=table, by_sha=by_sha)}
            for path in sorted(table) if not is_dir[path]
        ]
        directory_rows = [
            {"path": path if path else "/", **commit_set_metrics(commits, path, table=table, by_sha=by_sha)}
            for path in sorted(table) if is_dir[path]
        ]
        author_rows = author_metrics(commits, "", table=table, by_sha=by_sha)
        max_directory_churn = max((row["churn"] for row in directory_rows), default=0)
        max_file_churn = max((row["churn"] for row in file_rows), default=0)

        return render_template(
            "repo.html",
            repo_id=repo_id,
            meta=meta,
            ref=ref,
            commit_count=len(commits),
            total_commit_count=len(all_commits),
            repo_metrics=repo_metrics,
            file_rows=file_rows,
            directory_rows=directory_rows,
            author_rows=author_rows,
            max_directory_churn=max_directory_churn,
            max_file_churn=max_file_churn,
            all_repos=_list_repos(app.config["DATA_DIR"]),
            all_authors=all_authors,
            object_options=object_options,
            available_commits=all_commits,
            filters={
                "author": selected_author,
                "path": selected_path,
                "commit_mode": commit_mode,
                "start": "" if start is None else start,
                "end": "" if end is None else end,
                "commits": selected_commits,
            },
            merge_info=_merge_info_for_template(all_commits, meta.get("author_merges", {})),
        )

    @app.route("/repo/<repo_id>/commits")
    def repo_commits(repo_id):
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
            return redirect(url_for("repo_view", repo_id=repo_id))
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
        try:
            commits = parse_commits(meta["repo_root"])
        except Exception as exc:  # pragma: no cover - defensive, surfaced to user
            flash(f"Could not read repository history: {exc}")
            return redirect(url_for("repo_commits", repo_id=repo_id))
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

    @app.route("/repo/<repo_id>/merges", methods=["POST"])
    def repo_merges_manage(repo_id):
        """Save manual author merges for this repo. Form data is a list
        of (alias_N, to_N) pairs; empty pairs are ignored.
        """
        repo_dir = os.path.join(app.config["DATA_DIR"], repo_id)
        meta = _load_meta(repo_dir)
        if meta is None:
            flash("Unknown repository.")
            return redirect(url_for("index"))
        merges: dict = {}
        i = 0
        while True:
            alias = (request.form.get(f"alias_{i}") or "").strip()
            target = (request.form.get(f"to_{i}") or "").strip()
            if not alias and not target:
                # Past the last populated row -- stop.
                if not any(
                    request.form.get(f"alias_{j}") or request.form.get(f"to_{j}")
                    for j in range(i + 1, i + 50)
                ):
                    break
                i += 1
                continue
            if alias and target and alias != target:
                merges[alias] = target
            i += 1
        meta["author_merges"] = merges
        _save_meta(repo_dir, meta)
        flash(f"Saved {len(merges)} author merge rule(s).", "success")
        return redirect(url_for("repo_view", repo_id=repo_id))

    @app.errorhandler(404)
    def not_found(_exc):
        return render_template("404.html"), 404

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


def _optional_timestamp(value):
    """Parse an optional Unix committer timestamp; invalid input is unset."""
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _dashboard_object_options(commits):
    """Return measurable file and directory paths available to F1."""
    files = {
        change.path
        for commit in commits
        for change in commit.changes
        if not change.binary
    }
    directories = set()
    for path in files:
        parts = path.split("/")
        directories.update("/".join(parts[:i]) for i in range(1, len(parts)))
    return [
        *({"path": path, "label": f"{path}/", "kind": "directory"} for path in sorted(directories)),
        *({"path": path, "label": path, "kind": "file"} for path in sorted(files)),
    ]


def _scope_commits_to_object(commits, path, kind):
    """Limit each commit's changes to one object without changing H.

    Keeping commits with no matching change preserves the C7 denominator
    |H| for modification frequency and churn rate.
    """
    prefix = f"{path}/"
    return [
        replace(
            commit,
            changes=[
                change
                for change in commit.changes
                if not change.binary
                and (change.path == path if kind == "file" else change.path.startswith(prefix))
            ],
        )
        for commit in commits
    ]


def _effective_author_mapping(meta: dict) -> dict:
    """Return the manual author-merge mapping stored for this repo.

    Note: .mailmap is already honoured by git itself during `git log`
    (we use %aN/%aE, which resolve via .mailmap automatically), so the
    commits returned by parse_commits already reflect mailmap merges.
    We only need to layer the user's *manual* merges on top here.
    """
    return dict(meta.get("author_merges") or {})


def _merge_info_for_template(commits, manual_merges: dict) -> dict:
    """Compute the data needed by the merge-management UI: the list of
    distinct authors currently visible, which are canonical (i.e. are
    the target of at least one merge) and which are aliases.
    """
    authors = sorted({c.author for c in commits})
    canonical = set(manual_merges.values())
    aliases = set(manual_merges.keys())
    return {
        "authors": authors,
        "canonical": sorted(canonical),
        "aliases": sorted(aliases),
        "manual": manual_merges,
    }


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
