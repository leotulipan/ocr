"""Intelligent filename generation service using Mistral AI."""

import json
import re
from pathlib import Path
from typing import Optional
from datetime import datetime
from mistralai import Mistral

from ..models.settings import Settings
from ..models.metadata import FilenameMetadata


class FilenameGenerator:
    """Generate intelligent filenames from OCR content."""

    SYSTEM_PROMPT = """You are a filename generation expert. Analyze document content and generate structured, descriptive filenames.

Your task:
1. Extract key information: date (ISO format YYYY-MM-DD), company/author name, document type/summary
2. For invoices, letters, legal documents use format: "{ISO-date} - {Company} - {Summary}"
3. If no date found, use company and summary only: "{Company} - {Summary}"
4. Keep summary concise (2-4 words), descriptive but not verbose
5. Use proper capitalization, no special characters except hyphens
6. Return ONLY valid JSON with no markdown formatting

Examples:
- Invoice from Medivere dated Dec 1, 2024: {"date": "2024-12-01", "company": "Medivere", "summary": "Befund Julia", "confidence": "high"}
- Letter from WKO dated Sept 3, 2024: {"date": "2024-09-03", "company": "WKO", "summary": "Mahnung Privat", "confidence": "high"}
- Undated receipt from Amazon: {"date": null, "company": "Amazon", "summary": "Order Receipt", "confidence": "medium"}

Return JSON format:
{
  "date": "YYYY-MM-DD or null",
  "company": "Company/Author name or null",
  "summary": "Brief description",
  "confidence": "high|medium|low"
}"""

    def __init__(self, settings: Settings):
        """Initialize filename generator."""
        self.client = Mistral(api_key=settings.mistral_api_key.get_secret_value())
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

    async def analyze_content(self, markdown_content: str, pages_analyzed: int = 1) -> FilenameMetadata:
        """Analyze markdown content and extract filename components."""
        try:
            # Call Mistral chat completion API
            response = await self.client.chat.complete_async(
                model=self.settings.filename_generation_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Analyze this document content and generate filename:\n\n{markdown_content[:4000]}"}
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
            confidence = result.get("confidence", "medium")

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
                confidence="low",
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
