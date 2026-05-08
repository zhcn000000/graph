from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from knowgraph.documents.converter import aconvert_file
from knowgraph.documents.models import Document


def _make_asyncify_mock():
    """asyncify(fn) -> async wrapper function."""

    def mock_asyncify(fn):
        async def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return wrapper

    return mock_asyncify


class TestAconvertFile:
    async def test_convert_local_path(self):
        with patch("knowgraph.documents.converter.get_markitdown_converter") as mock_get:
            mock_converter = MagicMock()
            mock_converter.convert_local.return_value = MagicMock(markdown="# Test\nContent")
            mock_get.return_value = mock_converter

            with patch("knowgraph.documents.converter.asyncify", _make_asyncify_mock()):
                result = await aconvert_file(Path("/fake/path/test.md"))

        assert isinstance(result, Document)
        assert result.content == "# Test\nContent"
        assert result.link == "file:///fake/path/test.md"

    async def test_convert_url(self):
        with patch("knowgraph.documents.converter.get_markitdown_converter") as mock_get:
            mock_converter = MagicMock()
            mock_converter.convert_url.return_value = MagicMock(markdown="# Web Content")
            mock_get.return_value = mock_converter

            with patch("knowgraph.documents.converter.asyncify", _make_asyncify_mock()):
                result = await aconvert_file("https://example.com/page")

        assert isinstance(result, Document)
        assert result.content == "# Web Content"
        assert result.link == "https://example.com/page"

    async def test_convert_stream(self):
        with patch("knowgraph.documents.converter.get_markitdown_converter") as mock_get:
            mock_converter = MagicMock()
            mock_converter.convert_stream.return_value = MagicMock(markdown="# Stream Content")
            mock_get.return_value = mock_converter

            with patch("knowgraph.documents.converter.asyncify", _make_asyncify_mock()):
                stream = BytesIO(b"fake binary content")
                result = await aconvert_file(stream)

        assert isinstance(result, Document)
        assert result.content == "# Stream Content"
        assert result.link.startswith("data:application/octet-stream;base64,")

    async def test_convert_data_uri(self):
        with patch("knowgraph.documents.converter.get_markitdown_converter") as mock_get:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = MagicMock(markdown="# Data Content")
            mock_get.return_value = mock_converter

            with patch("knowgraph.documents.converter.asyncify", _make_asyncify_mock()):
                result = await aconvert_file("data:text/plain;base64,SGVsbG8=")

        assert isinstance(result, Document)
        assert result.content == "# Data Content"

    async def test_convert_file_uri(self):
        with patch("knowgraph.documents.converter.get_markitdown_converter") as mock_get:
            mock_converter = MagicMock()
            mock_converter.convert_uri.return_value = MagicMock(markdown="# File Content")
            mock_get.return_value = mock_converter

            with patch("knowgraph.documents.converter.asyncify", _make_asyncify_mock()):
                result = await aconvert_file("file:///data/test.md")

        assert isinstance(result, Document)
        assert result.content == "# File Content"

    async def test_convert_unsupported_type(self):
        with pytest.raises(TypeError, match="Unsupported URI type"):
            await aconvert_file(42)

    async def test_convert_string_no_scheme(self):
        with pytest.raises(TypeError, match="Unsupported URI type"):
            await aconvert_file("just a string without scheme")
