"""Folder watcher for monitoring new files."""

import asyncio
import time
from pathlib import Path
from typing import Callable, Awaitable, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
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
        self._stability_tasks: Set[asyncio.Task] = set()

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

        # Create stability check task
        task = asyncio.create_task(self.wait_for_file_stability(file_path))
        self._stability_tasks.add(task)
        task.add_done_callback(self._stability_tasks.discard)

    def start(self):
        """Start watching the folder."""
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
        for task in self._stability_tasks:
            if not task.done():
                task.cancel()


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
        """Handle file creation event.

        Args:
            event: The file system event
        """
        # Only handle file creation (not directory creation)
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            file_path = Path(event.src_path)

            # Skip if already processed
            if file_path in self.processed_files:
                return

            self.processed_files.add(file_path)
            self.watcher._handle_new_file(file_path)
