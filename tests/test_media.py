"""Integration tests against real ffmpeg/ffprobe, using generated media."""

import io
import tarfile
import zipfile

from tests.conftest import ffprobe, upload


def probe_bytes(tmp_path, data: bytes, name: str):
    path = tmp_path / name
    path.write_bytes(data)
    return ffprobe(path)


def streams(info, kind):
    return [s for s in info["streams"] if s["codec_type"] == kind]


def test_audio_to_mp3(client, media, tmp_path):
    r = client.post("/convert/audio/to/mp3", files=upload(media["wav"]))
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert 'filename="input.mp3"' in r.headers["content-disposition"]
    info = probe_bytes(tmp_path, r.content, "out.mp3")
    assert streams(info, "audio")[0]["codec_name"] == "mp3"


def test_m4a_to_wav(client, media, tmp_path):
    r = client.post("/convert/audio/to/wav", files=upload(media["m4a"]))
    assert r.status_code == 200
    info = probe_bytes(tmp_path, r.content, "out.wav")
    assert streams(info, "audio")[0]["codec_name"] == "pcm_s16le"


def test_video_to_mp4(client, media, tmp_path):
    r = client.post("/convert/video/to/mp4", files=upload(media["video"]))
    assert r.status_code == 200
    assert r.headers["content-type"] == "video/mp4"
    info = probe_bytes(tmp_path, r.content, "out.mp4")
    video = streams(info, "video")[0]
    assert video["codec_name"] == "h264"
    assert video["height"] == 640
    assert streams(info, "audio")[0]["codec_name"] == "aac"


def test_image_to_jpg(client, media, tmp_path):
    r = client.post("/convert/image/to/jpg", files=upload(media["tiff"]))
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    info = probe_bytes(tmp_path, r.content, "out.jpg")
    assert streams(info, "video")[0]["codec_name"] == "mjpeg"


def test_extract_audio_is_mono_by_default(client, media, tmp_path):
    r = client.post("/video/extract/audio", files=upload(media["video"]))
    assert r.status_code == 200
    info = probe_bytes(tmp_path, r.content, "out.wav")
    assert streams(info, "audio")[0]["channels"] == 1


def test_extract_audio_all_channels(client, media, tmp_path):
    r = client.post("/video/extract/audio?mono=no", files=upload(media["video"]))
    assert r.status_code == 200
    info = probe_bytes(tmp_path, r.content, "out.wav")
    assert streams(info, "audio")[0]["channels"] == 2


def test_extract_images_json_and_download(client, media):
    r = client.post("/video/extract/images", files=upload(media["video"]))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"totalfiles", "description", "files"}
    assert abs(body["totalfiles"] - 3) <= 1
    assert len(body["files"]) == body["totalfiles"]
    first = body["files"][0]
    assert first["name"].endswith("-0001.png")
    assert first["url"].endswith(f"/video/extract/download/{first['name']}")
    assert first["url"].startswith("http://") and ":3000/" in first["url"]
    path = first["url"].split(":3000", 1)[1]
    d = client.get(path)
    assert d.status_code == 200
    assert d.headers["content-type"] == "image/png"
    assert client.get(path).status_code == 404  # deleted after first download


def test_extract_images_fps(client, media):
    body = client.post("/video/extract/images?fps=4", files=upload(media["video"])).json()
    assert abs(body["totalfiles"] - 12) <= 2


def test_extract_images_zip(client, media):
    r = client.post("/video/extract/images?compress=zip", files=upload(media["video"]))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert abs(len(names) - 3) <= 1
    assert all(n.endswith(".png") for n in names)


def test_extract_images_gzip(client, media):
    r = client.post("/video/extract/images?compress=gzip", files=upload(media["video"]))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/gzip"
    names = tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz").getnames()
    assert abs(len(names) - 3) <= 1


def test_probe(client, media):
    r = client.post("/probe", files=upload(media["video"]))
    assert r.status_code == 200
    info = r.json()
    assert set(info) >= {"streams", "format", "chapters"}
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio"}
    assert info["format"]["format_name"].startswith("mov")


def test_invalid_media_returns_500_json(client, media):
    r = client.post("/convert/audio/to/mp3", files=upload(media["invalid"]))
    assert r.status_code == 500
    assert "error" in r.json()


def test_temp_files_are_cleaned_up(client, media, tmp_path):
    client.post("/convert/audio/to/mp3", files=upload(media["wav"]))
    client.post("/convert/audio/to/mp3", files=upload(media["invalid"]))
    client.post("/probe", files=upload(media["video"]))
    assert list(tmp_path.iterdir()) == []


def test_keep_all_files(client, media, tmp_path, monkeypatch):
    monkeypatch.setenv("KEEP_ALL_FILES", "true")
    client.post("/probe", files=upload(media["wav"]))
    assert len(list(tmp_path.iterdir())) == 1
