"""Main OCR CLI application."""

import asyncio
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

from . import __version__
from .models.settings import Settings
from .adapters.mistral_adapter import MistralOCRAdapter
from .utils.output_manager import OutputManager
from .services.filename_generator import FilenameGenerator
from .utils.cache_manager import CacheManager
from .utils.file_renamer import FileRenamer


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        console = Console()
        console.print(f"OCR version: [cyan]{__version__}[/cyan]")
        raise typer.Exit()


app = typer.Typer()
console = Console()


@app.callback()
def main(
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True, help="Show version and exit")
):
    """OCR CLI - Process documents with Mistral AI."""
    pass


@app.command()
def process_file(
    file: Path = typer.Option(..., "--file", "-f", exists=True, help="File to process"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory (overrides default save at input location)"),
    include_page_headlines: bool = typer.Option(False, "--page-headlines", help="Include page numbers as markdown headlines"),
    page_pattern: Optional[str] = typer.Option(None, "--pages", help="Page pattern (e.g., '1-3', '5-', '4,5')"),
    rename: bool = typer.Option(False, "--rename", help="Enable intelligent filename generation and renaming"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show suggested filename without renaming"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before renaming"),
    force: bool = typer.Option(False, "--force", help="Force regenerate filename even if cached")
):
    """Process a single file with OCR."""
    asyncio.run(_process_file(file, output_dir, include_page_headlines, page_pattern, rename, dry_run, confirm, force))


@app.command()
def process_files(
    files: List[Path] = typer.Option(..., "--files", help="Files to process"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    include_page_headlines: bool = typer.Option(False, "--page-headlines", help="Include page numbers as markdown headlines"),
    page_pattern: Optional[str] = typer.Option(None, "--pages", help="Page pattern (e.g., '1-3', '5-', '4,5')"),
    rename: bool = typer.Option(False, "--rename", help="Enable intelligent filename generation and renaming"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show suggested filenames without renaming"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before renaming"),
    force: bool = typer.Option(False, "--force", help="Force regenerate filenames even if cached")
):
    """Process multiple files with OCR."""
    asyncio.run(_process_files(files, output_dir, include_page_headlines, page_pattern, rename, dry_run, confirm, force))


@app.command()
def process_folder(
    folder: Path = typer.Option(..., "--folder", "-d", exists=True, help="Folder to process"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    include_page_headlines: bool = typer.Option(False, "--page-headlines", help="Include page numbers as markdown headlines"),
    page_pattern: Optional[str] = typer.Option(None, "--pages", help="Page pattern (e.g., '1-3', '5-', '4,5')"),
    rename: bool = typer.Option(False, "--rename", help="Enable intelligent filename generation and renaming"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show suggested filenames without renaming"),
    confirm: bool = typer.Option(False, "--confirm", help="Ask for confirmation before renaming"),
    force: bool = typer.Option(False, "--force", help="Force regenerate filenames even if cached")
):
    """Process all supported files in a folder with OCR."""
    asyncio.run(_process_folder(folder, output_dir, include_page_headlines, page_pattern, rename, dry_run, confirm, force))


async def _process_file(file_path: Path, output_dir: Optional[Path] = None,
                       include_page_headlines: bool = False,
                       page_pattern: Optional[str] = None,
                       rename: bool = False,
                       dry_run: bool = False,
                       confirm: bool = False,
                       force: bool = False):
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


async def _process_files(file_paths: List[Path], output_dir: Optional[Path] = None,
                        include_page_headlines: bool = False,
                        page_pattern: Optional[str] = None,
                        rename: bool = False,
                        dry_run: bool = False,
                        confirm: bool = False,
                        force: bool = False):
    """Process multiple files."""
    try:
        # Load settings
        settings = Settings()
        
        # Initialize OCR service and output manager
        ocr_service = MistralOCRAdapter(settings)
        # For batch: default to project ocr_output unless user provided --output
        output_manager = OutputManager(output_dir, save_at_input_location=False)
        
        console.print(f"Processing {len(file_paths)} files...")
        if page_pattern:
            console.print(f"Page pattern: [yellow]{page_pattern}[/yellow]")
        if include_page_headlines:
            console.print("Including page headlines: [yellow]enabled[/yellow]")
        
        # Process files with progress bar
        results = []
        api_images_total = 0
        for file_path in track(file_paths, description="Processing files..."):
            try:
                result, api_images = await ocr_service.process_file(file_path, page_pattern, include_page_headlines)
                results.append(result)
                api_images_total += api_images
                console.print(f"✓ Processed [green]{file_path.name}[/green] ({api_images} images)")
            except Exception as e:
                console.print(f"❌ Error processing {file_path.name}: [red]{e}[/red]")
                results.append(f"Error processing {file_path.name}: {e}")
        
        # Save results
        filenames = [f.stem for f in file_paths]
        output_files = output_manager.save_batch_results(results, filenames, file_paths, include_page_headlines)
        
        # Create summary table
        table = Table(title="Processing Results")
        table.add_column("File", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Output", style="blue")
        table.add_column("Images", style="yellow")
        
        saved_images_total = 0
        for file_path, (output_file, saved_images) in zip(file_paths, output_files):
            status = "✓ Success" if "Error" not in str(output_file) else "❌ Error"
            table.add_row(file_path.name, status, str(output_file), str(saved_images))
            saved_images_total += saved_images
        
        console.print(table)
        console.print(f"📊 Total API images: {api_images_total}, Total saved images: {saved_images_total}")
        
    except Exception as e:
        console.print(f"❌ Error: [red]{e}[/red]")
        raise typer.Exit(1)


async def _process_folder(folder_path: Path, output_dir: Optional[Path] = None,
                         include_page_headlines: bool = False,
                         page_pattern: Optional[str] = None,
                         rename: bool = False,
                         dry_run: bool = False,
                         confirm: bool = False,
                         force: bool = False):
    """Process all supported files in a folder."""
    try:
        # Load settings
        settings = Settings()
        
        # Initialize OCR service and output manager
        ocr_service = MistralOCRAdapter(settings)
        # For folder: default to project ocr_output unless user provided --output
        output_manager = OutputManager(output_dir, save_at_input_location=False)
        
        console.print(f"Processing folder: [green]{folder_path}[/green]")
        if page_pattern:
            console.print(f"Page pattern: [yellow]{page_pattern}[/yellow]")
        if include_page_headlines:
            console.print("Including page headlines: [yellow]enabled[/yellow]")
        
        # Process folder
        results = await ocr_service.process_folder(folder_path, page_pattern, include_page_headlines)
        
        # Get list of processed files
        supported_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.avif', '.pptx', '.docx'}
        processed_files = [
            f for f in folder_path.iterdir() 
            if f.is_file() and f.suffix.lower() in supported_extensions
        ]
        
        # Extract markdown content and count total API images
        markdown_results = []
        api_images_total = 0
        for result, api_images in results:
            markdown_results.append(result)
            api_images_total += api_images
        
        # Save results
        filenames = [f.stem for f in processed_files]
        output_files = output_manager.save_batch_results(markdown_results, filenames, processed_files, include_page_headlines)
        
        # Create summary table
        table = Table(title="Folder Processing Results")
        table.add_column("File", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Output", style="blue")
        table.add_column("Images", style="yellow")
        
        saved_images_total = 0
        for file_path, (output_file, saved_images) in zip(processed_files, output_files):
            status = "✓ Success" if "Error" not in str(output_file) else "❌ Error"
            table.add_row(file_path.name, status, str(output_file), str(saved_images))
            saved_images_total += saved_images
        
        console.print(table)
        console.print(f"📊 Total API images: {api_images_total}, Total saved images: {saved_images_total}")
        
    except Exception as e:
        console.print(f"❌ Error: [red]{e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
