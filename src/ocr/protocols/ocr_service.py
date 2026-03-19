"""Protocol definitions for OCR services."""

from pathlib import Path
from typing import Protocol


class OCRService(Protocol):
    """Protocol for OCR services."""

    async def process_file(self, file_path: Path, page_pattern: str | None = None, include_page_headlines: bool = False, include_images: bool = True) -> tuple[str, int, int]:
        """Process a single file and return extracted text."""
        ...

    async def process_files(self, file_paths: list[Path]) -> list[str]:
        """Process multiple files and return extracted text for each."""
        ...

    async def process_folder(self, folder_path: Path) -> list[str]:
        """Process all supported files in a folder and return extracted text."""
        ...
