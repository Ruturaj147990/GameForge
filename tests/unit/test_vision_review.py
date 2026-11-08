"""Unit tests for vision_review explicit validation and error handling."""

from pathlib import Path
from unittest.mock import MagicMock
from src.gameforge_ide.pipeline.vision_review import review_screenshot


def test_review_screenshot_missing_or_empty_response(monkeypatch, tmp_path):
    dummy_img = tmp_path / "test.png"
    dummy_img.write_bytes(b"fake image bytes")

    mock_prov = MagicMock()
    mock_prov.chat_with_tools.return_value = {"content": ""}
    monkeypatch.setattr("src.gameforge_ide.pipeline.vision_review.OllamaProvider", lambda *args, **kwargs: mock_prov)

    res = review_screenshot(dummy_img, "request", "design", "facts")
    assert res["available"] is False
    assert res["matches_request"] is False


def test_review_screenshot_unparseable_content(monkeypatch, tmp_path):
    dummy_img = tmp_path / "test.png"
    dummy_img.write_bytes(b"fake image bytes")

    mock_prov = MagicMock()
    mock_prov.chat_with_tools.return_value = {"content": "not json at all"}
    monkeypatch.setattr("src.gameforge_ide.pipeline.vision_review.OllamaProvider", lambda *args, **kwargs: mock_prov)

    res = review_screenshot(dummy_img, "request", "design", "facts")
    assert res["available"] is False
    assert res["matches_request"] is False


def test_review_screenshot_missing_matches_request_key(monkeypatch, tmp_path):
    dummy_img = tmp_path / "test.png"
    dummy_img.write_bytes(b"fake image bytes")

    mock_prov = MagicMock()
    mock_prov.chat_with_tools.return_value = {"content": '{"problems": ["blurry"], "suggestions": ["sharpen"]}'}
    monkeypatch.setattr("src.gameforge_ide.pipeline.vision_review.OllamaProvider", lambda *args, **kwargs: mock_prov)

    res = review_screenshot(dummy_img, "request", "design", "facts")
    assert res["available"] is True
    # Must NOT default to True when key is absent
    assert res["matches_request"] is False
    assert res["problems"] == ["blurry"]


def test_review_screenshot_explicit_true(monkeypatch, tmp_path):
    dummy_img = tmp_path / "test.png"
    dummy_img.write_bytes(b"fake image bytes")

    mock_prov = MagicMock()
    mock_prov.chat_with_tools.return_value = {"content": '{"matches_request": true, "problems": []}'}
    monkeypatch.setattr("src.gameforge_ide.pipeline.vision_review.OllamaProvider", lambda *args, **kwargs: mock_prov)

    res = review_screenshot(dummy_img, "request", "design", "facts")
    assert res["available"] is True
    assert res["matches_request"] is True


def test_review_screenshot_explicit_false(monkeypatch, tmp_path):
    dummy_img = tmp_path / "test.png"
    dummy_img.write_bytes(b"fake image bytes")

    mock_prov = MagicMock()
    mock_prov.chat_with_tools.return_value = {"content": '{"matches_request": false, "problems": ["wrong scene"]}'}
    monkeypatch.setattr("src.gameforge_ide.pipeline.vision_review.OllamaProvider", lambda *args, **kwargs: mock_prov)

    res = review_screenshot(dummy_img, "request", "design", "facts")
    assert res["available"] is True
    assert res["matches_request"] is False


def test_review_screenshot_nonexistent_image(tmp_path):
    missing_img = tmp_path / "does_not_exist.png"
    res = review_screenshot(missing_img, "request", "design", "facts")
    assert res["available"] is False
    assert res["matches_request"] is False
    assert "not found or empty" in res["error"]


def test_review_screenshot_non_vision_model_blocked(tmp_path):
    dummy_img = tmp_path / "test.png"
    dummy_img.write_bytes(b"fake image bytes")
    # llama3.1:8b is registered in CapabilityRegistry with supports_images=False
    res = review_screenshot(dummy_img, "request", "design", "facts", model="llama3.1:8b")
    assert res["available"] is False
    assert res["matches_request"] is False
    assert "does not support images/vision" in res["error"]
