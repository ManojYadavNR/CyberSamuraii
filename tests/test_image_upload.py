"""Tests for image upload and query detection."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from main import app
from services.image_upload import save_upload
from services.query_detector import detect_query_type


def test_detect_query_type_local_image_path(tmp_path):
    img = tmp_path / "face.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert detect_query_type(str(img)) == "image"


def test_save_upload_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_UPLOAD_DIR", str(tmp_path))
    from importlib import reload
    import services.image_upload as mod
    reload(mod)

    saved = mod.save_upload(b"\xff\xd8\xff" + b"\x00" * 64, "profile.jpg")
    assert saved["image_id"]
    assert saved["image_path"]
    assert (tmp_path / saved["stored_name"]).is_file()


def test_upload_endpoint_accepts_multipart(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_UPLOAD_DIR", str(tmp_path))
    client = TestClient(app)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    res = client.post(
        "/api/intel/image/upload",
        files={"file": ("test.png", io.BytesIO(png), "image/png")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["image_path"]
    assert data["preview_url"].startswith("/api/intel/image/uploads/")


def test_upload_endpoint_rejects_non_image():
    client = TestClient(app)
    res = client.post(
        "/api/intel/image/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert res.status_code == 400
