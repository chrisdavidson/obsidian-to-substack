"""Tests for Datawrapper API client (mocked, no real API calls)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obsidian_to_substack.datawrapper import (
    create_chart,
    export_chart_png,
    publish_chart,
    publish_table,
    upload_data,
)
from obsidian_to_substack.table_handler import (
    extract_tables,
    replace_tables_with_embeds,
)


def _mock_urlopen(response_data: dict | None, status: int = 200):
    """Create a mock for urllib.request.urlopen."""
    mock_response = MagicMock()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    body = json.dumps(response_data).encode("utf-8") if response_data else b""
    mock_response.read.return_value = body
    mock_response.status = status
    return mock_response


class TestCreateChart:
    @patch("obsidian_to_substack.datawrapper.urllib.request.urlopen")
    def test_returns_chart_id(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"id": "aBcDe"})
        chart_id = create_chart("Test Table", "fake-token")
        assert chart_id == "aBcDe"

    @patch("obsidian_to_substack.datawrapper.urllib.request.urlopen")
    def test_sends_correct_payload(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"id": "xyz"})
        create_chart("My Title", "fake-token")
        call_args = mock_urlopen.call_args[0][0]
        body = json.loads(call_args.data.decode("utf-8"))
        assert body["title"] == "My Title"
        assert body["type"] == "tables"


class TestUploadData:
    @patch("obsidian_to_substack.datawrapper.urllib.request.urlopen")
    def test_sends_csv_data(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(None)
        upload_data("aBcDe", "col1,col2\na,b\n", "fake-token")
        call_args = mock_urlopen.call_args[0][0]
        assert call_args.data == b"col1,col2\na,b\n"
        assert call_args.get_header("Content-type") == "text/csv"


class TestPublishChart:
    @patch("obsidian_to_substack.datawrapper.urllib.request.urlopen")
    def test_returns_public_url_dict_format(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "data": {"publicUrl": "https://datawrapper.dwcdn.net/aBcDe/1/"},
        })
        url = publish_chart("aBcDe", "fake-token")
        assert url == "https://datawrapper.dwcdn.net/aBcDe/1/"

    @patch("obsidian_to_substack.datawrapper.urllib.request.urlopen")
    def test_returns_public_url_list_format(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({
            "data": [{"publicUrl": "https://datawrapper.dwcdn.net/aBcDe/1/"}],
        })
        url = publish_chart("aBcDe", "fake-token")
        assert url == "https://datawrapper.dwcdn.net/aBcDe/1/"


class TestExportChartPng:
    @patch("obsidian_to_substack.datawrapper.urllib.request.urlopen")
    def test_returns_png_bytes(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"\x89PNG\r\n\x1a\nfakedata"
        mock_urlopen.return_value = mock_response

        result = export_chart_png("aBcDe", "fake-token")
        assert result == b"\x89PNG\r\n\x1a\nfakedata"

        call_args = mock_urlopen.call_args[0][0]
        assert "/charts/aBcDe/export/png" in call_args.full_url
        assert call_args.get_header("Accept") == "image/png"


class TestPublishTable:
    @patch("obsidian_to_substack.datawrapper.urllib.request.urlopen")
    def test_full_flow(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock_urlopen({"id": "tbl1"}),
            _mock_urlopen(None),
            _mock_urlopen({
                "data": {"publicUrl": "https://datawrapper.dwcdn.net/tbl1/1/"},
            }),
        ]
        url, chart_id = publish_table("A,B\n1,2\n", "Test", "fake-token")
        assert url == "https://datawrapper.dwcdn.net/tbl1/1/"
        assert chart_id == "tbl1"
        assert mock_urlopen.call_count == 3


FAKE_PNG = b"\x89PNG\r\n\x1a\nfake"


class TestReplaceTablesWithEmbeds:
    @patch("obsidian_to_substack.datawrapper.export_chart_png", return_value=FAKE_PNG)
    @patch("obsidian_to_substack.datawrapper.publish_table")
    def test_replaces_table_with_img_tag(self, mock_publish, mock_export):
        mock_publish.return_value = ("https://datawrapper.dwcdn.net/xyz/1/", "xyz")
        text = "Before\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nAfter"
        tables = extract_tables(text)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = replace_tables_with_embeds(
                text, tables, tmpdir,
                api_token="fake",
                article_title="Test Article",
            )
            assert '<img src="table-1.png"' in result
            assert "<!-- Datawrapper: https://datawrapper.dwcdn.net/xyz/1/ -->" in result
            assert "| A |" not in result
            assert "Before" in result
            assert "After" in result

    @patch("obsidian_to_substack.datawrapper.export_chart_png", return_value=FAKE_PNG)
    @patch("obsidian_to_substack.datawrapper.publish_table")
    def test_png_file_created(self, mock_publish, mock_export):
        mock_publish.return_value = ("https://datawrapper.dwcdn.net/xyz/1/", "xyz")
        text = "| X | Y |\n| --- | --- |\n| a | b |\n"
        tables = extract_tables(text)
        with tempfile.TemporaryDirectory() as tmpdir:
            replace_tables_with_embeds(
                text, tables, tmpdir,
                api_token="fake",
                article_title="Test",
            )
            assert (Path(tmpdir) / "table-1.png").exists()
            assert (Path(tmpdir) / "table-1.png").read_bytes() == FAKE_PNG

    @patch("obsidian_to_substack.datawrapper.export_chart_png", return_value=FAKE_PNG)
    @patch("obsidian_to_substack.datawrapper.publish_table")
    def test_csv_backup_still_created(self, mock_publish, mock_export):
        mock_publish.return_value = ("https://datawrapper.dwcdn.net/xyz/1/", "xyz")
        text = "| X | Y |\n| --- | --- |\n| a | b |\n"
        tables = extract_tables(text)
        with tempfile.TemporaryDirectory() as tmpdir:
            replace_tables_with_embeds(
                text, tables, tmpdir,
                api_token="fake",
                article_title="Test",
            )
            assert (Path(tmpdir) / "table-1.csv").exists()

    @patch("obsidian_to_substack.datawrapper.publish_table")
    def test_falls_back_on_api_failure(self, mock_publish):
        mock_publish.side_effect = RuntimeError("API error")
        text = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        tables = extract_tables(text)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = replace_tables_with_embeds(
                text, tables, tmpdir,
                api_token="fake",
                article_title="Test",
            )
            assert "<!-- TABLE 1:" in result
            assert "table-1.csv" in result

    def test_no_tables_returns_unchanged(self):
        text = "No tables here."
        with tempfile.TemporaryDirectory() as tmpdir:
            result = replace_tables_with_embeds(
                text, [], tmpdir,
                api_token="fake",
                article_title="Test",
            )
            assert result == text
