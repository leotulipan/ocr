"""File-based locking to prevent duplicate processing."""

import os
import time
from pathlib import Path
from typing import Optional


class LockManager:
    """Manage file locks to prevent duplicate processing.

    Uses file-based locking with stale lock detection to ensure only one
    process can work on a file at a time.
    """

    LOCK_TIMEOUT_SECONDS = 300  # 5 minutes

    @staticmethod
    def get_lock_path(file_path: Path) -> Path:
        """Get the lock file path for a given source file.

        Args:
            file_path: Path to the source file

        Returns:
            Path to the lock file in .ocr subdirectory
        """
        ocr_dir = file_path.parent / ".ocr"
        ocr_dir.mkdir(exist_ok=True)
        return ocr_dir / f".{file_path.stem}.lock"

    @staticmethod
    def acquire_lock(file_path: Path) -> bool:
        """Attempt to acquire a lock for processing a file.

        Args:
            file_path: Path to the file to lock

        Returns:
            True if lock was acquired, False if already locked
        """
        lock_path = LockManager.get_lock_path(file_path)

        # Check for stale lock
        if lock_path.exists():
            try:
                stat = lock_path.stat()
                lock_age = time.time() - stat.st_mtime
                if lock_age > LockManager.LOCK_TIMEOUT_SECONDS:
                    # Stale lock detected, remove it
                    lock_path.unlink()
                else:
                    # Valid lock exists
                    return False
            except Exception:
                # If we can't read the lock, try to remove it
                try:
                    lock_path.unlink()
                except Exception:
                    return False

        # Try to create lock file exclusively
        try:
            # Using O_CREAT | O_EXCL ensures atomic creation
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)

            # Write timestamp and PID to lock file
            with open(lock_path, 'w') as f:
                f.write(f"{time.time()}\n{os.getpid()}\n")

            return True
        except FileExistsError:
            # Another process created the lock between our check and creation
            return False
        except Exception:
            return False

    @staticmethod
    def release_lock(file_path: Path) -> bool:
        """Release a lock for a file.

        Args:
            file_path: Path to the file to unlock

        Returns:
            True if lock was released, False if lock didn't exist
        """
        lock_path = LockManager.get_lock_path(file_path)

        try:
            if lock_path.exists():
                lock_path.unlink()
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def is_locked(file_path: Path) -> bool:
        """Check if a file is currently locked.

        Args:
            file_path: Path to check

        Returns:
            True if locked, False otherwise
        """
        lock_path = LockManager.get_lock_path(file_path)

        if not lock_path.exists():
            return False

        # Check if lock is stale
        try:
            stat = lock_path.stat()
            lock_age = time.time() - stat.st_mtime
            return lock_age <= LockManager.LOCK_TIMEOUT_SECONDS
        except Exception:
            return False


class FileLock:
    """Context manager for file locking.

    Usage:
        with FileLock(file_path) as locked:
            if locked:
                # Process file
                pass
            else:
                # File is locked by another process
                pass
    """

    def __init__(self, file_path: Path):
        """Initialize file lock.

        Args:
            file_path: Path to the file to lock
        """
        self.file_path = file_path
        self.locked = False

    def __enter__(self) -> bool:
        """Acquire lock when entering context.

        Returns:
            True if lock was acquired, False otherwise
        """
        self.locked = LockManager.acquire_lock(self.file_path)
        return self.locked

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release lock when exiting context."""
        if self.locked:
            LockManager.release_lock(self.file_path)
        return False
