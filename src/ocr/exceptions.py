"""OCR application exceptions.

This module defines a hierarchy of exceptions for better error handling
and user-friendly error messages.
"""


class OCRError(Exception):
    """Base exception for OCR errors."""

    def __init__(self, message: str, suggestion: str = None):
        """Initialize OCR error.

        Args:
            message: Error message describing what went wrong
            suggestion: Optional suggestion for how to fix the issue
        """
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class FileNotFoundError(OCRError):
    """File or folder not found."""

    pass


class InvalidFileError(OCRError):
    """Invalid or corrupted file."""

    pass


class APIError(OCRError):
    """API communication error."""

    def __init__(self, message: str, status_code: int = None, retry_after: int = None, suggestion: str = None):
        """Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code if available
            retry_after: Seconds to wait before retrying (for rate limits)
            suggestion: Optional suggestion for fixing the issue
        """
        super().__init__(message, suggestion)
        self.status_code = status_code
        self.retry_after = retry_after


class AuthenticationError(APIError):
    """API authentication failed."""

    pass


class RateLimitError(APIError):
    """API rate limit exceeded."""

    pass


class QuotaExceededError(APIError):
    """API quota exceeded."""

    pass


class CacheError(OCRError):
    """Cache read/write error."""

    pass


class FilenameGenerationError(OCRError):
    """Filename generation failed."""

    pass
