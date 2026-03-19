"""Tests for CacheManager."""

from ocr.utils.cache_manager import CacheManager


class TestGetCachedOcrFile:
    """Tests for finding cached OCR files."""

    def test_finds_pg1_file(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        ocr_dir = tmp_path / ".ocr"
        ocr_dir.mkdir()
        pg1 = ocr_dir / "doc.pg1.md"
        pg1.write_text("---\nsource_file: test\n---\ncontent")

        result = CacheManager.get_cached_ocr_file(source)
        assert result == pg1

    def test_finds_md_file(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        ocr_dir = tmp_path / ".ocr"
        ocr_dir.mkdir()
        md = ocr_dir / "doc.md"
        md.write_text("---\nsource_file: test\n---\ncontent")

        result = CacheManager.get_cached_ocr_file(source)
        assert result == md

    def test_returns_none_when_no_cache(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        result = CacheManager.get_cached_ocr_file(source)
        assert result is None


class TestGetCachedMarkdown:
    """Tests for retrieving cached markdown content."""

    def test_returns_content_without_frontmatter(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        ocr_dir = tmp_path / ".ocr"
        ocr_dir.mkdir()
        md = ocr_dir / "doc.pg1.md"
        md.write_text("---\nsource_file: test\n---\n\nHello world")

        result = CacheManager.get_cached_markdown(source)
        assert result is not None
        assert "Hello world" in result

    def test_returns_none_when_no_cache(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        result = CacheManager.get_cached_markdown(source)
        assert result is None
