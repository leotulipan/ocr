"""Tests for FolderWatcher."""

from unittest.mock import AsyncMock, MagicMock

from ocr.services.folder_watcher import FileHandler, FolderWatcher


class TestFolderWatcher:
    """Tests for FolderWatcher."""

    def test_mark_processed(self, tmp_path):
        watcher = FolderWatcher(tmp_path, AsyncMock())
        test_path = tmp_path / "test.pdf"
        watcher.mark_processed(test_path)
        assert test_path in watcher.handler.processed_files

    def test_unsupported_extension_ignored(self, tmp_path):
        watcher = FolderWatcher(tmp_path, AsyncMock())
        watcher._loop = MagicMock()
        watcher._handle_new_file(tmp_path / "file.txt")
        # No future should be created for unsupported file
        assert len(watcher._stability_futures) == 0

    def test_handle_new_file_without_loop_is_noop(self, tmp_path):
        watcher = FolderWatcher(tmp_path, AsyncMock())
        # _loop is None by default
        watcher._handle_new_file(tmp_path / "file.pdf")
        assert len(watcher._stability_futures) == 0


class TestFileHandler:
    """Tests for FileHandler."""

    def test_on_created_skips_processed(self, tmp_path):
        watcher = MagicMock()
        processed = {tmp_path / "test.pdf"}
        handler = FileHandler(watcher, processed)

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "test.pdf")
        event.__class__ = type("FileCreatedEvent", (), {})

        # Since it's in processed_files, _handle_new_file should not be called
        from watchdog.events import FileCreatedEvent
        event = MagicMock(spec=FileCreatedEvent)
        event.is_directory = False
        event.src_path = str(tmp_path / "test.pdf")
        handler.on_created(event)
        watcher._handle_new_file.assert_not_called()

    def test_on_moved_adds_dest_to_processed(self, tmp_path):
        watcher = MagicMock()
        processed = set()
        handler = FileHandler(watcher, processed)

        event = MagicMock()
        event.is_directory = False
        event.dest_path = str(tmp_path / "renamed.pdf")
        handler.on_moved(event)
        assert tmp_path / "renamed.pdf" in processed
