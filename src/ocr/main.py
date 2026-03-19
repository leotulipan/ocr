"""Main OCR CLI application."""

import asyncio
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table
from rich.prompt import Confirm
import re
import yaml
from datetime import datetime

from . import __version__
from .models.settings import Settings
from .models.metadata import OCRMetadata
from .adapters.mistral_adapter import MistralOCRAdapter
from .utils.output_manager import OutputManager
from .services.filename_generator import FilenameGenerator
from .utils.cache_manager import CacheManager
from .utils.file_renamer import FileRenamer
from .utils.error_handler import ErrorHandler
from .utils.progress_manager import ProgressManager
from .utils.lock_manager import FileLock
from .services.folder_watcher import FolderWatcher
from .services.processing_queue import ProcessingQueue


app = typer.Typer(no_args_is_help=True)
console = Console()

# Supported file extensions
SUPPORTED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.avif', '.pptx', '.docx'}


def _log_rename(
    file_path: Path,
    new_source: Path,
    new_ocr: Optional[Path],
    filename_metadata,
) -> None:
    """Log a rename event to both frontmatter and directory log file."""
    from_name = file_path.name
    to_name = new_source.name
    confidence = filename_metadata.confidence if filename_metadata else None

    # Log to .ocr/rename.log
    FileRenamer.log_rename_to_file(file_path.parent, from_name, to_name, confidence)

    # Log to OCR markdown frontmatter
    if new_ocr and new_ocr.exists():
        FileRenamer.log_rename_to_frontmatter(new_ocr, from_name, to_name, confidence)


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        console.print(f"OCR version: [cyan]{__version__}[/cyan]")
        raise typer.Exit()


@app.callback()
def callback(
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True, help="Show version and exit"),
):
    """OCR CLI - Process documents with Mistral AI OCR."""
    pass


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


