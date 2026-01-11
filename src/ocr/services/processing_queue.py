"""Async processing queue with retry logic and concurrency control."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Awaitable, Optional, Dict
from rich.console import Console

console = Console()


class JobStatus(Enum):
    """Status of a processing job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingJob:
    """Represents a file processing job."""
    file_path: Path
    status: JobStatus
    attempts: int = 0
    max_attempts: int = 3
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class ProcessingQueue:
    """Async queue for processing files with retry logic.

    Features:
    - Concurrent processing with semaphore
    - Retry with exponential backoff (3 attempts)
    - Job status tracking
    - Duplicate job prevention
    """

    def __init__(self, max_concurrent: int = 3):
        """Initialize processing queue.

        Args:
            max_concurrent: Maximum number of concurrent jobs
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.jobs: Dict[Path, ProcessingJob] = {}
        self.queue: asyncio.Queue[ProcessingJob] = asyncio.Queue()
        self.processing_task: Optional[asyncio.Task] = None
        self._shutdown = False

    def add_job(self, file_path: Path) -> bool:
        """Add a job to the queue.

        Args:
            file_path: Path to the file to process

        Returns:
            True if job was added, False if already exists
        """
        if file_path in self.jobs:
            job = self.jobs[file_path]
            # Don't re-add if already completed or currently processing
            if job.status in (JobStatus.COMPLETED, JobStatus.PROCESSING):
                return False

        job = ProcessingJob(file_path=file_path, status=JobStatus.PENDING)
        self.jobs[file_path] = job
        self.queue.put_nowait(job)
        return True

    async def process_job(
        self,
        job: ProcessingJob,
        processor: Callable[[Path], Awaitable[None]]
    ) -> bool:
        """Process a single job with retry logic.

        Args:
            job: The job to process
            processor: Async function that processes the file

        Returns:
            True if successful, False if failed after retries
        """
        async with self.semaphore:
            while job.attempts < job.max_attempts:
                job.attempts += 1
                job.status = JobStatus.PROCESSING
                job.started_at = datetime.now()

                try:
                    await processor(job.file_path)
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.now()
                    return True
                except Exception as e:
                    job.error = str(e)
                    console.print(f"[yellow]Attempt {job.attempts}/{job.max_attempts} failed for {job.file_path.name}: {e}[/yellow]")

                    if job.attempts < job.max_attempts:
                        # Exponential backoff: 1s, 2s, 4s
                        delay = 2 ** (job.attempts - 1)
                        await asyncio.sleep(delay)

            # All attempts failed
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            console.print(f"[red]Failed to process {job.file_path.name} after {job.max_attempts} attempts: {job.error}[/red]")
            return False

    async def start_processing(
        self,
        processor: Callable[[Path], Awaitable[None]]
    ):
        """Start processing jobs from the queue.

        Args:
            processor: Async function that processes files
        """
        while not self._shutdown:
            try:
                # Wait for a job with timeout to allow checking shutdown flag
                job = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                asyncio.create_task(self.process_job(job, processor))
            except asyncio.TimeoutError:
                # No job available, continue loop to check shutdown
                continue
            except Exception as e:
                console.print(f"[red]Queue processing error: {e}[/red]")

    def start(self, processor: Callable[[Path], Awaitable[None]]):
        """Start the queue processor in the background.

        Args:
            processor: Async function that processes files
        """
        if self.processing_task is None or self.processing_task.done():
            self._shutdown = False
            self.processing_task = asyncio.create_task(self.start_processing(processor))

    async def stop(self):
        """Stop the queue processor gracefully."""
        self._shutdown = True
        if self.processing_task and not self.processing_task.done():
            # Wait for current processing to finish
            await asyncio.sleep(0.5)
            if not self.processing_task.done():
                self.processing_task.cancel()
                try:
                    await self.processing_task
                except asyncio.CancelledError:
                    pass

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics.

        Returns:
            Dictionary with counts by status
        """
        stats = {
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "total": len(self.jobs)
        }

        for job in self.jobs.values():
            stats[job.status.value] += 1

        return stats
