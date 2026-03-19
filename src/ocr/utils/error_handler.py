"""Centralized error handling with rich formatting."""

from rich.console import Console
from rich.panel import Panel

from ..exceptions import (
    AuthenticationError,
    FileNotFoundError,
    InvalidFileError,
    OCRError,
    QuotaExceededError,
    RateLimitError,
)

console = Console()


class ErrorHandler:
    """Handle and format errors for CLI."""

    @staticmethod
    def handle_error(error: Exception, verbose: bool = False) -> int:
        """Handle error and return appropriate exit code.

        Args:
            error: The exception to handle
            verbose: Show detailed stack traces

        Returns:
            Exit code (0=success, 1=general, 2=auth, 3=rate limit, 4=quota, 5=invalid file, 6=not found)
        """
        if isinstance(error, AuthenticationError):
            ErrorHandler._show_auth_error(error)
            return 2
        elif isinstance(error, RateLimitError):
            ErrorHandler._show_rate_limit_error(error)
            return 3
        elif isinstance(error, QuotaExceededError):
            ErrorHandler._show_quota_error(error)
            return 4
        elif isinstance(error, InvalidFileError):
            ErrorHandler._show_file_error(error)
            return 5
        elif isinstance(error, FileNotFoundError):
            ErrorHandler._show_not_found_error(error)
            return 6
        elif isinstance(error, OCRError):
            ErrorHandler._show_ocr_error(error, verbose)
            return 1
        else:
            ErrorHandler._show_generic_error(error, verbose)
            return 1

    @staticmethod
    def _show_auth_error(error: AuthenticationError):
        """Display authentication error with suggestions."""
        console.print(
            Panel(
                "[red]Authentication Failed[/red]\n\n"
                f"{error.message}\n\n"
                "[yellow]Suggestions:[/yellow]\n"
                "1. Check your MISTRAL_API_KEY in .env file\n"
                "2. Verify the key is valid at https://console.mistral.ai\n"
                "3. Ensure the key has OCR API access enabled",
                title="❌ Authentication Error",
                border_style="red",
            )
        )

    @staticmethod
    def _show_rate_limit_error(error: RateLimitError):
        """Display rate limit error with suggestions."""
        retry_msg = f"\n\nRetry after: {error.retry_after} seconds" if error.retry_after else ""
        console.print(
            Panel(
                "[yellow]Rate Limit Exceeded[/yellow]\n\n"
                f"{error.message}{retry_msg}\n\n"
                "[cyan]Suggestions:[/cyan]\n"
                "1. Wait before retrying your request\n"
                "2. Reduce --concurrent value for batch operations\n"
                "3. Process files in smaller batches\n"
                "4. Consider upgrading your API plan for higher limits",
                title="⚠️  Rate Limit Error",
                border_style="yellow",
            )
        )

    @staticmethod
    def _show_quota_error(error: QuotaExceededError):
        """Display quota error with suggestions."""
        console.print(
            Panel(
                "[red]API Quota Exceeded[/red]\n\n"
                f"{error.message}\n\n"
                "[yellow]Suggestions:[/yellow]\n"
                "1. Check your usage at https://console.mistral.ai\n"
                "2. Upgrade your plan for higher monthly limits\n"
                "3. Wait for quota reset (usually monthly)",
                title="❌ Quota Error",
                border_style="red",
            )
        )

    @staticmethod
    def _show_file_error(error: InvalidFileError):
        """Display invalid file error with suggestions."""
        suggestion = error.suggestion or "Verify the file is not corrupted and retry"
        console.print(
            Panel(
                f"[red]Invalid File[/red]\n\n{error.message}\n\n[yellow]Suggestion:[/yellow] {suggestion}",
                title="❌ File Error",
                border_style="red",
            )
        )

    @staticmethod
    def _show_not_found_error(error: FileNotFoundError):
        """Display file not found error."""
        console.print(f"[red]Error:[/red] {error.message}")
        if error.suggestion:
            console.print(f"[yellow]Suggestion:[/yellow] {error.suggestion}")

    @staticmethod
    def _show_ocr_error(error: OCRError, verbose: bool):
        """Display OCR error with optional stack trace."""
        console.print(f"[red]Error:[/red] {error.message}")
        if error.suggestion:
            console.print(f"[yellow]Suggestion:[/yellow] {error.suggestion}")
        if verbose:
            import traceback

            console.print("\n[dim]Stack trace:[/dim]")
            console.print(traceback.format_exc())

    @staticmethod
    def _show_generic_error(error: Exception, verbose: bool):
        """Display generic error for unexpected exceptions."""
        console.print(f"[red]Unexpected Error:[/red] {str(error)}")
        console.print("\n[yellow]This may be a bug. Please report it at:[/yellow]")
        console.print("https://github.com/leotulipan/ocr/issues")

        if verbose:
            import traceback

            console.print("\n[dim]Stack trace:[/dim]")
            console.print(traceback.format_exc())
