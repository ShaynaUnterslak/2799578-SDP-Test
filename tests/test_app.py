"""End-to-end acceptance tests for the web-app dashboard (C1), wiring
ingestion (C2) through to the metrics views (C3-C8). This is the
executable check for the "runnable web-app dashboard" requirement.
"""
import io
import os
import zipfile

import app as app_module
import rat.metrics as metrics_module
from app import create_app


def _client(tmp_path):
    app = create_app(data_dir=str(tmp_path / "data"))
    app.testing = True
    return app.test_client()


def test_index_page_loads(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Repo Analysis Tool" in resp.data


def test_ingest_clone_then_view_dashboard(repo, tmp_path):
    repo.write("a.txt", "line1\nline2\n")
    repo.commit("init", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    repo.write("a.txt", "line1\nline2\nline3\n")
    repo.commit("edit", timestamp=1001, author_name="Bob", author_email="bob@example.com")

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"a.txt" in resp.data
    assert b"Alice" in resp.data
    assert b"Bob" in resp.data
    # The marker/user must get explicit, visible confirmation that
    # ingestion succeeded (not just a silent page change).
    assert b"ngested" in resp.data or b"successfully" in resp.data.lower()


def test_ingest_clone_invalid_url_shows_error_and_does_not_hang(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/ingest/clone",
        data={"url": "https://example.invalid/does-not-exist.git"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Could not clone repository" in resp.data


def test_ingest_zip_then_view_dashboard(repo, tmp_path):
    repo.write("a.txt", "line1\n")
    repo.commit("init", timestamp=1000)
    zip_path = tmp_path / "repo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, _dirs, files in os.walk(repo.path):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, os.path.dirname(repo.path))
                zf.write(full, rel)

    client = _client(tmp_path)
    with open(zip_path, "rb") as fh:
        data = {"zipfile": (io.BytesIO(fh.read()), "repo.zip")}
        resp = client.post("/ingest/zip", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    assert b"a.txt" in resp.data
    assert b"ngested" in resp.data or b"successfully" in resp.data.lower()


def test_ingest_without_input_shows_error_not_crash(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": ""}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"provide a repository URL" in resp.data


def _ajax_headers():
    return {"X-Requested-With": "XMLHttpRequest"}


def test_ajax_clone_success_returns_json_not_redirect(repo, tmp_path):
    repo.write("a.txt", "line1\n")
    repo.commit("init", timestamp=1000)

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, headers=_ajax_headers())

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "successfully" in body["message"].lower()
    assert body["repo"]["source"] == "clone"
    assert body["repo"]["name"] == repo.path
    assert "id" in body["repo"]
    assert body["repo"]["url"].startswith("/repo/")


def test_ajax_clone_error_returns_json_with_400(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/ingest/clone",
        data={"url": "https://example.invalid/does-not-exist.git"},
        headers=_ajax_headers(),
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False
    assert "Could not clone repository" in body["message"]


def test_ajax_zip_success_returns_json_not_redirect(repo, tmp_path):
    repo.write("a.txt", "line1\n")
    repo.commit("init", timestamp=1000)
    zip_path = tmp_path / "repo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, _dirs, files in os.walk(repo.path):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, os.path.dirname(repo.path))
                zf.write(full, rel)

    client = _client(tmp_path)
    with open(zip_path, "rb") as fh:
        data = {"zipfile": (io.BytesIO(fh.read()), "repo.zip")}
        resp = client.post(
            "/ingest/zip",
            data=data,
            content_type="multipart/form-data",
            headers=_ajax_headers(),
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["repo"]["source"] == "zip"
    assert body["repo"]["name"] == "repo.zip"


def test_ajax_zip_error_returns_json_with_400(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/ingest/zip", data={}, content_type="multipart/form-data", headers=_ajax_headers())

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False
    assert "choose a .zip file" in body["message"]


def test_index_lists_newly_ingested_repo_without_navigating_away(repo, tmp_path):
    """After an AJAX ingest, GET / must already include the new repo
    (so the client-side list update reflects real server state).
    """
    repo.write("a.txt", "line1\n")
    repo.commit("init", timestamp=1000)

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, headers=_ajax_headers())
    repo_id = resp.get_json()["repo"]["id"]

    index_resp = client.get("/")
    assert f"/repo/{repo_id}".encode() in index_resp.data


# --- F5: Usability (navigation, error handling, performance) ----------


def _ingest_repo_with_several_files_and_authors(repo, tmp_path):
    repo.write("a.txt", "l1\n")
    repo.commit("a init", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    repo.write("dir/b.txt", "l1\n")
    repo.commit("b init", timestamp=1001, author_name="Bob", author_email="bob@example.com")
    repo.write("dir/c.txt", "l1\n")
    repo.commit("c init", timestamp=1002, author_name="Alice", author_email="alice@example.com")

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, headers=_ajax_headers())
    repo_id = resp.get_json()["repo"]["id"]
    return client, repo_id


def test_repo_dashboard_builds_object_table_only_once_per_request(repo, tmp_path, monkeypatch):
    """F5 performance (Done when: medium repos perform well): the dashboard
    renders a metrics row per file, per directory, and per author. It must
    build the (object, commit) table ONCE and reuse it for every row,
    not rebuild it from scratch on every single row -- otherwise a
    medium-sized repo (~10000 commits) becomes unusably slow.
    """
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)

    calls = []
    real_build = metrics_module.build_object_table

    def counting_build(commits):
        calls.append(1)
        return real_build(commits)

    monkeypatch.setattr(metrics_module, "build_object_table", counting_build)
    monkeypatch.setattr(app_module, "build_object_table", counting_build)

    resp = client.get(f"/repo/{repo_id}")
    assert resp.status_code == 200
    # There are 3 files, directories (dir, root) and 2 authors in this
    # fixture -- a per-row rebuild would call this many times over.
    assert len(calls) == 1


# --- F4: Efficient architecture and visualisation --------------------


def test_repo_dashboard_aggregates_all_author_metrics_once(repo, tmp_path, monkeypatch):
    """F4 Done-when: one bulk aggregation supplies all author rows instead
    of rescanning the same root deltas for each metric and author.
    """
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    calls = []
    real_aggregate = metrics_module.author_metrics

    def counting_aggregate(*args, **kwargs):
        calls.append(1)
        return real_aggregate(*args, **kwargs)

    monkeypatch.setattr(app_module, "author_metrics", counting_aggregate)
    response = client.get(f"/repo/{repo_id}")

    assert response.status_code == 200
    assert calls == [1]
    assert b"Alice" in response.data and b"Bob" in response.data


def test_repo_dashboard_visualises_churn_and_author_ownership(repo, tmp_path):
    """F4 Done-when: key comparative metrics have clear, accessible visual
    encodings in addition to their exact numeric values.
    """
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    response = client.get(f"/repo/{repo_id}")

    assert response.status_code == 200
    assert b'<progress class="metric-bar churn-bar"' in response.data
    assert b'aria-label="Directory churn 3"' in response.data
    assert b'aria-label="File churn 1"' in response.data
    assert b'<progress class="metric-bar ownership-bar"' in response.data
    assert b'aria-label="Author ownership 66.7%"' in response.data


def test_repo_commits_route_handles_history_read_error_gracefully(repo, tmp_path, monkeypatch):
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("corrupt repository")

    monkeypatch.setattr(app_module, "parse_commits", boom)
    resp = client.get(f"/repo/{repo_id}/commits", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Could not read repository history" in resp.data


def test_repo_commit_detail_route_handles_history_read_error_gracefully(repo, tmp_path, monkeypatch):
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("corrupt repository")

    monkeypatch.setattr(app_module, "parse_commits", boom)
    resp = client.get(f"/repo/{repo_id}/commit/deadbeef", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Could not read repository history" in resp.data


def test_repo_commit_detail_route_handles_unknown_sha_gracefully(repo, tmp_path):
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    resp = client.get(f"/repo/{repo_id}/commit/deadbeef", follow_redirects=True)
    assert resp.status_code == 200
    assert b"No metrics found" in resp.data


def test_unknown_route_shows_friendly_404_not_a_traceback(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/this-page-does-not-exist")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data


def test_repo_dashboard_page_has_home_navigation_link(repo, tmp_path):
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    resp = client.get(f"/repo/{repo_id}")
    assert b'href="/"' in resp.data


def test_commits_page_has_home_navigation_link(repo, tmp_path):
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    resp = client.get(f"/repo/{repo_id}/commits")
    assert b'href="/"' in resp.data


def test_commit_detail_page_has_home_navigation_link(repo, tmp_path):
    client, repo_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    commits_resp = client.get(f"/repo/{repo_id}/commits")
    assert b'href="/"' in commits_resp.data

    detail_resp = client.get(f"/repo/{repo_id}/commit/deadbeef")
    assert b'href="/"' in detail_resp.data


# --- F3: Multiple Repository Support -----------------------------------


def _make_second_repo(tmp_path):
    """Build a second, distinct local git repo so we can ingest it
    alongside the first and prove the dashboard supports multiple
    repositories simultaneously (F3 Done-when).
    """
    from conftest import RepoBuilder

    second = RepoBuilder(tmp_path / "second_repo")
    second.write("other.txt", "x\ny\nz\n")
    second.commit("init-second", timestamp=2000, author_name="Carol", author_email="carol@example.com")
    return second


def test_index_lists_both_ingested_repos(repo, tmp_path):
    """F3 Done-when (part 1): two repositories can be ingested and both
    are listed on the dashboard index.
    """
    client, first_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    second = _make_second_repo(tmp_path)
    resp = client.post("/ingest/clone", data={"url": second.path}, headers=_ajax_headers())
    second_id = resp.get_json()["repo"]["id"]

    index_resp = client.get("/")
    assert first_id.encode() in index_resp.data
    assert second_id.encode() in index_resp.data


def test_each_repo_dashboard_shows_only_its_own_metrics(repo, tmp_path):
    """F3 Done-when (part 2): each repository is independently
    analysable -- repo A's dashboard shows only repo A's files/authors,
    repo B's shows only repo B's.
    """
    client, first_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    second = _make_second_repo(tmp_path)
    resp = client.post("/ingest/clone", data={"url": second.path}, headers=_ajax_headers())
    second_id = resp.get_json()["repo"]["id"]

    first_dash = client.get(f"/repo/{first_id}")
    second_dash = client.get(f"/repo/{second_id}")

    # repo A has a.txt/dir/b.txt/dir/c.txt and authors Alice/Bob --
    # repo B has only other.txt and author Carol. These must not leak.
    assert b"a.txt" in first_dash.data
    assert b"Alice" in first_dash.data
    assert b"other.txt" not in first_dash.data
    assert b"Carol" not in first_dash.data

    assert b"other.txt" in second_dash.data
    assert b"Carol" in second_dash.data
    assert b"a.txt" not in second_dash.data
    assert b"Alice" not in second_dash.data


def test_repo_dashboard_has_a_repository_switcher(repo, tmp_path):
    """F3 Done-when (part 3): the dashboard is *switchable* -- from
    within a repo's dashboard the user can see and navigate to the
    other ingested repositories without going back to the index.
    """
    client, first_id = _ingest_repo_with_several_files_and_authors(repo, tmp_path)
    second = _make_second_repo(tmp_path)
    resp = client.post("/ingest/clone", data={"url": second.path}, headers=_ajax_headers())
    second_id = resp.get_json()["repo"]["id"]

    first_dash = client.get(f"/repo/{first_id}")
    # The switcher must expose a link to the OTHER repo on this page.
    assert f"/repo/{second_id}".encode() in first_dash.data
    # And a visible affordance so the marker/user recognises it.
    assert b"Switch repository" in first_dash.data or b"switch" in first_dash.data.lower()

    second_dash = client.get(f"/repo/{second_id}")
    assert f"/repo/{first_id}".encode() in second_dash.data


# --- F2: Author Merging ----------------------------------------------


def test_dashboard_applies_mailmap_when_present(repo, tmp_path):
    """F2 Done-when (part 1): a .mailmap file in the repo merges
    different identities into a single author on the dashboard.
    """
    repo.write("a.txt", "l1\n")
    repo.commit("c1", timestamp=1000, author_name="Old", author_email="old@example.com")
    repo.write_mailmap("Real Name <real@example.com> Old <old@example.com>\n")
    repo.write("b.txt", "l1\n")
    repo.commit("c2", timestamp=2000, author_name="Old", author_email="old@example.com")

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, headers=_ajax_headers())
    repo_id = resp.get_json()["repo"]["id"]

    dash = client.get(f"/repo/{repo_id}")
    # Jinja2 escapes `<`/`>` in HTML, so check the name portion only.
    assert b"Real Name" in dash.data
    # "Old" as an author must not appear -- only "Real Name" should.
    assert b"Old &lt;old@example.com&gt;" not in dash.data
    # Confirm the canonical author shows up in the author-ownership table.
    assert b"1.000" in dash.data


def test_manual_merge_without_mailmap(repo, tmp_path):
    """F2 Done-when (part 2): manual merging works even with no
    .mailmap present -- the user can merge different authors through
    the dashboard and the merged identity is reported.
    """
    repo.write("a.txt", "l1\n")
    repo.commit("c1", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    repo.write("a.txt", "l1\nl2\n")
    repo.commit("c2", timestamp=2000, author_name="Bob", author_email="bob@example.com")

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, headers=_ajax_headers())
    repo_id = resp.get_json()["repo"]["id"]

    # Pre-merge: both authors appear.
    pre = client.get(f"/repo/{repo_id}")
    assert b"Alice" in pre.data
    assert b"Bob" in pre.data

    # Manual merge: Bob -> Alice.
    merge_resp = client.post(
        f"/repo/{repo_id}/merges",
        data={"alias_0": "Bob <bob@example.com>", "to_0": "Alice <alice@example.com>"},
        follow_redirects=True,
    )
    assert b"Alice" in merge_resp.data
    # Bob must no longer appear as a distinct author in the ownership
    # table (the merge form's dropdown still lists him as a selectable
    # option, so we scope the check to the ownership table region only).
    between = merge_resp.data.split(b"Author metrics", 1)[1].split(b"Merge authors", 1)[0]
    assert b"Bob" not in between


def test_manual_merge_updates_author_ownership(repo, tmp_path):
    """F2 constraint: merging changes h[a] and therefore author metrics
    (ownership, churn, modifications). After merging Bob into Alice,
    Alice owns 100% of root churn.
    """
    repo.write("a.txt", "l1\n")
    repo.commit("c1", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    repo.write("a.txt", "l1\nl2\n")
    repo.commit("c2", timestamp=2000, author_name="Bob", author_email="bob@example.com")

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, headers=_ajax_headers())
    repo_id = resp.get_json()["repo"]["id"]

    client.post(
        f"/repo/{repo_id}/merges",
        data={"alias_0": "Bob <bob@example.com>", "to_0": "Alice <alice@example.com>"},
        follow_redirects=True,
    )
    post = client.get(f"/repo/{repo_id}")
    # Alice now owns 100% of root churn (was 50% pre-merge).
    assert b"Alice" in post.data
    assert b"1.000" in post.data  # ownership = 1.000


def test_manual_merge_does_not_affect_non_author_metrics(repo, tmp_path):
    """F2 constraint: non-author metrics are unaffected by merging.
    """
    repo.write("a.txt", "l1\nl2\n")
    repo.commit("c1", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    repo.write("a.txt", "l1\nl2\nl3\n")
    repo.commit("c2", timestamp=2000, author_name="Bob", author_email="bob@example.com")

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, headers=_ajax_headers())
    repo_id = resp.get_json()["repo"]["id"]

    pre = client.get(f"/repo/{repo_id}")
    # Root churn = 3 (2 added in c1, 1 added in c2).
    assert b">3</b>" in pre.data

    client.post(
        f"/repo/{repo_id}/merges",
        data={"alias_0": "Bob <bob@example.com>", "to_0": "Alice <alice@example.com>"},
        follow_redirects=True,
    )
    post = client.get(f"/repo/{repo_id}")
    # Root churn is unchanged.
    assert b">3</b>" in post.data


# --- F1: Filtering ----------------------------------------------------


def _ingest_repo_for_filtering(repo, tmp_path):
    repo.write("src/a.txt", "a1\na2\n")
    first = repo.commit("first", timestamp=1000, author_name="Alice", author_email="alice@example.com")
    repo.write("src/a.txt", "a1\na2\na3\n")
    repo.write("docs/readme.txt", "d1\nd2\nd3\nd4\n")
    repo.commit("second", timestamp=2000, author_name="Bob", author_email="bob@example.com")
    repo.write("src/a.txt", "a1\na2\na3\na4\n")
    repo.write("src/b.txt", "b1\n")
    third = repo.commit("third", timestamp=3000, author_name="Alice", author_email="alice@example.com")

    client = _client(tmp_path)
    resp = client.post("/ingest/clone", data={"url": repo.path}, headers=_ajax_headers())
    return client, resp.get_json()["repo"]["id"], first, third


def _metric_sections(response):
    body = response.data
    return {
        "repository": body.split(b'<div class="summary">', 1)[1].split(b"</div>", 1)[0],
        "directories": body.split(b"Directory metrics", 1)[1].split(b"File metrics", 1)[0],
        "files": body.split(b"File metrics", 1)[1].split(b"Author metrics", 1)[0],
        "authors": body.split(b"Author metrics", 1)[1].split(b"Merge authors", 1)[0],
    }


def test_dashboard_combines_repository_author_object_and_period_filters(repo, tmp_path):
    """F1 Done-when: repository, author, object, and half-open
    committer-date filters all apply to every displayed metric category.
    """
    client, repo_id, _first, _third = _ingest_repo_for_filtering(repo, tmp_path)

    response = client.get(
        f"/repo/{repo_id}",
        query_string={
            "author": "Alice <alice@example.com>",
            "path": "src",
            "commit_mode": "period",
            "start": "1000",
            "end": "3000",
        },
    )

    assert response.status_code == 200
    assert b"Showing 1 of 3 commits" in response.data
    assert b'name="author"' in response.data
    assert b'name="path"' in response.data
    assert b'name="start"' in response.data
    assert b'name="end"' in response.data
    sections = _metric_sections(response)
    assert b'>2</b><span class="label">Added lines' in sections["repository"]
    assert b"src" in sections["directories"] and b"docs" not in sections["directories"]
    assert b"src/a.txt" in sections["files"]
    assert b"src/b.txt" not in sections["files"] and b"docs/readme.txt" not in sections["files"]
    assert b"Alice" in sections["authors"] and b"Bob" not in sections["authors"]
    assert b"<td>1</td><td>2</td><td>1.000</td>" in sections["authors"]


def test_dashboard_manual_commit_filter_accepts_an_arbitrary_commit_list(repo, tmp_path):
    """F1 constraint and Done-when: an arbitrary H subset can be selected,
    and commit-set plus author metrics use exactly that manual list.
    """
    client, repo_id, first, third = _ingest_repo_for_filtering(repo, tmp_path)

    response = client.get(
        f"/repo/{repo_id}",
        query_string=[
            ("path", "src/a.txt"),
            ("commit_mode", "manual"),
            ("commit", first),
            ("commit", third),
        ],
    )

    assert response.status_code == 200
    assert b"Showing 2 of 3 commits" in response.data
    assert response.data.count(b'name="commit"') >= 3
    sections = _metric_sections(response)
    assert b'>3</b><span class="label">Added lines' in sections["repository"]
    assert b"src" in sections["directories"] and b"docs" not in sections["directories"]
    assert b"src/a.txt" in sections["files"]
    assert b"src/b.txt" not in sections["files"] and b"docs/readme.txt" not in sections["files"]
    assert b"Alice" in sections["authors"] and b"Bob" not in sections["authors"]
    assert b"<td>2</td><td>3</td><td>1.000</td>" in sections["authors"]
