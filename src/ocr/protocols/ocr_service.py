"""Protocol definitions for OCR services."""

from typing import Protocol, List
from pathlib import Path


class OCRService(Protocol):
    """Protocol for OCR services."""
    
    async def process_file(self, file_path: Path) -> str:
        """Process a single file and return extracted text."""
        ...
    
    async def process_files(self, file_paths: List[Path]) -> List[str]:
        """Process multiple files and return extracted text for each."""
        ...
    
    async def process_folder(self, folder_path: Path) -> List[str]:
        """Process all supported files in a folder and return extracted text."""
        ...
