"""Metadata models for OCR processing."""

from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class FilenameMetadata(BaseModel):
    """Metadata for generated filenames."""

    generated_filename: str
    generation_timestamp: datetime
    generation_method: str = Field(default="mistral-small-2506")
    confidence: Optional[float] = None  # 0.0 (low) to 1.0 (high), e.g., 0.5 for medium
    extracted_date: Optional[str] = None
    extracted_company: Optional[str] = None
    extracted_summary: Optional[str] = None
    pages_analyzed: int = 1


class OCRMetadata(BaseModel):
    """Complete metadata for OCR output files."""

    source_file: Optional[str] = None
    original_filename: Optional[str] = None  # Original filename before any renaming
    processed_at: datetime
    content_length: int
    include_page_headlines: bool = False
    images_saved: int = 0
    filename_metadata: Optional[FilenameMetadata] = None

    @classmethod
    def from_legacy_json(cls, data: dict) -> "OCRMetadata":
        """Create from existing JSON metadata (backward compatibility)."""
        # Handle datetime parsing
        processed_at_str = data.get("processed_at")
        if isinstance(processed_at_str, str):
            processed_at = datetime.fromisoformat(processed_at_str)
        else:
            processed_at = datetime.now()

        return cls(
            source_file=data.get("source_file"),
            original_filename=data.get("original_filename"),
            processed_at=processed_at,
            content_length=data.get("content_length", 0),
            include_page_headlines=data.get("include_page_headlines", False),
            images_saved=data.get("images_saved", 0),
            filename_metadata=None  # Legacy files don't have this
        )

    def to_yaml_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        result = {
            "source_file": self.source_file,
            "original_filename": self.original_filename,
            "processed_at": self.processed_at.isoformat(),
            "content_length": self.content_length,
            "include_page_headlines": self.include_page_headlines,
            "images_saved": self.images_saved,
        }

        if self.filename_metadata:
            result["filename_metadata"] = {
                "generated_filename": self.filename_metadata.generated_filename,
                "generation_timestamp": self.filename_metadata.generation_timestamp.isoformat(),
                "generation_method": self.filename_metadata.generation_method,
                "confidence": self.filename_metadata.confidence,
                "extracted_date": self.filename_metadata.extracted_date,
                "extracted_company": self.filename_metadata.extracted_company,
                "extracted_summary": self.filename_metadata.extracted_summary,
                "pages_analyzed": self.filename_metadata.pages_analyzed,
            }

        return result
