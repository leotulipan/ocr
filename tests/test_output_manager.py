"""Tests for OutputManager."""

import pytest

from ocr.utils.output_manager import OutputManager


class TestSaveTextResult:
    """Tests for save_text_result method."""

    @pytest.mark.asyncio
    async def test_single_page_creates_pg1_file(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        om = OutputManager(save_at_input_location=True)

        output_file, img_count = await om.save_text_result("Hello world", "doc", source, pages_processed=1)
        assert output_file.name == "doc.pg1.md"
        assert output_file.parent.name == ".ocr"
        assert img_count == 0

    @pytest.mark.asyncio
    async def test_multi_page_creates_md_file(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        om = OutputManager(save_at_input_location=True)

        output_file, _ = await om.save_text_result("Hello world", "doc", source, pages_processed=5)
        assert output_file.name == "doc.md"

    @pytest.mark.asyncio
    async def test_skip_images_strips_header(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        om = OutputManager(save_at_input_location=True)

        content = '<!--IMAGES_MAP\n{"img.jpg": {"mime": "image/jpeg", "base64": "abc"}}\n-->\n\nText content'
        output_file, img_count = await om.save_text_result(content, "doc", source, pages_processed=1, skip_images=True)
        assert img_count == 0
        text = output_file.read_text(encoding="utf-8")
        assert "IMAGES_MAP" not in text
        assert "Text content" in text

    @pytest.mark.asyncio
    async def test_yaml_frontmatter_present(self, tmp_path):
        source = tmp_path / "doc.pdf"
        source.touch()
        om = OutputManager(save_at_input_location=True)

        output_file, _ = await om.save_text_result("Content", "doc", source, pages_processed=1)
        text = output_file.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "source_file:" in text
