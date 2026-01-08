"""Cache manager for OCR metadata."""

import json
import re
import yaml
from pathlib import Path
from typing import Optional
from datetime import datetime

from ..models.metadata import OCRMetadata, FilenameMetadata


class CacheManager:
    """Manage OCR metadata caching."""

    @staticmethod
    def get_cached_ocr_file(source_file: Path) -> Optional[Path]:
        """Find existing OCR markdown file for source file."""
        # Check in same directory as source file
        ocr_file = source_file.parent / f"{source_file.stem}_ocr.md"
        if ocr_file.exists():
            return ocr_file
        return None

    @staticmethod
    def extract_metadata(ocr_file: Path) -> Optional[OCRMetadata]:
        """Extract metadata from OCR markdown file."""
        try:
            with open(ocr_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Try YAML frontmatter first (new format)
            yaml_match = re.match(r'^---\n(.*?)\n---\n\n', content, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                metadata_dict = yaml.safe_load(yaml_content)

                # Parse filename_metadata if present
                filename_metadata = None
                if "filename_metadata" in metadata_dict and metadata_dict["filename_metadata"]:
                    fm_data = metadata_dict["filename_metadata"]
                    filename_metadata = FilenameMetadata(
                        generated_filename=fm_data.get("generated_filename", ""),
                        generation_timestamp=datetime.fromisoformat(fm_data.get("generation_timestamp", datetime.now().isoformat())),
                        generation_method=fm_data.get("generation_method", "unknown"),
                        confidence=fm_data.get("confidence"),
                        extracted_date=fm_data.get("extracted_date"),
                        extracted_company=fm_data.get("extracted_company"),
                        extracted_summary=fm_data.get("extracted_summary"),
                        pages_analyzed=fm_data.get("pages_analyzed", 1)
                    )

                return OCRMetadata(
                    source_file=metadata_dict.get("source_file"),
                    processed_at=datetime.fromisoformat(metadata_dict.get("processed_at", datetime.now().isoformat())),
                    content_length=metadata_dict.get("content_length", 0),
                    include_page_headlines=metadata_dict.get("include_page_headlines", False),
                    images_saved=metadata_dict.get("images_saved", 0),
                    filename_metadata=filename_metadata
                )

            # Fallback to legacy HTML comment format
            html_match = re.match(r'^<!--\n(.*?)\n-->\n\n', content, re.DOTALL)
            if html_match:
                metadata_json = json.loads(html_match.group(1))
                return OCRMetadata.from_legacy_json(metadata_json)

            return None

        except Exception:
            return None

    @staticmethod
    def get_cached_filename(source_file: Path, force: bool = False) -> Optional[FilenameMetadata]:
        """Get cached filename metadata if available."""
        if force:
            return None

        ocr_file = CacheManager.get_cached_ocr_file(source_file)
        if not ocr_file:
            return None

        metadata = CacheManager.extract_metadata(ocr_file)
        if not metadata or not metadata.filename_metadata:
            return None

        return metadata.filename_metadata

    @staticmethod
    def get_cached_markdown(source_file: Path) -> Optional[str]:
        """Get cached markdown content without re-OCRing."""
        ocr_file = CacheManager.get_cached_ocr_file(source_file)
        if not ocr_file:
            return None

        try:
            with open(ocr_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Strip YAML frontmatter
            content = re.sub(r'^---\n.*?\n---\n\n', '', content, count=1, flags=re.DOTALL)

            # Strip legacy HTML comment header if present
            content = re.sub(r'^<!--\n.*?\n-->\n\n', '', content, count=1, flags=re.DOTALL)

            # Strip images map if present
            content = re.sub(r'^<!--IMAGES_MAP\n.*?\n-->\n\n', '', content, count=1, flags=re.DOTALL)

            return content

        except Exception:
            return None
