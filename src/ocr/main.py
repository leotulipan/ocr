"""Main OCR CLI application."""

import asyncio
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table
from rich.prompt import Confirm

from . import __version__
from .models.settings import Settings
from .adapters.mistral_adapter import MistralOCRAdapter
from .utils.output_manager import OutputManager
from .services.filename_generator import FilenameGenerator
from .utils.cache_manager import CacheManager
from .utils.file_renamer import FileRenamer


app = typer.Typer()
console = Console()

# Supported file extensions
SUPPORTED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.avif', '.pptx', '.docx'}


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        console.print(f"OCR version: [cyan]{__version__}[/cyan]")
        raise typer.Exit()


def expand_paths(paths: List[Path]) -> List[Path]:
    """Expand paths to file list. Folders are expanded to all supported files."""
    files = []
    for path in paths:
        if not path.exists():
            console.print(f"[red]Error:[/red] Path does not exist: {path}")
            continue

        if path.is_file():
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)
            else:
                console.print(f"[yellow]Warning:[/yellow] Unsupported file type: {path}")
        elif path.is_dir():
            # Find all supported files in directory
            dir_files = [
                f for f in path.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
            ]
            if dir_files:
                files.extend(dir_files)
            else:
                console.print(f"[yellow]Warning:[/yellow] No supported files found in: {path}")

    return files


@app.command()
def main(
    paths: List[Path] = typer.Argument(..., help="Files or folders to process"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output directory (default: save next to source for single file, ocr_output for multiple)"),
    pages: Optional[str] = typer.Option(None, "--pages", help="Page pattern (e.g., '1-3', '5-', '4,5')"),
    page_headlines: bool = typer.Option(False, "--page-headlines", help="Include page numbers as markdown headlines"),
    rename: bool = typer.Option(False, "--rename", help="Enable intelligent filename generation and renaming"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show suggested filenames without renaming"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before operations"),
    force: bool = typer.Option(False, "--force", help="Force regenerate filenames even if cached"),
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True, help="Show version and exit"),
):
    """OCR CLI - Process documents with Mistral AI.

    Examples:
        ocr document.pdf
        ocr invoice1.pdf invoice2.pdf
        ocr ./invoices/
        ocr *.pdf --rename
    """
    asyncio.run(_main(paths, output, pages, page_headlines, rename, dry_run, confirm, force))


async def _main(
    paths: List[Path],
    output_dir: Optional[Path],
    page_pattern: Optional[str],
    include_page_headlines: bool,
    rename: bool,
    dry_run: bool,
    confirm: bool,
    force: bool,
):
    """Main processing logic."""
    try:
        # Expand paths to file list
        files = expand_paths(paths)

        if not files:
            console.print("[red]Error:[/red] No valid files to process")
            raise typer.Exit(1)

        # Determine processing mode
        is_single_file = len(files) == 1

        # Batch confirmation
        if confirm and not is_single_file:
            if not Confirm.ask(f"Process {len(files)} files?", default=True):
                console.print("[yellow]Operation cancelled[/yellow]")
                return

        # Process files
        if is_single_file:
            await _process_single_file(
                files[0], output_dir, page_pattern, include_page_headlines,
                rename, dry_run, confirm, force
            )
        else:
            await _process_multiple_files(
                files, output_dir, page_pattern, include_page_headlines,
                rename, dry_run, confirm, force
            )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


