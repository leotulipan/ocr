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

CRITICAL RULES:
1. Extract ONLY information that is explicitly present in the document or current filename
2. DO NOT hallucinate, infer, or guess information not in the text or filename
3. IGNORE any embedded images or image references (e.g., "![img-0.jpeg]")
4. Look for text content in markdown headings (# and ##), body text, and tables
5. Extract company name from the first H1 heading (starts with single #) or prominent business name near the top
6. Extract date in ISO format YYYY-MM-DD from any date found in the document OR current filename
7. For summary, identify the document type from H2 headings (##) or prominent keywords
8. If provided, use the current filename as a HIGH PRIORITY source for dates, names, and keywords

EXTRACTION GUIDELINES:
- **Company**: Look for markdown heading starting with "# " (H1) at the top of document. This is usually the company name. Shorten long names to key identifier (e.g., "Kolariks Freizeitbetriebe GmbH" → "Kolarik").
- **Date**: FIRST check current filename for ISO dates (YYYY-MM-DD), then search the document for dates in any format (DD.MM.YYYY, YYYY-MM-DD, etc.). Convert to ISO YYYY-MM-DD format. Check near the bottom for transaction dates.
- **Summary**: Look for H2 headings (##) like "## RECHNUNG" or keywords indicating document type. Also check current filename for keywords like "Meldezettel", "Rechnung", "Invoice". Use business-appropriate terms.

CURRENT FILENAME HINTS:
- If filename contains "YYYY-MM-DD" format, prioritize this date over dates in document
- If filename contains recognizable keywords (Meldezettel, Rechnung, etc.), use them
- If filename has structured info like "2020-10-01 Meldezettel Sompek Strasse", extract all parts
- Reformat filename info to match pattern: "{ISO-date} - {Company/Location} - {Summary}"

MARKDOWN STRUCTURE HINTS:
- "# CompanyName" = H1 heading with company
- "## RECHNUNG" = H2 heading indicating invoice/receipt type
- Tables and lists contain data but look for dates at the bottom
- Ignore image markers like "![]()" completely

CONFIDENCE SCORING (0.0 to 1.0, one decimal place):
- 0.9-1.0: All three fields (date, company, summary) clearly visible and unambiguous in document OR filename
- 0.7-0.8: Two fields clear, one partially clear or requires minor interpretation
- 0.5-0.6: Two fields found, one missing or unclear
- 0.3-0.4: Only one field clearly identified
- 0.1-0.2: No structured information found or mostly unreadable

Format: "{ISO-date} - {Company} - {Summary}" or "{Company} - {Summary}" if no date

Examples of correct extraction:

Input: "# HEUNISCH + FREBEN\n...\nDatum: 24.10.2022\n## Gastrorechnung"
Output: {"date": "2022-10-24", "company": "HEUNISCH + FREBEN", "summary": "Gastrorechnung", "confidence": 0.9}

Input (with current filename "2020-10-01 Meldezettel Sompek Strasse.pdf"): "Meldezettel document content..."
Output: {"date": "2020-10-01", "company": "Sompek Strasse", "summary": "Meldezettel", "confidence": 0.9}

Input: "# Kolariks Freizeitbetriebe GmbH\n1020 Wien...\n## RECHNUNG\n...\n21.10.2022 21:29:18"
Output: {"date": "2022-10-21", "company": "Kolarik", "summary": "Rechnung", "confidence": 0.9}

Input: "# WKO\nSome text...\n## Mahnung"
Output: {"date": null, "company": "WKO", "summary": "Mahnung", "confidence": 0.6}

Return ONLY valid JSON (no markdown code blocks):
{
  "date": "YYYY-MM-DD or null",
  "company": "Company name from H1 heading or null",
  "summary": "Document type 1-3 words",
  "confidence": 0.5
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

    async def analyze_content(
        self,
        markdown_content: str,
        pages_analyzed: int = 1,
        current_filename: Optional[str] = None
    ) -> FilenameMetadata:
        """Analyze markdown content and extract filename components.

        Args:
            markdown_content: The OCR'd markdown content to analyze
            pages_analyzed: Number of pages analyzed (1 for first page, -1 for all)
            current_filename: Optional current filename to use as additional context
        """
        try:
            # Build user message with optional current filename
            user_message = "Analyze this document content and generate filename:"
            if current_filename:
                user_message += f"\n\nCurrent filename: {current_filename}"
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
