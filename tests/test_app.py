"""End-to-end acceptance tests for the web-app dashboard (C1), wiring
ingestion (C2) through to the metrics views (C3-C8). This is the
executable check for the "runnable web-app dashboard" requirement.
"""
import io
import os
import zipfile

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
