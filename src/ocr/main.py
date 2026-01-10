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
    image_descriptions: bool = typer.Option(True, "--image-descriptions/--no-image-descriptions", help="Include AI-generated descriptions for embedded images (default: enabled)"),
    concat: bool = typer.Option(False, "--concat", help="Concatenate multiple files into one output document (treats each file as a page)"),
    rename: bool = typer.Option(False, "--rename", help="Enable intelligent filename generation and renaming"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show suggested filenames without renaming"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before operations"),
    force: bool = typer.Option(False, "--force", help="Force regenerate filenames even if cached"),
    confidence: float = typer.Option(0.7, "--confidence", help="Minimum confidence threshold for accepting generated filenames (0.0-1.0, default: 0.7)"),
    verbose: bool = typer.Option(False, "--verbose", help="Show detailed processing information"),
    concurrent: int = typer.Option(3, "--concurrent", help="Number of files to process concurrently (default: 3, max: 10)"),
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True, help="Show version and exit"),
):
    """OCR CLI - Process documents with Mistral AI.

    Examples:
        ocr document.pdf
        ocr invoice1.pdf invoice2.pdf
        ocr ./invoices/
        ocr *.pdf --rename
        ocr magazine.pdf --image-descriptions
        ocr page1.jpg page2.jpg page3.jpg --concat --output combined.md
    """
    # Validate concurrent parameter
    if concurrent < 1:
        console.print("[red]Error:[/red] --concurrent must be at least 1")
        raise typer.Exit(1)
    if concurrent > 10:
        console.print("[yellow]Warning:[/yellow] --concurrent capped at 10 for stability")
        concurrent = 10

    asyncio.run(_main(paths, output, pages, page_headlines, image_descriptions, concat, rename, dry_run, confirm, force, confidence, verbose, concurrent))


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
    force: bool,
    confidence_threshold: float,
    verbose: bool,
    concurrent: int,
):
    """Main processing logic."""
    try:
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
                include_image_descriptions, rename, confirm, force, confidence_threshold, verbose, concurrent
            )
            return

        # Determine processing mode
        is_single_file = len(files) == 1

        # Process files
        if is_single_file:
            await _process_single_file(
                files[0], output_dir, page_pattern, include_page_headlines,
                include_image_descriptions, rename, dry_run, confirm, force, confidence_threshold, verbose
            )
        else:
            await _process_multiple_files(
                files, output_dir, page_pattern, include_page_headlines,
                include_image_descriptions, rename, dry_run, confirm, force, confidence_threshold, verbose, concurrent
            )

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _is_filename_already_correct(file_path: Path, generated_filename: str) -> bool:
    """Check if current filename already matches the generated filename."""
    current_name = file_path.stem  # Filename without extension
    return current_name == generated_filename


