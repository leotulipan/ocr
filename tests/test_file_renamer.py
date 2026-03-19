"""Tests for FileRenamer."""

import os
import time

from ocr.utils.file_renamer import FileRenamer


class TestResolveCollision:
    """Tests for collision resolution."""

    def test_no_collision(self, tmp_path):
        target = tmp_path / "test.pdf"
        assert FileRenamer.resolve_collision(target) == target

    def test_collision_adds_counter(self, tmp_path):
        target = tmp_path / "test.pdf"
        target.touch()
        result = FileRenamer.resolve_collision(target)
        assert result == tmp_path / "test_2.pdf"

    def test_multiple_collisions(self, tmp_path):
        (tmp_path / "test.pdf").touch()
        (tmp_path / "test_2.pdf").touch()
        result = FileRenamer.resolve_collision(tmp_path / "test.pdf")
        assert result == tmp_path / "test_3.pdf"


class TestRenameFilePair:
    """Tests for rename_file_pair."""

    def test_rename_source_only(self, tmp_path):
        source = tmp_path / "old.pdf"
        source.write_text("content")

        new_source, new_ocr = FileRenamer.rename_file_pair(source, "new")
        assert new_source == tmp_path / "new.pdf"
        assert new_source.exists()
        assert not source.exists()

    def test_rename_with_ocr_file(self, tmp_path):
        source = tmp_path / "old.pdf"
        source.write_text("content")
        ocr_dir = tmp_path / ".ocr"
        ocr_dir.mkdir()
        ocr_file = ocr_dir / "old.pg1.md"
        ocr_file.write_text("---\n---\nmarkdown")

        new_source, new_ocr = FileRenamer.rename_file_pair(source, "new")
        assert new_source == tmp_path / "new.pdf"
        assert new_ocr == ocr_dir / "new.pg1.md"
        assert new_ocr.exists()

    def test_dry_run_returns_paths_without_renaming(self, tmp_path):
        source = tmp_path / "old.pdf"
        source.write_text("content")

        new_source, new_ocr = FileRenamer.rename_file_pair(source, "new", dry_run=True)
        assert new_source == tmp_path / "new.pdf"
        assert source.exists()  # Not renamed

    def test_timestamp_preserved_on_rename(self, tmp_path):
        source = tmp_path / "old.pdf"
        source.write_text("content")

        # Set a specific mtime in the past
        past_time = time.time() - 86400 * 365  # 1 year ago
        os.utime(source, (past_time, past_time))
        original_mtime = os.stat(source).st_mtime

        new_source, _ = FileRenamer.rename_file_pair(source, "new")
        assert abs(os.stat(new_source).st_mtime - original_mtime) < 1.0

    def test_collision_during_rename(self, tmp_path):
        source = tmp_path / "old.pdf"
        source.write_text("old content")
        existing = tmp_path / "new.pdf"
        existing.write_text("existing content")

        new_source, _ = FileRenamer.rename_file_pair(source, "new")
        assert new_source == tmp_path / "new_2.pdf"
        assert new_source.exists()
