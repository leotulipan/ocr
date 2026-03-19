"""Metadata models for OCR processing."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FilenameMetadata(BaseModel):
    """Metadata for generated filenames."""

    generated_filename: str
    generation_timestamp: datetime
    generation_method: str = Field(default="mistral-small-2506")
    confidence: float | None = None  # 0.0 (low) to 1.0 (high), e.g., 0.5 for medium
    extracted_date: str | None = None
    extracted_company: str | None = None
    extracted_summary: str | None = None
    pages_analyzed: int = 1


class RenameEvent(BaseModel):
    """A single rename operation record."""

    from_name: str
    to_name: str
    timestamp: datetime
    confidence: float | None = None


class OCRMetadata(BaseModel):
    """Complete metadata for OCR output files."""

    source_file: str | None = None
    original_filename: str | None = None  # Original filename before any renaming
    processed_at: datetime
    content_length: int
    include_page_headlines: bool = False
    images_saved: int = 0
    filename_metadata: FilenameMetadata | None = None
    rename_history: list[RenameEvent] = Field(default_factory=list)

    @classmethod
    def from_legacy_json(cls, data: dict) -> "OCRMetadata":
        """Create from existing JSON metadata (backward compatibility)."""
        # Handle datetime parsing
        processed_at_str = data.get("processed_at")
        if isinstance(processed_at_str, str):
            processed_at = datetime.fromisoformat(processed_at_str)
        else:
            processed_at = datetime.now()

        # Parse rename_history if present
        rename_history = []
        for entry in data.get("rename_history", []):
            rename_history.append(
                RenameEvent(
                    from_name=entry["from_name"],
                    to_name=entry["to_name"],
                    timestamp=datetime.fromisoformat(entry["timestamp"]),
                    confidence=entry.get("confidence"),
                )
            )

        return cls(
            source_file=data.get("source_file"),
            original_filename=data.get("original_filename"),
            processed_at=processed_at,
            content_length=data.get("content_length", 0),
            include_page_headlines=data.get("include_page_headlines", False),
            images_saved=data.get("images_saved", 0),
            filename_metadata=None,  # Legacy files don't have this
            rename_history=rename_history,
        )

    def to_yaml_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        result = {
            "source_file": self.source_file,
            "original_filename": self.original_filename,
            "processed_at": self.processed_at.isoformat(),
            "content_length": self.content_length,
            "include_page_headlines": self.include_page_headlines,
            "images_saved": self.images_saved,
        }

        if self.rename_history:
            result["rename_history"] = [
                {
                    "from_name": event.from_name,
                    "to_name": event.to_name,
                    "timestamp": event.timestamp.isoformat(),
                    "confidence": event.confidence,
                }
                for event in self.rename_history
            ]

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
