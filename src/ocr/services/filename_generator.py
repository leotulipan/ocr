"""Intelligent filename generation service using Mistral AI."""

import json
import re
from pathlib import Path
from typing import Optional
from datetime import datetime
from mistralai import Mistral

from ..models.settings import Settings
from ..models.metadata import FilenameMetadata

_PROMPT_FILE = Path(__file__).parent / "filename_generator_prompt.md"


class FilenameGenerator:
    """Generate intelligent filenames from OCR content."""

    SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")

    def __init__(self, settings: Settings, client: Optional[Mistral] = None):
        """Initialize filename generator.

        Args:
            settings: Application settings
            client: Optional pre-initialized Mistral client for sharing with OCR adapter
        """
        self.client = client or Mistral(api_key=settings.mistral_api_key.get_secret_value())
        self.settings = settings

    def _extract_json_from_response(self, text: str) -> dict:
        """Extract JSON from response, handling markdown code blocks."""
        # Remove markdown code blocks if present
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in response: {text}") from e

    async def analyze_content(
        self,
        markdown_content: str,
        pages_analyzed: int = 1,
        current_filename: Optional[str] = None,
        file_created_date: Optional[str] = None,
        file_modified_date: Optional[str] = None
    ) -> FilenameMetadata:
        """Analyze markdown content and extract filename components.

        Args:
            markdown_content: The OCR'd markdown content to analyze
            pages_analyzed: Number of pages analyzed (1 for first page, -1 for all)
            current_filename: Optional current filename to use as additional context
            file_created_date: Optional file creation date from filesystem (ISO format)
            file_modified_date: Optional file modification date from filesystem (ISO format)
        """
        try:
            # Build user message with optional current filename and file dates
            user_message = "Analyze this document content and generate filename:"
            if current_filename:
                user_message += f"\n\nCurrent filename: {current_filename}"
            if file_created_date or file_modified_date:
                user_message += "\n\nFilesystem dates:"
                if file_created_date:
                    user_message += f"\n  - File created: {file_created_date}"
                if file_modified_date:
                    user_message += f"\n  - File modified: {file_modified_date}"
            user_message += f"\n\nDocument content:\n{markdown_content[:4000]}"

            # Call Mistral chat completion API
            response = await self.client.chat.complete_async(
                model=self.settings.filename_generation_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=self.settings.filename_generation_temperature,
                max_tokens=self.settings.filename_generation_max_tokens
            )

            # Parse response
            result_text = response.choices[0].message.content
            result = self._extract_json_from_response(result_text)

            # Build filename
            date = result.get("date")
            company = result.get("company")
            summary = result.get("summary", "Document")
            confidence_raw = result.get("confidence", 0.5)

            # Parse confidence as float
            if isinstance(confidence_raw, (int, float)):
                confidence = float(confidence_raw)
                # Clamp to 0.0-1.0 range and round to 1 decimal place
                confidence = round(max(0.0, min(1.0, confidence)), 1)
            else:
                # Fallback for unexpected types
                confidence = 0.5

            # Construct filename following pattern
            parts = []
            if date:
                parts.append(date)
            if company:
                parts.append(company)
            parts.append(summary)

            generated_filename = " - ".join(parts)

            # Sanitize filename (remove invalid characters)
            generated_filename = self._sanitize_filename(generated_filename)

            return FilenameMetadata(
                generated_filename=generated_filename,
                generation_timestamp=datetime.now(),
                generation_method=self.settings.filename_generation_model,
                confidence=confidence,
                extracted_date=date,
                extracted_company=company,
                extracted_summary=summary,
                pages_analyzed=pages_analyzed
            )

        except Exception as e:
            # Fallback: use generic name
            return FilenameMetadata(
                generated_filename="Document",
                generation_timestamp=datetime.now(),
                generation_method="fallback",
                confidence=0.1,  # Low confidence for fallback
                pages_analyzed=pages_analyzed
            )

    def _sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename."""
        # Windows forbidden characters: < > : " / \ | ? *
        invalid_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(invalid_chars, '', filename)

        # Replace multiple spaces with single space
        sanitized = re.sub(r'\s+', ' ', sanitized)

        # Trim whitespace
        sanitized = sanitized.strip()

        # Limit length (Windows max path is 260, leave room for directory and extension)
        max_length = 200
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].strip()

        return sanitized

    def generate_filename_with_extension(self, base_filename: str, original_file: Path) -> str:
        """Combine generated filename with original file extension."""
        extension = original_file.suffix
        return f"{base_filename}{extension}"