async def _process_single_file(
    file_path: Path,
    output_dir: Optional[Path],
    page_pattern: Optional[str],
    include_page_headlines: bool,
    include_image_descriptions: bool,
    rename: bool,
    dry_run: bool,
    confirm: bool,
    force: bool,
    confidence_threshold: float,
    verbose: bool,
):
    """Process a single file with optional filename generation."""
    try:
        # Load settings
        settings = Settings()
        settings.include_image_descriptions = include_image_descriptions

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
            if verbose:
                console.print(f"[yellow]Filename generation mode enabled[/yellow]")

            # Initialize filename generator
            filename_generator = FilenameGenerator(settings)

            # Step 1: Check cache
            cached_filename = CacheManager.get_cached_filename(file_path, force=force)
            if cached_filename and not force:
                if verbose:
                    console.print(f"[green]Using cached filename:[/green] {cached_filename.generated_filename}")
                filename_metadata = cached_filename

                # Check if file is already correctly named
                if _is_filename_already_correct(file_path, filename_metadata.generated_filename):
                    if verbose:
                        console.print(f"[green][OK] Already correctly named:[/green] {file_path.name}")
                    else:
                        console.print(f"[green][OK] {file_path.name}[/green] (already correct)")
                    return
            else:
                # Step 2: Try to get cached markdown to avoid re-OCR
                markdown_content = CacheManager.get_cached_markdown(file_path)

                if not markdown_content:
                    # Step 3: OCR first page only
                    if verbose:
                        console.print("[yellow]Processing first page for analysis...[/yellow]")
                    markdown_content, _ = await ocr_service.process_first_page(file_path, include_page_headlines)
                    pages_processed = 1

                # Step 4: Generate filename
                if verbose:
                    console.print("[yellow]Analyzing content for filename generation...[/yellow]")
                filename_metadata = await filename_generator.analyze_content(
                    markdown_content,
                    pages_analyzed=1,
                    current_filename=file_path.name
                )

                if verbose:
                    console.print(f"[green]Generated filename:[/green] {filename_metadata.generated_filename}")
                    console.print(f"[cyan]Confidence:[/cyan] {filename_metadata.confidence}")

                # Step 5: Check if first page analysis was sufficient
                # Use confidence_threshold for determining if full document processing is needed
                if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                    if verbose:
                        console.print(f"[yellow]Low confidence ({filename_metadata.confidence}), processing all pages...[/yellow]")
                    full_markdown, _ = await ocr_service.process_file(file_path, page_pattern, include_page_headlines)
                    filename_metadata = await filename_generator.analyze_content(
                        full_markdown,
                        pages_analyzed=-1,
                        current_filename=file_path.name
                    )
                    if verbose:
                        console.print(f"[green]Updated filename:[/green] {filename_metadata.generated_filename}")
                        console.print(f"[cyan]Updated confidence:[/cyan] {filename_metadata.confidence}")
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
                elif verbose:
                    console.print(f"[cyan]Current:[/cyan] {file_path.name}")
                    console.print(f"[green]New:[/green] {new_name}")
                    console.print(f"[cyan]Confidence:[/cyan] {filename_metadata.confidence}")
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
            console.print(f"[OK] Saved result to: [blue]{output_file}[/blue]")
            console.print(f"[INFO] API returned {api_images} images, saved {saved_images} images")

        # Perform rename if requested
        if rename and filename_metadata:
            console.print("\n[yellow]Renaming files...[/yellow]")
            new_source, new_ocr = FileRenamer.rename_file_pair(
                file_path,
                filename_metadata.generated_filename,
                dry_run=False
            )
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
    force: bool,
    confidence_threshold: float,
    verbose: bool,
    concurrent: int,
):
    """Process multiple files with optional batch rename and concurrent processing."""
    try:
        # Load settings
        settings = Settings()
        settings.include_image_descriptions = include_image_descriptions

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
                        include_image_descriptions, rename, dry_run, confirm, force,
                        confidence_threshold, verbose
                    )
                    results.append((file_path, "success", None))
                except Exception as e:
                    console.print(f"[ERROR] Error processing {file_path.name}: [red]{e}[/red]")
                    results.append((file_path, "error", str(e)))
        elif use_concurrent:
            # Concurrent processing with semaphore
            import asyncio
            semaphore = asyncio.Semaphore(concurrent)

            async def process_file_with_semaphore(file_path: Path):
                async with semaphore:
                    try:
                        # Capture filename metadata for simple output
                        filename_generator = FilenameGenerator(settings) if (rename or dry_run) else None

                        if rename or dry_run:
                            # Quick filename generation
                            cached_filename = CacheManager.get_cached_filename(file_path, force=force)
                            if cached_filename and not force:
                                filename_metadata = cached_filename

                                # Check if file is already correctly named
                                if _is_filename_already_correct(file_path, filename_metadata.generated_filename):
                                    console.print(f"[green][OK] {file_path.name}[/green] (already correct)")
                                    return (file_path, "skipped", filename_metadata)
                            else:
                                markdown_content = CacheManager.get_cached_markdown(file_path)
                                if not markdown_content:
                                    ocr_service = MistralOCRAdapter(settings)
                                    markdown_content, _ = await ocr_service.process_first_page(file_path, include_page_headlines)

                                filename_metadata = await filename_generator.analyze_content(
                                    markdown_content,
                                    pages_analyzed=1,
                                    current_filename=file_path.name
                                )

                                # Check confidence and process all pages if needed
                                if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                                    ocr_service = MistralOCRAdapter(settings)
                                    full_markdown, _ = await ocr_service.process_file(file_path, page_pattern, include_page_headlines)
                                    filename_metadata = await filename_generator.analyze_content(
                                        full_markdown,
                                        pages_analyzed=-1,
                                        current_filename=file_path.name
                                    )

                            # Print simple output - show current -> new filename
                            new_name = filename_generator.generate_filename_with_extension(
                                filename_metadata.generated_filename, file_path
                            )
                            console.print(f"{file_path.name} -> {new_name} (Confidence: {filename_metadata.confidence})")

                            # Perform rename if not dry-run
                            if rename and not dry_run:
                                from .utils.file_renamer import FileRenamer
                                new_source, new_ocr = FileRenamer.rename_file_pair(
                                    file_path,
                                    filename_metadata.generated_filename,
                                    dry_run=False
                                )
                                console.print(f"  [OK] Renamed to: [green]{new_source.name}[/green]")

                            return (file_path, "success", filename_metadata)
                        else:
                            # Non-rename mode
                            await _process_single_file(
                                file_path, output_dir, page_pattern, include_page_headlines,
                                include_image_descriptions, rename, dry_run, confirm, force,
                                confidence_threshold, verbose
                            )
                            return (file_path, "success", None)
                    except Exception as e:
                        console.print(f"[ERROR] Error processing {file_path.name}: [red]{e}[/red]")
                        return (file_path, "error", str(e))

            # Run all tasks concurrently
            results = await asyncio.gather(*[process_file_with_semaphore(f) for f in files])
            results = list(results)  # Convert to list

        else:
            # Sequential processing without progress bar (non-verbose mode)
            for file_path in files:
                try:
                    # Capture filename metadata for simple output
                    filename_generator = FilenameGenerator(settings) if (rename or dry_run) else None

                    if rename or dry_run:
                        # Quick filename generation
                        cached_filename = CacheManager.get_cached_filename(file_path, force=force)
                        if cached_filename and not force:
                            filename_metadata = cached_filename

                            # Check if file is already correctly named
                            if _is_filename_already_correct(file_path, filename_metadata.generated_filename):
                                console.print(f"[green][OK] {file_path.name}[/green] (already correct)")
                                results.append((file_path, "skipped", filename_metadata))
                                continue
                        else:
                            markdown_content = CacheManager.get_cached_markdown(file_path)
                            if not markdown_content:
                                ocr_service = MistralOCRAdapter(settings)
                                markdown_content, _ = await ocr_service.process_first_page(file_path, include_page_headlines)

                            filename_metadata = await filename_generator.analyze_content(
                                markdown_content,
                                pages_analyzed=1,
                                current_filename=file_path.name
                            )

                            # Check confidence and process all pages if needed
                            if filename_metadata.confidence is not None and filename_metadata.confidence < confidence_threshold:
                                ocr_service = MistralOCRAdapter(settings)
                                full_markdown, _ = await ocr_service.process_file(file_path, page_pattern, include_page_headlines)
                                filename_metadata = await filename_generator.analyze_content(
                                    full_markdown,
                                    pages_analyzed=-1,
                                    current_filename=file_path.name
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

                        # Perform rename if not dry-run
                        if rename and not dry_run:
                            from .utils.file_renamer import FileRenamer
                            new_source, new_ocr = FileRenamer.rename_file_pair(
                                file_path,
                                filename_metadata.generated_filename,
                                dry_run=False
                            )
                            console.print(f"  [OK] Renamed to: [green]{new_source.name}[/green]")

                        results.append((file_path, "success", filename_metadata))
                    else:
                        # Non-rename mode
                        await _process_single_file(
                            file_path, output_dir, page_pattern, include_page_headlines,
                            include_image_descriptions, rename, dry_run, confirm, force,
                            confidence_threshold, verbose
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

            for file_path, status, _ in results:
                if status == "success":
                    status_text = "[OK] Success"
                elif status == "skipped":
                    status_text = "[OK] Already correct"
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
    force: bool,
    confidence_threshold: float,
    verbose: bool,
    concurrent: int,
):
    """Process multiple files and concatenate into one output document."""
    try:
        # Load settings
        settings = Settings()
        settings.include_image_descriptions = include_image_descriptions

        # Initialize OCR service
        ocr_service = MistralOCRAdapter(settings)

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
                markdown, api_images = await ocr_service.process_file(file_path, page_pattern, False)

                # Save individual OCR file for caching (in .ocr subdirectory)
                individual_output_file, saved_images = individual_output_manager.save_text_result(
                    markdown,
                    file_path.stem,
                    file_path,
                    include_page_headlines=False,  # No page headlines in individual files
                    filename_metadata=None,
                    pages_processed=1  # Each file treated as single page for caching
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
            filename_generator = FilenameGenerator(settings)
            # Use first file's name as current_filename for context
            filename_metadata = await filename_generator.analyze_content(
                combined_markdown,
                pages_analyzed=len(files),
                current_filename=files[0].name
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


if __name__ == "__main__":
    app()
