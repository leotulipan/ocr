"""Progress tracking and display for OCR operations."""

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

console = Console()


class ProgressManager:
    """Manage progress display for OCR operations.

    Context manager that provides progress tracking with Rich progress bars.
    In verbose mode, shows detailed progress with spinner, bar, and time estimates.
    In simple mode, suppresses progress bar (handled by simple print statements).
    """

    def __init__(self, verbose: bool = False):
        """Initialize progress manager.

        Args:
            verbose: Show detailed progress bar (True) or use simple output (False)
        """
        self.verbose = verbose
        self.progress = None
        self.task_id = None

    def __enter__(self):
        """Enter context manager and start progress display if verbose."""
        if self.verbose:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console,
            )
            self.progress.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and stop progress display."""
        if self.progress:
            self.progress.__exit__(exc_type, exc_val, exc_tb)
        return False

    def start_task(self, description: str, total: int):
        """Start a new progress task.

        Args:
            description: Task description to display
            total: Total number of items to process
        """
        if self.progress:
            self.task_id = self.progress.add_task(description, total=total)

    def update(self, advance: int = 1):
        """Update progress by advancing the task.

        Args:
            advance: Number of items to advance (default: 1)
        """
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, advance=advance)

    def update_description(self, description: str):
        """Update the task description.

        Args:
            description: New description to display
        """
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, description=description)

    def complete(self):
        """Mark the current task as completed."""
        if self.progress and self.task_id is not None:
            self.progress.update(self.task_id, completed=True)
