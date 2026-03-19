"""Page pattern parser for OCR processing."""

import re


class PagePatternParser:
    """Parser for page patterns like '1-3', '5-', '4,5'."""

    @staticmethod
    def parse_pattern(pattern: str, total_pages: int) -> set[int]:
        """
        Parse a page pattern and return set of page numbers (1-indexed).

        Args:
            pattern: Page pattern string (e.g., "1-3", "5-", "4,5")
            total_pages: Total number of pages in the document

        Returns:
            Set of page numbers to process (1-indexed)

        Examples:
            "1-3" -> {1, 2, 3}
            "5-" -> {5, 6, 7, ...} (all pages from 5 to end)
            "4,5" -> {4, 5}
            "1-3,5,7-" -> {1, 2, 3, 5, 7, 8, ...}
        """
        if not pattern:
            return set(range(1, total_pages + 1))

        # Handle keyword patterns
        pattern_lower = pattern.strip().lower()
        if pattern_lower in ("all", "*"):
            return set(range(1, total_pages + 1))
        if pattern_lower in ("pg1", "first"):
            return {1}

        pages = set()
        parts = pattern.split(",")

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Handle range patterns (e.g., "1-3", "5-")
            if "-" in part:
                range_parts = part.split("-")
                if len(range_parts) == 2:
                    start_str = range_parts[0].strip()
                    end_str = range_parts[1].strip()

                    try:
                        start = int(start_str) if start_str else 1
                        end = int(end_str) if end_str else total_pages

                        # Validate ranges
                        start = max(1, min(start, total_pages))
                        end = max(1, min(end, total_pages))

                        if start <= end:
                            pages.update(range(start, end + 1))
                    except ValueError:
                        continue
            else:
                # Handle single page numbers
                try:
                    page_num = int(part)
                    if 1 <= page_num <= total_pages:
                        pages.add(page_num)
                except ValueError:
                    continue

        return pages

    @staticmethod
    def validate_pattern(pattern: str) -> bool:
        """
        Validate if a page pattern is well-formed.

        Args:
            pattern: Page pattern string to validate

        Returns:
            True if pattern is valid, False otherwise
        """
        if not pattern:
            return True

        # Handle keyword patterns
        if pattern.strip().lower() in ("all", "*", "pg1", "first"):
            return True

        # Pattern should only contain digits, commas, hyphens, and spaces
        if not re.match(r"^[\d\s,\-]+$", pattern):
            return False

        parts = pattern.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue

            if "-" in part:
                range_parts = part.split("-")
                if len(range_parts) != 2:
                    return False

                start_str = range_parts[0].strip()
                end_str = range_parts[1].strip()

                # At least one part should be a number
                if not start_str and not end_str:
                    return False

                # If both parts exist, they should be numbers
                if start_str and not start_str.isdigit():
                    return False
                if end_str and not end_str.isdigit():
                    return False
            else:
                if not part.isdigit():
                    return False

        return True
