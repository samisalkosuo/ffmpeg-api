"""Tests that do not need ffmpeg: service endpoints, upload rules, download validation, OpenAPI."""

import io

EXPECTED_PATHS = {
    "/convert/audio/to/mp3": "post",
    "/convert/audio/to/wav": "post",
    "/convert/video/to/mp4": "post",
    "/convert/image/to/jpg": "post",
    "/video/extract/audio": "post",
    "/video/extract/images": "post",
    "/video/extract/download/{filename}": "get",
    "/probe": "post",
    "/endpoints": "get",
    "/health": "get",
}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "FFMPEG API" in r.text


def test_unknown_route_returns_json_404(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json() == {"error": "route not found"}


def test_endpoints_lists_all_routes(client):
    listed = {e["path"]: e["methods"] for e in client.get("/endpoints").json()}
    for path, method in EXPECTED_PATHS.items():
        assert method.upper() in listed[path]


def test_openapi_documents_every_route(client):
    spec = client.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["license"]["name"] == "MIT"
    for path, method in EXPECTED_PATHS.items():
        op = spec["paths"][path][method]
        assert op["summary"], path
        assert op["description"], path
        assert op["operationId"], path
        assert op["tags"], path
    for path in EXPECTED_PATHS:
        if EXPECTED_PATHS[path] == "post":
            body = spec["paths"][path]["post"]["requestBody"]["content"]["multipart/form-data"]
            assert body["schema"]["properties"]["file"]["format"] == "binary"


def test_docs_do_not_use_external_urls(client):
    html = client.get("/docs").text
    assert "cdn.jsdelivr" not in html
    assert "/static/swagger/swagger-ui-bundle.js" in html


def test_non_multipart_request_is_rejected(client):
    r = client.post("/probe", content=b"abc")
    assert r.status_code == 400
    assert "multipart" in r.json()["error"]


def test_multipart_without_file_is_rejected(client):
    r = client.post("/probe", data={"name": "value"}, files={"x": ("", b"")})
    assert r.status_code == 400


def test_non_file_field_is_rejected(client):
    body = b'--B\r\nContent-Disposition: form-data; name="text"\r\n\r\nhello\r\n--B--\r\n'
    r = client.post(
        "/probe", content=body, headers={"content-type": "multipart/form-data; boundary=B"}
    )
    assert r.status_code == 400
    assert "Non-file field" in r.json()["error"]


def test_size_limit(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FILE_SIZE_LIMIT_BYTES", "1000")
    r = client.post("/probe", files={"file": ("big.bin", io.BytesIO(b"x" * 5000))})
    assert r.status_code == 413
    assert "exceeds max size limit" in r.json()["error"]
    assert list(tmp_path.iterdir()) == []  # partial upload removed


def test_download_rejects_path_traversal_and_unknown_names(client):
    assert client.get("/video/extract/download/..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/video/extract/download/passwd").status_code == 404
    assert client.get("/video/extract/download/ba0f565c-0001.png").status_code == 404


def test_download_deletes_by_default_and_keeps_with_delete_no(client, tmp_path):
    keep = tmp_path / "aaaaaaaa-0001.png"
    gone = tmp_path / "bbbbbbbb-0001.png"
    keep.write_bytes(b"png")
    gone.write_bytes(b"png")
    assert client.get("/video/extract/download/aaaaaaaa-0001.png?delete=no").status_code == 200
    assert keep.exists()
    assert client.get("/video/extract/download/bbbbbbbb-0001.png").status_code == 200
    assert not gone.exists()


def test_invalid_fps_is_422(client):
    r = client.post("/video/extract/images?fps=0", files={"file": ("a.mov", b"x")})
    assert r.status_code == 422
    assert "error" in r.json()
