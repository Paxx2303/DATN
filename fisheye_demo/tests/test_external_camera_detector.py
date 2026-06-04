"""
tests/test_external_camera_detector.py — Camera Discovery Tests
"""

import pytest
from unittest.mock import patch, MagicMock
from external_camera_detector import extract_camera_entries, _resolve_url


class TestResolveUrl:
    def test_absolute_url_unchanged(self):
        result = _resolve_url("http://example.com", "http://other.com/img.jpg")
        assert result == "http://other.com/img.jpg"
    
    def test_relative_url_resolved(self):
        result = _resolve_url("http://example.com/cameras/", "img.jpg")
        assert result == "http://example.com/cameras/img.jpg"
    
    def test_root_relative_resolved(self):
        result = _resolve_url("http://example.com/path/", "/snapshots/cam1.jpg")
        assert result == "http://example.com/snapshots/cam1.jpg"


class TestExtractCameraEntries:
    def test_returns_empty_list_on_network_error(self):
        import requests
        with patch("requests.get", side_effect=requests.RequestException("Network error")):
            result = extract_camera_entries("http://invalid-url.test")
            assert result == []
    
    def test_limit_respected(self):
        mock_html = """<html><body>
            <img src="cam1.jpg"><img src="cam2.jpg">
            <img src="cam3.jpg"><img src="cam4.jpg">
        </body></html>"""
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        mock_resp.raise_for_status = MagicMock()
        
        with patch("requests.get", return_value=mock_resp):
            result = extract_camera_entries("http://test.com", limit=2)
            assert len(result) <= 2