@app.command("run")
def main(
    paths: List[Path] = typer.Argument(..., help="Files or folders to process"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output directory (default: save next to source for single file, ocr_output for multiple)"),
    pages: Optional[str] = typer.Option(None, "--pages", help="Page pattern (e.g., '1-3', '5-', '4,5')"),
    page_headlines: bool = typer.Option(True, "--page-headlines/--no-page-headlines", help="Include page numbers as markdown headlines (default: enabled)"),
    image_descriptions: bool = typer.Option(True, "--image-descriptions/--no-image-descriptions", help="Include AI-generated descriptions for embedded images (default: enabled)"),
    concat: bool = typer.Option(False, "--concat", help="Concatenate multiple files into one output document (treats each file as a page)"),
    rename: bool = typer.Option(False, "--rename", help="Enable intelligent filename generation and renaming"),
    undo: bool = typer.Option(False, "--undo", help="Undo previous renames where confidence was below the threshold"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show suggested filenames without renaming"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before operations"),
    force: bool = typer.Option(False, "--force", help="Force regenerate both OCR and filenames (equivalent to --force-ocr --force-filename)"),
    force_ocr: bool = typer.Option(False, "--force-ocr", help="Force re-OCR even if cached OCR exists"),
    force_filename: bool = typer.Option(False, "--force-filename", help="Force regenerate filename even if cached"),
    confidence: float = typer.Option(0.7, "--confidence", help="Minimum confidence threshold for accepting generated filenames (0.0-1.0, default: 0.7)"),
    filename_model: Optional[str] = typer.Option(None, "--filename-model", help="Model for filename generation (e.g., mistral-small-2506, mistral-large-latest, open-mistral-nemo). Default: mistral-small-2506"),
    verbose: bool = typer.Option(False, "--verbose", help="Show detailed processing information"),
    concurrent: int = typer.Option(3, "--concurrent", help="Number of files to process concurrently (default: 3, max: 10)"),
):
    """Process documents with OCR.

    Examples:
        ocr run document.pdf
        ocr run invoice1.pdf invoice2.pdf
        ocr run ./invoices/
        ocr run *.pdf --rename
        ocr run magazine.pdf --image-descriptions
        ocr run page1.jpg page2.jpg page3.jpg --concat --output combined.md
        ocr run ./folder --undo --confidence 0.2
        ocr run ./folder --undo --confidence 0.2 --dry-run
    """
    # Handle --undo mode before anything else
    if undo:
        _run_undo(paths, confidence, dry_run)
        return

    # Validate concurrent parameter
    if concurrent < 1:
        console.print("[red]Error:[/red] --concurrent must be at least 1")
        raise typer.Exit(1)
    if concurrent > 10:
        console.print("[yellow]Warning:[/yellow] --concurrent capped at 10 for stability")
        concurrent = 10

    # Handle --force as shorthand for both flags
    if force:
        force_ocr = True
        force_filename = True

    asyncio.run(_main(paths, output, pages, page_headlines, image_descriptions, concat, rename, dry_run, confirm, force_ocr, force_filename, confidence, filename_model, verbose, concurrent))


async def _main(
    paths: List[Path],
    output_dir: Optional[Path],
    page_pattern: Optional[str],
    include_page_headlines: bool,
    include_image_descriptions: bool,
    concat: bool,
    rename: bool,
    dry_run: bool,
    confirm: bool,
    force_ocr: bool,
    force_filename: bool,
    confidence_threshold: float,
    filename_model: Optional[str],
    verbose: bool,
    concurrent: int,
):
    """Main processing logic."""
    try:
        # Load settings and create shared Mistral client (Sprint 1: Client Sharing)
        settings = Settings()
        settings.include_image_descriptions = include_image_descriptions

        # Override filename generation model if provided (Sprint 1: Model Selection)
        if filename_model:
            settings.filename_generation_model = filename_model
        from mistralai import Mistral
        shared_client = Mistral(api_key=settings.mistral_api_key.get_secret_value())

        # Expand paths to file list
        files = expand_paths(paths)

        if not files:
            console.print("[red]Error:[/red] No valid files to process")
            raise typer.Exit(1)

        # Check for concat mode
        if concat:
            if len(files) < 2:
                console.print("[red]Error:[/red] --concat requires at least 2 files")
                raise typer.Exit(1)
            if dry_run:
                console.print("[yellow]Warning:[/yellow] --dry-run is ignored in --concat mode")
            await _process_concat_files(
                files, output_dir, page_pattern, include_page_headlines,
                include_image_descriptions, rename, confirm, force_ocr, force_filename, confidence_threshold, verbose, concurrent,
                settings, shared_client
            )
            return

        # Determine processing mode
        is_single_file = len(files) == 1

        # Process files
        if is_single_file:
            await _process_single_file(
                files[0], output_dir, page_pattern, include_page_headlines,
                include_image_descriptions, rename, dry_run, confirm, force_ocr, force_filename, confidence_threshold, verbose,
                settings, shared_client
            )
        else:
            await _process_multiple_files(
                files, output_dir, page_pattern, include_page_headlines,
                include_image_descriptions, rename, dry_run, confirm, force_ocr, force_filename, confidence_threshold, verbose, concurrent,
                settings, shared_client
            )

    except typer.Exit:
        # Re-raise typer.Exit as-is (it's an intentional exit)
        raise
    except Exception as e:
        # Sprint 2: Use error handler with proper exit codes
        exit_code = ErrorHandler.handle_error(e, verbose=verbose)
        raise typer.Exit(exit_code)


def _is_filename_already_correct(file_path: Path, generated_filename: str) -> bool:
    """Check if current filename already matches the generated filename."""
    current_name = file_path.stem  # Filename without extension
    return current_name == generated_filename


def _get_file_dates(file_path: Path) -> tuple[Optional[str], Optional[str]]:
    """Extract file creation and modification dates from filesystem.

    Returns:
        Tuple of (created_date, modified_date) in ISO format (YYYY-MM-DD)
    """
    try:
        # Get file stats
        stat = file_path.stat()

        # Get creation time (st_ctime on Windows is creation time, on Unix it's metadata change time)
        # Use st_birthtime if available (macOS), otherwise use st_ctime
        created_timestamp = getattr(stat, 'st_birthtime', stat.st_ctime)
        created_date = datetime.fromtimestamp(created_timestamp).strftime('%Y-%m-%d')

        # Get modification time
        modified_timestamp = stat.st_mtime
        modified_date = datetime.fromtimestamp(modified_timestamp).strftime('%Y-%m-%d')

        return created_date, modified_date
    except Exception as e:
        # If we can't get dates, return None
        return None, None


async def _generate_filename_for_file(
    file_path: Path,
    ocr_service: MistralOCRAdapter,
    filename_generator: FilenameGenerator,
    output_manager: OutputManager,
    force_ocr: bool,
    force_filename: bool,
    confidence_threshold: float,
    include_page_headlines: bool,
    page_pattern: Optional[str],
    verbose: bool,
) -> tuple[Optional['FilenameMetadata'], Optional[str], int]:
    """Generate filename for a file with smart caching and confidence checking.

    This is the consolidated filename generation logic used by all processing modes
    (single file, batch concurrent, batch sequential).

    Args:
        file_path: Path to the file to process
        ocr_service: OCR service instance (with shared client)
        filename_generator: Filename generator instance (with shared client)
        output_manager: Output manager for saving results
        force_ocr: Force re-OCR even if cached
        force_filename: Force regenerate filename even if cached
        confidence_threshold: Minimum confidence to accept filename (0.0-1.0)
        include_page_headlines: Include page numbers in markdown
        page_pattern: Page selection pattern (e.g., "1-3")
        verbose: Show detailed progress

    Returns:
        Tuple of (filename_metadata, markdown_content, pages_processed)
        Returns (None, None, 0) if file is already correctly named
    """
    from .models.metadata import FilenameMetadata

    # Extract filesystem dates
    file_created_date, file_modified_date = _get_file_dates(file_path)

    # Step 1: Check cache
    cached_filename = CacheManager.get_cached_filename(file_path, force=force_filename)
    if cached_filename and not force_filename:
        if verbose:
            console.print(f"[green]Using cached filename:[/green] {cached_filename.generated_filename}")

        # Check if file is already correctly named
        if _is_filename_already_correct(file_path, cached_filename.generated_filename):
            return None, None, 0  # Signal to skip this file

        return cached_filename, None, 1

    # Step 2: Try to get cached markdown to avoid re-OCR (unless force_ocr is set)
    markdown_content = CacheManager.get_cached_markdown(file_path) if not force_ocr else None
    pages_processed = 1

    if not markdown_content:
        # Step 3: OCR first page only
        if verbose:
            console.print("[yellow]Processing first page for analysis...[/yellow]")
        markdown_content, _ = await ocr_service.process_first_page(file_path, include_page_headlines, include_images=False)
        pages_processed = 1

    # Step 4: Generate filename from first page
    if verbose:
        console.print("[yellow]Analyzing content for filename generation...[/yellow]")
    filename_metadata = await filename_generator.analyze_content(
        markdown_content,
        pages_analyzed=1,
        current_filename=file_path.name,
        file_created_date=file_created_date,
        file_modified_date=file_modified_date
    )

    if verbose:
        console.print(f"[green]Generated filename:[/green] {filename_metadata.generated_filename}")
        console.print(f"[cyan]Confidence:[/cyan] {filename_metadata.confidence}")

    # Step 5: Smart OCR caching - only process remaining pages if confidence is low (Sprint 2)
    if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
        if verbose:
            console.print(f"[yellow]Low confidence ({filename_metadata.confidence}), processing remaining pages...[/yellow]")

        # Smart caching: Only OCR pages 2-N (not re-OCR page 1)
        # Override page_pattern to get pages 2 onwards
        remaining_pages_pattern = "2-"
        remaining_markdown, _, _ = await ocr_service.process_file(file_path, remaining_pages_pattern, include_page_headlines, include_images=False)

        # Concatenate first page + remaining pages
        full_markdown = markdown_content + "\n\n" + remaining_markdown

        # Re-analyze with full document
        filename_metadata = await filename_generator.analyze_content(
            full_markdown,
            pages_analyzed=-1,
            current_filename=file_path.name,
            file_created_date=file_created_date,
            file_modified_date=file_modified_date
        )
        if verbose:
            console.print(f"[green]Updated filename:[/green] {filename_metadata.generated_filename}")
            console.print(f"[cyan]Updated confidence:[/cyan] {filename_metadata.confidence}")
        markdown_content = full_markdown
        pages_processed = -1  # Indicates all pages

    return filename_metadata, markdown_content, pages_processed


async def _process_single_file(
    file_path: Path,
    output_dir: Optional[Path],
    page_pattern: Optional[str],
    include_page_headlines: bool,
    include_image_descriptions: bool,
    rename: bool,
    dry_run: bool,
    confirm: bool,
    force_ocr: bool,
    force_filename: bool,
    confidence_threshold: float,
    verbose: bool,
    settings: Settings,
    shared_client,
):
    """Process a single file with optional filename generation."""
    try:
        # Initialize OCR service with shared client
        ocr_service = MistralOCRAdapter(settings, shared_client)
        # Default: save at input location unless output_dir is provided
        save_at_input_location = output_dir is None
        output_manager = OutputManager(output_dir, save_at_input_location)

        filename_metadata = None
        markdown_content = None
        pages_processed = 1  # Default to single page

        # Filename generation workflow (Sprint 2: Consolidated logic)
        if rename or dry_run:
            if verbose:
                console.print(f"[yellow]Filename generation mode enabled[/yellow]")

            # Initialize filename generator with shared client
            filename_generator = FilenameGenerator(settings, shared_client)

            # Use consolidated filename generation function
            filename_metadata, markdown_content, pages_processed = await _generate_filename_for_file(
                file_path,
                ocr_service,
                filename_generator,
                output_manager,
                force_ocr,
                force_filename,
                confidence_threshold,
                include_page_headlines,
                page_pattern,
                verbose
            )

            # Check if file was skipped (already correctly named)
            if pages_processed == 0:
                if verbose:
                    console.print(f"[green][OK] Already correctly named:[/green] {file_path.name}")
                else:
                    console.print(f"[green][OK] {file_path.name}[/green] (already correct)")
                return

            # Step 6: Save markdown even for dry-run
            if markdown_content:
                output_file, saved_images = await output_manager.save_text_result(
                    markdown_content,
                    file_path.stem,
                    file_path,
                    include_page_headlines,
                    filename_metadata=filename_metadata,
                    pages_processed=pages_processed,
                    copy_to_source_dir=False,  # Don't copy in rename/dry-run workflow
                    skip_images=True  # No image extraction needed for rename
                )
                if verbose:
                    console.print(f"[OK] Saved OCR result to: [blue]{output_file}[/blue]")

            # Step 7: Handle dry-run
            if dry_run:
                if verbose:
                    console.print(f"\n[yellow]DRY RUN - No files will be renamed[/yellow]")
                new_name = filename_generator.generate_filename_with_extension(
                    filename_metadata.generated_filename, file_path
                )
                # Show current -> new filename
                if not verbose and filename_metadata:
                    console.print(f"{file_path.name} -> {new_name} (Confidence: {filename_metadata.confidence})")
                    # Warn if below confidence threshold
                    if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                        console.print(f"  [red]WARNING: Confidence ({filename_metadata.confidence}) below threshold ({confidence_threshold})[/red]")
                elif verbose:
                    console.print(f"[cyan]Current:[/cyan] {file_path.name}")
                    console.print(f"[green]New:[/green] {new_name}")
                    console.print(f"[cyan]Confidence:[/cyan] {filename_metadata.confidence}")
                    # Warn if below confidence threshold
                    if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                        console.print(f"[red]WARNING: Confidence below threshold ({confidence_threshold})[/red]")
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
            if include_page_headlines:
                console.print("Including page headlines: [yellow]enabled[/yellow]")

            result, api_images, pages_processed = await ocr_service.process_file(file_path, page_pattern, include_page_headlines)
        else:
            result = markdown_content
            api_images = 0  # Already counted from cache

        # Save result with filename metadata (if not already saved)
        if not markdown_content or not (rename or dry_run):
            output_file, saved_images = await output_manager.save_text_result(
                result,
                file_path.stem,
                file_path,
                include_page_headlines,
                filename_metadata=filename_metadata,
                pages_processed=pages_processed,
                copy_to_source_dir=not rename  # Copy to source dir when not renaming
            )
            console.print(f"[OK] Saved result to: [blue]{output_file}[/blue]")
            console.print(f"[INFO] API returned {api_images} images, saved {saved_images} images")

        # Perform rename if requested
        if rename and filename_metadata:
            if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                console.print(f"  [yellow]SKIPPED:[/yellow] Confidence ({filename_metadata.confidence}) below threshold ({confidence_threshold})")
            else:
                console.print("\n[yellow]Renaming files...[/yellow]")
                new_source, new_ocr = FileRenamer.rename_file_pair(
                    file_path,
                    filename_metadata.generated_filename,
                    dry_run=False
                )
                _log_rename(file_path, new_source, new_ocr, filename_metadata)
                console.print(f"[OK] Renamed to: [green]{new_source.name}[/green]")
                console.print(f"[OK] OCR file: [green]{new_ocr.name}[/green]")

    except Exception as e:
        console.print(f"[ERROR] Error processing {file_path}: [red]{e}[/red]")
        raise typer.Exit(1)


async def _process_multiple_files(
    files: List[Path],
    output_dir: Optional[Path],
    page_pattern: Optional[str],
    include_page_headlines: bool,
    include_image_descriptions: bool,
    rename: bool,
    dry_run: bool,
    confirm: bool,
    force_ocr: bool,
    force_filename: bool,
    confidence_threshold: float,
    verbose: bool,
    concurrent: int,
    settings: Settings,
    shared_client,
):
    """Process multiple files with optional batch rename and concurrent processing."""
    try:

        # For batch: default to project ocr_output unless user provided --output
        save_at_input_location = False
        output_manager = OutputManager(output_dir, save_at_input_location)

        console.print(f"Processing {len(files)} files...")
        if verbose:
            if page_pattern:
                console.print(f"Page pattern: [yellow]{page_pattern}[/yellow]")
            if include_page_headlines:
                console.print("Including page headlines: [yellow]enabled[/yellow]")
            if include_image_descriptions:
                console.print("Image descriptions: [yellow]enabled[/yellow]")
            if concurrent > 1:
                console.print(f"Concurrent processing: [yellow]{concurrent} files[/yellow]")
            console.print("")  # Add blank line for better readability

        # Check if we can use concurrent processing
        # Cannot use concurrent with confirm+rename (needs sequential user input)
        use_concurrent = concurrent > 1 and not (confirm and rename and not dry_run)

        if use_concurrent and verbose:
            console.print(f"[cyan]Using concurrent processing ({concurrent} workers)[/cyan]")
        elif not use_concurrent and concurrent > 1 and (confirm and rename and not dry_run):
            console.print("[yellow]Sequential mode: --confirm with --rename requires user input per file[/yellow]")

        # Process each file
        results = []
        if verbose and not use_concurrent:
            # Use progress bar in verbose mode
            for file_path in track(files, description="Processing files..."):
                try:
                    # Use single-file logic for each file to support rename/dry-run
                    await _process_single_file(
                        file_path, output_dir, page_pattern, include_page_headlines,
                        include_image_descriptions, rename, dry_run, confirm, force_ocr, force_filename,
                        confidence_threshold, verbose, settings, shared_client
                    )
                    results.append((file_path, "success", None))
                except Exception as e:
                    console.print(f"[ERROR] Error processing {file_path.name}: [red]{e}[/red]")
                    results.append((file_path, "error", str(e)))
        elif use_concurrent:
            # Concurrent processing with semaphore
            import asyncio
            semaphore = asyncio.Semaphore(concurrent)

            # Progress tracking for concurrent operations
            with ProgressManager(verbose=verbose) as progress:
                if verbose:
                    progress.start_task(f"Processing {len(files)} files concurrently", total=len(files))

                async def process_file_with_semaphore(file_path: Path):
                    async with semaphore:
                        try:
                            if rename or dry_run:
                                # Sprint 2: Use consolidated filename generation
                                ocr_service = MistralOCRAdapter(settings, shared_client)
                                filename_generator = FilenameGenerator(settings, shared_client)
                                output_manager = OutputManager(output_dir, save_at_input_location=True)

                                filename_metadata, markdown_content, pages_processed = await _generate_filename_for_file(
                                    file_path,
                                    ocr_service,
                                    filename_generator,
                                    output_manager,
                                    force_ocr,
                                    force_filename,
                                    confidence_threshold,
                                    include_page_headlines,
                                    page_pattern,
                                    verbose=False  # No verbose output in concurrent mode
                                )

                                # Check if file was skipped (already correctly named)
                                if pages_processed == 0:
                                    console.print(f"[green][OK] {file_path.name}[/green] (already correct)")
                                    if verbose:
                                        progress.update()
                                    return (file_path, "skipped", filename_metadata)

                                # Save OCR result BEFORE printing (Ctrl-C resilience)
                                if markdown_content:
                                    await output_manager.save_text_result(
                                        markdown_content,
                                        file_path.stem,
                                        file_path,
                                        include_page_headlines,
                                        filename_metadata,
                                        pages_processed,
                                        copy_to_source_dir=False,  # Don't copy in rename/dry-run workflow
                                        skip_images=True
                                    )

                                # Print simple output - show current -> new filename
                                new_name = filename_generator.generate_filename_with_extension(
                                    filename_metadata.generated_filename, file_path
                                )
                                console.print(f"{file_path.name} -> {new_name} (Confidence: {filename_metadata.confidence})")

                                # Warn if below confidence threshold in dry-run
                                if dry_run and filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                                    console.print(f"  [red]WARNING: Confidence ({filename_metadata.confidence}) below threshold ({confidence_threshold})[/red]")

                                # Perform rename if not dry-run
                                if rename and not dry_run:
                                    if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                                        console.print(f"  [yellow]SKIPPED:[/yellow] Confidence ({filename_metadata.confidence}) below threshold ({confidence_threshold})")
                                    else:
                                        from .utils.file_renamer import FileRenamer
                                        new_source, new_ocr = FileRenamer.rename_file_pair(
                                            file_path,
                                            filename_metadata.generated_filename,
                                            dry_run=False
                                        )
                                        _log_rename(file_path, new_source, new_ocr, filename_metadata)
                                        console.print(f"  [OK] Renamed to: [green]{new_source.name}[/green]")

                                if verbose:
                                    progress.update()
                                return (file_path, "success", filename_metadata)
                            else:
                                # Non-rename mode
                                await _process_single_file(
                                    file_path, output_dir, page_pattern, include_page_headlines,
                                    include_image_descriptions, rename, dry_run, confirm, force_ocr, force_filename,
                                    confidence_threshold, verbose, settings, shared_client
                                )
                                if verbose:
                                    progress.update()
                                return (file_path, "success", None)
                        except Exception as e:
                            console.print(f"[ERROR] Error processing {file_path.name}: [red]{e}[/red]")
                            if verbose:
                                progress.update()
                            return (file_path, "error", str(e))

                # Run all tasks concurrently
                results = await asyncio.gather(*[process_file_with_semaphore(f) for f in files])
                results = list(results)  # Convert to list

        else:
            # Sequential processing without progress bar (non-verbose mode)
            for file_path in files:
                try:
                    # Capture filename metadata for simple output
                    if rename or dry_run:
                        # Sprint 2: Use consolidated filename generation
                        ocr_service = MistralOCRAdapter(settings, shared_client)
                        filename_generator = FilenameGenerator(settings, shared_client)
                        batch_output_manager = OutputManager(output_dir, save_at_input_location=True)

                        filename_metadata, markdown_content, pages_processed = await _generate_filename_for_file(
                            file_path,
                            ocr_service,
                            filename_generator,
                            batch_output_manager,
                            force_ocr,
                            force_filename,
                            confidence_threshold,
                            include_page_headlines,
                            page_pattern,
                            verbose=False  # Simple output in sequential mode
                        )

                        # Check if file was skipped (already correctly named)
                        if pages_processed == 0:
                            console.print(f"[green][OK] {file_path.name}[/green] (already correct)")
                            results.append((file_path, "skipped", None))
                            continue

                        # Save OCR result BEFORE printing (Ctrl-C resilience)
                        if markdown_content:
                            await batch_output_manager.save_text_result(
                                markdown_content,
                                file_path.stem,
                                file_path,
                                include_page_headlines,
                                filename_metadata,
                                pages_processed,
                                copy_to_source_dir=False,  # Don't copy in rename/dry-run workflow
                                skip_images=True
                            )

                        # Handle confirmation for this file
                        if confirm and rename and not dry_run:
                            from .utils.file_renamer import FileRenamer
                            if not FileRenamer.confirm_rename(file_path, filename_metadata.generated_filename):
                                console.print(f"[yellow]Skipped:[/yellow] {file_path.name}")
                                results.append((file_path, "skipped", filename_metadata))
                                continue

                        # Print simple output - show current -> new filename
                        new_name = filename_generator.generate_filename_with_extension(
                            filename_metadata.generated_filename, file_path
                        )
                        console.print(f"{file_path.name} -> {new_name} (Confidence: {filename_metadata.confidence})")

                        # Warn if below confidence threshold in dry-run
                        if dry_run and filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                            console.print(f"  [red]WARNING: Confidence ({filename_metadata.confidence}) below threshold ({confidence_threshold})[/red]")

                        # Perform rename if not dry-run
                        if rename and not dry_run:
                            if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                                console.print(f"  [yellow]SKIPPED:[/yellow] Confidence ({filename_metadata.confidence}) below threshold ({confidence_threshold})")
                            else:
                                from .utils.file_renamer import FileRenamer
                                new_source, new_ocr = FileRenamer.rename_file_pair(
                                    file_path,
                                    filename_metadata.generated_filename,
                                    dry_run=False
                                )
                                _log_rename(file_path, new_source, new_ocr, filename_metadata)
                                console.print(f"  [OK] Renamed to: [green]{new_source.name}[/green]")

                        results.append((file_path, "success", filename_metadata))
                    else:
                        # Non-rename mode
                        await _process_single_file(
                            file_path, output_dir, page_pattern, include_page_headlines,
                            include_image_descriptions, rename, dry_run, confirm, force_ocr, force_filename,
                            confidence_threshold, verbose, settings, shared_client
                        )
                        results.append((file_path, "success", None))
                except Exception as e:
                    console.print(f"[ERROR] Error processing {file_path.name}: [red]{e}[/red]")
                    results.append((file_path, "error", str(e)))

        # Create summary table only in verbose mode
        if verbose:
            table = Table(title="Processing Results")
            table.add_column("File", style="cyan")
            table.add_column("Status", style="green")

            for file_path, status, metadata in results:
                if status == "success":
                    status_text = "[OK] Success"
                elif status == "skipped":
                    status_text = "[OK] Already correct"
                elif status == "error":
                    # Show actual error message if available
                    error_msg = str(metadata)[:50] if metadata else "unknown error"
                    status_text = f"[ERROR] {error_msg}"
                else:
                    status_text = f"[ERROR] {status}"
                table.add_row(file_path.name, status_text)

            console.print(table)

        # Summary line
        success_count = len([r for r in results if r[1] == "success"])
        skipped_count = len([r for r in results if r[1] == "skipped"])
        if verbose or success_count + skipped_count < len(results):
            if skipped_count > 0:
                console.print(f"\n[green]Processed {success_count} / {len(results)} files successfully, {skipped_count} already correct[/green]")
            else:
                console.print(f"\n[green]Processed {success_count} / {len(results)} files successfully[/green]")

    except Exception as e:
        console.print(f"[ERROR] Error: [red]{e}[/red]")
        raise typer.Exit(1)


async def _process_concat_files(
    files: List[Path],
    output_dir: Optional[Path],
    page_pattern: Optional[str],
    include_page_headlines: bool,
    include_image_descriptions: bool,
    rename: bool,
    confirm: bool,
    force_ocr: bool,
    force_filename: bool,
    confidence_threshold: float,
    verbose: bool,
    concurrent: int,
    settings: Settings,
    shared_client,
):
    """Process multiple files and concatenate into one output document."""
    try:
        # Initialize OCR service with shared client
        ocr_service = MistralOCRAdapter(settings, shared_client)

        console.print(f"[yellow]Concatenation mode:[/yellow] Processing {len(files)} files as pages of one document...")
        if page_pattern:
            console.print(f"Page pattern: [yellow]{page_pattern}[/yellow]")
        if include_image_descriptions:
            console.print("Image descriptions: [yellow]enabled[/yellow]")

        # Confirm if requested
        if confirm:
            if not Confirm.ask(f"Process and concatenate {len(files)} files?", default=True):
                console.print("[yellow]Operation cancelled[/yellow]")
                return

        # Process each file, save individual OCR files for caching, and collect markdown
        page_contents = []
        total_images_saved = 0

        # Determine base output directory (.ocr subdirectory for individual files and images)
        base_ocr_dir = files[0].parent / ".ocr"
        base_ocr_dir.mkdir(parents=True, exist_ok=True)

        # Create output manager for saving individual OCR files (for caching)
        individual_output_manager = OutputManager(None, save_at_input_location=True)

        for idx, file_path in enumerate(track(files, description="Processing pages..."), start=1):
            try:
                console.print(f"\n[cyan]Processing page {idx}:[/cyan] {file_path.name}")

                # Process file
                markdown, api_images, _ = await ocr_service.process_file(file_path, page_pattern, False)

                # Save individual OCR file for caching (in .ocr subdirectory)
                individual_output_file, saved_images = await individual_output_manager.save_text_result(
                    markdown,
                    file_path.stem,
                    file_path,
                    include_page_headlines=False,  # No page headlines in individual files
                    filename_metadata=None,
                    pages_processed=1,  # Each file treated as single page for caching
                    copy_to_source_dir=False  # Don't copy in concat mode
                )
                total_images_saved += saved_images

                # Extract just the markdown content (without YAML frontmatter) for concatenation
                # Read the saved file and extract content after frontmatter
                with open(individual_output_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Remove YAML frontmatter
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            markdown_only = parts[2].strip()
                        else:
                            markdown_only = content
                    else:
                        markdown_only = content

                # Add page header for concatenation
                page_header = f"### Page {idx}\n\n"
                page_content = page_header + markdown_only

                page_contents.append(page_content)
                console.print(f"  [green]Page {idx} processed[/green] (OCR file: {individual_output_file.name}, {saved_images} images)")

            except Exception as e:
                console.print(f"  [ERROR] Error processing {file_path.name}: [red]{e}[/red]")
                page_contents.append(f"### Page {idx}\n\n**Error processing this page:** {e}\n")

        # Combine all pages
        combined_markdown = "\n\n".join(page_contents)

        # Clean up empty images directory if no images were saved
        images_dir = base_ocr_dir / "images"
        if total_images_saved == 0 and images_dir.exists():
            try:
                images_dir.rmdir()
                console.print(f"[INFO] Removed empty images directory")
            except OSError:
                pass  # Directory not empty or other issue, skip

        # Determine output location and filename (save in parent directory, not .ocr)
        if output_dir:
            output_file = output_dir / f"{files[0].stem}.md"
        else:
            # Save in the directory of the first file (not in .ocr subdirectory)
            output_file = files[0].parent / f"{files[0].stem}.md"

        # Handle rename mode
        filename_metadata = None
        if rename:
            if verbose:
                console.print(f"\n[yellow]Generating intelligent filename for concatenated document...[/yellow]")
            filename_generator = FilenameGenerator(settings, shared_client)
            # Extract filesystem dates from first file
            file_created_date, file_modified_date = _get_file_dates(files[0])
            # Use first file's name as current_filename for context
            filename_metadata = await filename_generator.analyze_content(
                combined_markdown,
                pages_analyzed=len(files),
                current_filename=files[0].name,
                file_created_date=file_created_date,
                file_modified_date=file_modified_date
            )
            if verbose:
                console.print(f"[green]Generated filename:[/green] {filename_metadata.generated_filename}")
                console.print(f"[cyan]Confidence:[/cyan] {filename_metadata.confidence}")
            else:
                console.print(f"{filename_metadata.generated_filename} (Confidence: {filename_metadata.confidence})")

            # Update output filename
            output_file = output_file.parent / f"{filename_metadata.generated_filename}.md"

            # Confirm if requested
            if confirm:
                new_name = f"{filename_metadata.generated_filename}.md"
                if not Confirm.ask(f"Use filename '{new_name}'?", default=True):
                    console.print("[yellow]Using original filename instead[/yellow]")
                    output_file = files[0].parent / f"{files[0].stem}.md"
                    filename_metadata = None

        # Create metadata
        metadata = OCRMetadata(
            source_file=", ".join([str(f) for f in files]),
            original_filename=", ".join([f.name for f in files]),
            processed_at=datetime.now(),
            content_length=len(combined_markdown),
            include_page_headlines=True,  # Always true for concat mode
            images_saved=total_images_saved,
            filename_metadata=filename_metadata
        )

        # Serialize to YAML frontmatter
        yaml_dict = metadata.to_yaml_dict()
        yaml_content = yaml.dump(yaml_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
        header = f"---\n{yaml_content}---\n\n"

        # Write output
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(combined_markdown)

        console.print(f"\n[OK] Concatenated {len(files)} pages into: [blue]{output_file}[/blue]")
        console.print(f"[INFO] Total images saved: {total_images_saved}")
        console.print(f"[INFO] Individual OCR files saved in: [blue]{base_ocr_dir}[/blue]")

    except Exception as e:
        console.print(f"[ERROR] Error in concatenation: [red]{e}[/red]")
        raise typer.Exit(1)


@app.command()
def watch(
    folder: Path = typer.Argument(..., help="Folder to watch for new files"),
    rename: bool = typer.Option(False, "--rename", help="Automatically rename files with intelligent filenames"),
    concurrent: int = typer.Option(3, "--concurrent", "-c", min=1, max=10, help="Number of concurrent files to process"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Watch subdirectories recursively"),
    confidence_threshold: float = typer.Option(0.7, "--confidence", min=0.0, max=1.0, help="Minimum confidence threshold for filename generation"),
    filename_model: str = typer.Option("mistral-small-2506", "--filename-model", help="Model to use for filename generation"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Watch a folder for new files and process them automatically.

    Monitors the specified folder for new files and automatically processes them
    with OCR. Optionally renames files with intelligent filenames based on content.

    Example:
        ocr watch ~/Downloads --rename --concurrent 5
    """
    try:
        # Validate folder exists
        if not folder.exists():
            console.print(f"[red]Error:[/red] Folder does not exist: {folder}")
            raise typer.Exit(1)

        if not folder.is_dir():
            console.print(f"[red]Error:[/red] Path is not a directory: {folder}")
            raise typer.Exit(1)

        # Load settings
        settings = Settings()

        # Override filename generation model if specified
        if filename_model != "mistral-small-2506":
            settings.filename_generation_model = filename_model

        # Create shared Mistral client
        from mistralai import Mistral
        shared_client = Mistral(api_key=settings.mistral_api_key.get_secret_value())

        console.print(f"\n[cyan]Watch Mode[/cyan]")
        console.print(f"Folder: [blue]{folder.absolute()}[/blue]")
        console.print(f"Rename: [yellow]{'enabled' if rename else 'disabled'}[/yellow]")
        console.print(f"Concurrent: [yellow]{concurrent} files[/yellow]")
        console.print(f"Recursive: [yellow]{'yes' if recursive else 'no'}[/yellow]")
        if rename:
            console.print(f"Confidence threshold: [yellow]{confidence_threshold}[/yellow]")
        console.print()

        # Create processing queue
        queue = ProcessingQueue(max_concurrent=concurrent)

        # Define file processor
        async def process_file_with_lock(file_path: Path):
            """Process a file with lock to prevent duplicates."""
            # Use file lock to prevent duplicate processing
            with FileLock(file_path) as locked:
                if not locked:
                    console.print(f"[yellow]Skipped (locked): {file_path.name}[/yellow]")
                    return

                console.print(f"[cyan]Processing: {file_path.name}[/cyan]")

                # Create components for this file
                ocr_service = MistralOCRAdapter(settings, shared_client)
                output_manager = OutputManager(save_at_input_location=True)

                if rename:
                    # Process with filename generation
                    filename_generator = FilenameGenerator(settings, shared_client)

                    filename_metadata, markdown_content, pages_processed = await _generate_filename_for_file(
                        file_path,
                        ocr_service,
                        filename_generator,
                        output_manager,
                        force_ocr=False,
                        force_filename=False,
                        confidence_threshold=confidence_threshold,
                        include_page_headlines=False,
                        page_pattern=None,
                        verbose=verbose
                    )

                    # Skip if already correctly named
                    if pages_processed == 0:
                        console.print(f"[green][OK] {file_path.name}[/green] (already correct)")
                        return

                    # Perform rename (gate on confidence threshold)
                    if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                        console.print(f"  [yellow]SKIPPED:[/yellow] Confidence ({filename_metadata.confidence}) below threshold ({confidence_threshold})")
                    else:
                        new_source, new_ocr = FileRenamer.rename_file_pair(
                            file_path,
                            filename_metadata.generated_filename,
                            dry_run=False
                        )
                        # Mark renamed paths as processed to prevent re-triggering
                        watcher.mark_processed(new_source)
                        if new_ocr:
                            watcher.mark_processed(new_ocr)
                        _log_rename(file_path, new_source, new_ocr, filename_metadata)
                        console.print(f"[green][OK] Renamed to: {new_source.name}[/green] (Confidence: {filename_metadata.confidence})")
                else:
                    # Process without renaming
                    markdown, api_images, pages_count = await ocr_service.process_file(file_path, None, False)
                    output_file, saved_images = await output_manager.save_text_result(
                        markdown,
                        file_path.stem,
                        file_path,
                        include_page_headlines=False,
                        filename_metadata=None,
                        pages_processed=pages_count,
                        copy_to_source_dir=True  # Copy to source dir in watch mode without rename
                    )
                    console.print(f"[green][OK] Processed: {file_path.name}[/green]")

        # Define callback for new files
        async def on_file_ready(file_path: Path):
            """Called when a new file is ready for processing."""
            queue.add_job(file_path)

        # Create folder watcher
        watcher = FolderWatcher(
            folder_path=folder,
            on_file_ready=on_file_ready,
            recursive=recursive
        )

        # Start watch mode
        async def run_watch():
            """Run watch mode with queue processing."""
            queue.start(process_file_with_lock)
            watcher.start(asyncio.get_running_loop())

            console.print("[green]Press Ctrl+C to stop watching[/green]\n")

            try:
                # Keep running until interrupted
                while True:
                    await asyncio.sleep(1)

                    # Show stats periodically (every 30 seconds)
                    stats = queue.get_stats()
                    if stats["total"] > 0 and stats["total"] % 10 == 0:
                        console.print(f"[dim]Stats: {stats['completed']} completed, {stats['processing']} processing, {stats['failed']} failed[/dim]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping watch mode...[/yellow]")
                watcher.stop()
                await queue.stop()

                # Show final stats
                stats = queue.get_stats()
                console.print(f"\n[cyan]Final Stats:[/cyan]")
                console.print(f"  Completed: [green]{stats['completed']}[/green]")
                console.print(f"  Failed: [red]{stats['failed']}[/red]")
                console.print(f"  Total: {stats['total']}")

        # Run in asyncio event loop
        asyncio.run(run_watch())

    except KeyboardInterrupt:
        console.print("\n[yellow]Watch mode stopped[/yellow]")
        raise typer.Exit(0)
    except typer.Exit:
        # Re-raise typer.Exit as-is (it's an intentional exit)
        raise
    except Exception as e:
        exit_code = ErrorHandler.handle_error(e, verbose=verbose)
        raise typer.Exit(exit_code)


def _run_undo(paths: List[Path], confidence: float, dry_run: bool) -> None:
    """Undo previous renames where confidence was at or below the given threshold."""
    all_ocr_files: list[Path] = []

    for path in paths:
        if path.is_dir():
            ocr_dir = path / ".ocr"
            if ocr_dir.exists():
                all_ocr_files.extend(ocr_dir.glob("*.md"))
        elif path.is_file():
            ocr_file = CacheManager.get_cached_ocr_file(path)
            if ocr_file:
                all_ocr_files.append(ocr_file)
            else:
                console.print(f"[yellow]Warning:[/yellow] No OCR file found for {path}")

    if not all_ocr_files:
        console.print("[yellow]No OCR files found to check.[/yellow]")
        return

    undo_count = 0
    skip_count = 0

    for ocr_file in all_ocr_files:
        metadata = CacheManager.extract_metadata(ocr_file)
        if not metadata or not metadata.rename_history:
            continue

        last_rename = metadata.rename_history[-1]

        if last_rename.confidence is None or last_rename.confidence > confidence:
            continue

        current_name = last_rename.to_name
        original_name = last_rename.from_name

        source_dir = ocr_file.parent.parent if ocr_file.parent.name == ".ocr" else ocr_file.parent
        current_source = source_dir / current_name

        if not current_source.exists():
            console.print(f"[yellow]SKIP:[/yellow] {current_name} (file not found at {current_source})")
            skip_count += 1
            continue

        original_stem = Path(original_name).stem

        if dry_run:
            console.print(f"{current_name} -> {original_name} (Confidence: {last_rename.confidence}) [DRY RUN]")
            undo_count += 1
        else:
            try:
                new_source, new_ocr = FileRenamer.rename_file_pair(
                    current_source,
                    original_stem,
                    dry_run=False
                )
                _log_rename(current_source, new_source, new_ocr, None)
                console.print(f"{current_name} -> {new_source.name} [UNDONE] (was confidence: {last_rename.confidence})")
                undo_count += 1
            except Exception as e:
                console.print(f"[red]ERROR:[/red] Failed to undo {current_name}: {e}")
                skip_count += 1

    action = "Would undo" if dry_run else "Undone"
    console.print(f"\n[green]{action}: {undo_count} file(s)[/green]")
    if skip_count > 0:
        console.print(f"[yellow]Skipped: {skip_count} file(s)[/yellow]")


if __name__ == "__main__":
    app()
