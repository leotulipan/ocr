"""Folder watcher for monitoring new files."""

import asyncio
import concurrent.futures
import time
from pathlib import Path
from typing import Callable, Awaitable, Optional, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from rich.console import Console

console = Console()


class FolderWatcher:
    """Watches a folder for new files and triggers processing.

    Features:
    - Monitors FileCreatedEvent for new files
    - Waits for file stability (handles slow network transfers)
    - Filters by supported extensions
    - Recursive directory monitoring
    """

    SUPPORTED_EXTENSIONS = {'.pdf', '.pptx', '.docx', '.png', '.jpg', '.jpeg', '.avif'}

    def __init__(
        self,
        folder_path: Path,
        on_file_ready: Callable[[Path], Awaitable[None]],
        recursive: bool = False
    ):
        """Initialize folder watcher.

        Args:
            folder_path: Path to the folder to watch
            on_file_ready: Async callback when a file is ready for processing
            recursive: Watch subdirectories recursively
        """
        self.folder_path = folder_path
        self.on_file_ready = on_file_ready
        self.recursive = recursive
        self.observer = Observer()
        self.handler = FileHandler(self, set())
        self._stability_futures: Set[concurrent.futures.Future] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def mark_processed(self, file_path: Path):
        """Mark a path as processed to prevent re-triggering."""
        self.handler.processed_files.add(file_path)

    async def wait_for_file_stability(self, file_path: Path):
        """Wait for a file to stop changing (file transfer complete).

        Args:
            file_path: Path to the file to monitor
        """
        if not file_path.exists():
            return

        console.print(f"[cyan]Detected: {file_path.name}[/cyan]")

        # Wait for file size to stabilize (3 consecutive checks with same size)
        stable_count = 0
        prev_size = -1

        while stable_count < 3:
            await asyncio.sleep(1)

            if not file_path.exists():
                console.print(f"[yellow]File disappeared: {file_path.name}[/yellow]")
                return

            try:
                current_size = file_path.stat().st_size
                if current_size == prev_size:
                    stable_count += 1
                else:
                    stable_count = 0
                    prev_size = current_size
            except Exception as e:
                console.print(f"[yellow]Error checking file stability: {e}[/yellow]")
                return

        console.print(f"[green]Ready: {file_path.name}[/green]")

        # File is stable, trigger processing
        try:
            await self.on_file_ready(file_path)
        except Exception as e:
            console.print(f"[red]Error processing {file_path.name}: {e}[/red]")

    def _handle_new_file(self, file_path: Path):
        """Handle a new file event.

        Args:
            file_path: Path to the new file
        """
        # Filter by supported extensions
        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return

        if self._loop is None:
            return

        # Schedule coroutine on the main event loop from watchdog's background thread
        future = asyncio.run_coroutine_threadsafe(
            self.wait_for_file_stability(file_path),
            self._loop
        )
        self._stability_futures.add(future)
        future.add_done_callback(self._stability_futures.discard)

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start watching the folder."""
        self._loop = loop or asyncio.get_event_loop()

        if not self.folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {self.folder_path}")

        self.observer.schedule(
            self.handler,
            str(self.folder_path),
            recursive=self.recursive
        )
        self.observer.start()
        console.print(f"[green]Watching: {self.folder_path}[/green] (recursive: {self.recursive})")

    def stop(self):
        """Stop watching the folder."""
        self.observer.stop()
        self.observer.join()

        # Cancel any pending stability checks
        for future in self._stability_futures:
            if not future.done():
                future.cancel()


class FileHandler(FileSystemEventHandler):
    """Handles file system events from watchdog."""

    def __init__(self, watcher: FolderWatcher, processed_files: Set[Path]):
        """Initialize file handler.

        Args:
            watcher: The FolderWatcher instance
            processed_files: Set of files already processed (for deduplication)
        """
        self.watcher = watcher
        self.processed_files = processed_files

    def on_created(self, event):
        """Handle file creation event."""
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            file_path = Path(event.src_path)

            # Skip if already processed
            if file_path in self.processed_files:
                return

            self.processed_files.add(file_path)
            self.watcher._handle_new_file(file_path)

    def on_moved(self, event):
        """Handle file moved/renamed event to prevent re-processing renamed files."""
        if not event.is_directory:
            self.processed_files.add(Path(event.dest_path))