async def _process_single_file(
    file_path: Path,
    output_dir: Optional[Path],
    page_pattern: Optional[str],
    include_page_headlines: bool,
    rename: bool,
    dry_run: bool,
    confirm: bool,
    force: bool,
):
    """Process a single file with optional filename generation."""
    try:
        # Load settings
        settings = Settings()

        # Initialize OCR service
        ocr_service = MistralOCRAdapter(settings)
        # Default: save at input location unless output_dir is provided
        save_at_input_location = output_dir is None
        output_manager = OutputManager(output_dir, save_at_input_location)

        filename_metadata = None
        markdown_content = None
        pages_processed = 1  # Default to single page

        # Filename generation workflow
        if rename or dry_run:
            console.print(f"[yellow]Filename generation mode enabled[/yellow]")

            # Step 1: Check cache
            cached_filename = CacheManager.get_cached_filename(file_path, force=force)
            if cached_filename and not force:
                console.print(f"[green]Using cached filename:[/green] {cached_filename.generated_filename}")
                filename_metadata = cached_filename
            else:
                # Step 2: Try to get cached markdown to avoid re-OCR
                markdown_content = CacheManager.get_cached_markdown(file_path)

                if not markdown_content:
                    # Step 3: OCR first page only
                    console.print("[yellow]Processing first page for analysis...[/yellow]")
                    markdown_content, _ = await ocr_service.process_first_page(file_path, include_page_headlines)
                    pages_processed = 1

                # Step 4: Generate filename
                console.print("[yellow]Analyzing content for filename generation...[/yellow]")
                filename_generator = FilenameGenerator(settings)
                filename_metadata = await filename_generator.analyze_content(markdown_content, pages_analyzed=1)

                console.print(f"[green]Generated filename:[/green] {filename_metadata.generated_filename}")
                console.print(f"[cyan]Confidence:[/cyan] {filename_metadata.confidence}")

                # Step 5: Check if first page analysis was sufficient
                if filename_metadata.confidence == "low":
                    console.print("[yellow]Low confidence, processing all pages...[/yellow]")
                    full_markdown, _ = await ocr_service.process_file(file_path, page_pattern, include_page_headlines)
                    filename_metadata = await filename_generator.analyze_content(full_markdown, pages_analyzed=-1)
                    console.print(f"[green]Updated filename:[/green] {filename_metadata.generated_filename}")
                    markdown_content = full_markdown
                    pages_processed = -1  # Indicates all pages

            # Step 6: Save markdown even for dry-run
            if markdown_content:
                output_file, saved_images = output_manager.save_text_result(
                    markdown_content,
                    file_path.stem,
                    file_path,
                    include_page_headlines,
                    filename_metadata=filename_metadata,
                    pages_processed=pages_processed
                )
                console.print(f"✓ Saved OCR result to: [blue]{output_file}[/blue]")

            # Step 7: Handle dry-run
            if dry_run:
                console.print(f"\n[yellow]DRY RUN - No files will be renamed[/yellow]")
                new_name = filename_generator.generate_filename_with_extension(
                    filename_metadata.generated_filename, file_path
                )
                console.print(f"[green]Suggested filename:[/green] {new_name}")
                return

            # Step 8: Handle confirmation
            if confirm:
                if not FileRenamer.confirm_rename(file_path, filename_metadata.generated_filename):
                    console.print("[yellow]Rename cancelled by user[/yellow]")
                    rename = False

        # Standard OCR processing (if not in rename/dry-run mode or markdown not cached)
        if not markdown_content:
            console.print(f"Processing file: [green]{file_path}[/green]")
            if page_pattern:
                console.print(f"Page pattern: [yellow]{page_pattern}[/yellow]")
                # Determine pages processed from pattern (simplified - just check if it's "1")
                pages_processed = 1 if page_pattern == "1" else -1
            if include_page_headlines:
                console.print("Including page headlines: [yellow]enabled[/yellow]")

            result, api_images = await ocr_service.process_file(file_path, page_pattern, include_page_headlines)
        else:
            result = markdown_content
            api_images = 0  # Already counted from cache

        # Save result with filename metadata (if not already saved)
        if not markdown_content or not (rename or dry_run):
            output_file, saved_images = output_manager.save_text_result(
                result,
                file_path.stem,
                file_path,
                include_page_headlines,
                filename_metadata=filename_metadata,
                pages_processed=pages_processed
            )
            console.print(f"✓ Saved result to: [blue]{output_file}[/blue]")
            console.print(f"📊 API returned {api_images} images, saved {saved_images} images")

        # Perform rename if requested
        if rename and filename_metadata:
            console.print("\n[yellow]Renaming files...[/yellow]")
            new_source, new_ocr = FileRenamer.rename_file_pair(
                file_path,
                filename_metadata.generated_filename,
                dry_run=False
            )
            console.print(f"✓ Renamed to: [green]{new_source.name}[/green]")
            console.print(f"✓ OCR file: [green]{new_ocr.name}[/green]")

    except Exception as e:
        console.print(f"❌ Error processing {file_path}: [red]{e}[/red]")
        raise typer.Exit(1)


async def _process_multiple_files(
    files: List[Path],
    output_dir: Optional[Path],
    page_pattern: Optional[str],
    include_page_headlines: bool,
    rename: bool,
    dry_run: bool,
    confirm: bool,
    force: bool,
):
    """Process multiple files with optional batch rename."""
    try:
        # Load settings
        settings = Settings()

        # For batch: default to project ocr_output unless user provided --output
        save_at_input_location = False
        output_manager = OutputManager(output_dir, save_at_input_location)

        console.print(f"Processing {len(files)} files...")
        if page_pattern:
            console.print(f"Page pattern: [yellow]{page_pattern}[/yellow]")
        if include_page_headlines:
            console.print("Including page headlines: [yellow]enabled[/yellow]")

        # Process each file
        results = []
        for file_path in track(files, description="Processing files..."):
            try:
                # Use single-file logic for each file to support rename/dry-run
                await _process_single_file(
                    file_path, output_dir, page_pattern, include_page_headlines,
                    rename, dry_run, confirm, force
                )
                results.append((file_path, "success"))
            except Exception as e:
                console.print(f"❌ Error processing {file_path.name}: [red]{e}[/red]")
                results.append((file_path, f"error: {e}"))

        # Create summary table
        table = Table(title="Processing Results")
        table.add_column("File", style="cyan")
        table.add_column("Status", style="green")

        for file_path, status in results:
            status_text = "✓ Success" if status == "success" else f"❌ {status}"
            table.add_row(file_path.name, status_text)

        console.print(table)
        console.print(f"[green]Processed {len([r for r in results if r[1] == 'success'])} / {len(results)} files successfully[/green]")

    except Exception as e:
        console.print(f"❌ Error: [red]{e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
