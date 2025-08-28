"""Main OCR CLI application."""

import asyncio
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

from .models.settings import Settings
from .adapters.mistral_adapter import MistralOCRAdapter
from .utils.output_manager import OutputManager


app = typer.Typer()
console = Console()


@app.command()
def process_file(
    file: Path = typer.Option(..., "--file", "-f", exists=True, help="File to process"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory (overrides default save at input location)"),
    include_page_headlines: bool = typer.Option(False, "--page-headlines", help="Include page numbers as markdown headlines"),
    page_pattern: Optional[str] = typer.Option(None, "--pages", help="Page pattern (e.g., '1-3', '5-', '4,5')")
):
    """Process a single file with OCR."""
    asyncio.run(_process_file(file, output_dir, include_page_headlines, page_pattern))


@app.command()
def process_files(
    files: List[Path] = typer.Option(..., "--files", help="Files to process"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    include_page_headlines: bool = typer.Option(False, "--page-headlines", help="Include page numbers as markdown headlines"),
    page_pattern: Optional[str] = typer.Option(None, "--pages", help="Page pattern (e.g., '1-3', '5-', '4,5')")
):
    """Process multiple files with OCR."""
    asyncio.run(_process_files(files, output_dir, include_page_headlines, page_pattern))


@app.command()
def process_folder(
    folder: Path = typer.Option(..., "--folder", "-d", exists=True, help="Folder to process"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    include_page_headlines: bool = typer.Option(False, "--page-headlines", help="Include page numbers as markdown headlines"),
    page_pattern: Optional[str] = typer.Option(None, "--pages", help="Page pattern (e.g., '1-3', '5-', '4,5')")
):
    """Process all supported files in a folder with OCR."""
    asyncio.run(_process_folder(folder, output_dir, include_page_headlines, page_pattern))


async def _process_file(file_path: Path, output_dir: Optional[Path] = None, 
                       include_page_headlines: bool = False,
                       page_pattern: Optional[str] = None):
    """Process a single file."""
    try:
        # Load settings
        settings = Settings()
        
        # Initialize OCR service
        ocr_service = MistralOCRAdapter(settings)
        # Default: save at input location unless output_dir is provided
        save_at_input_location = output_dir is None
        output_manager = OutputManager(output_dir, save_at_input_location)
        
        console.print(f"Processing file: [green]{file_path}[/green]")
        if page_pattern:
            console.print(f"Page pattern: [yellow]{page_pattern}[/yellow]")
        if include_page_headlines:
            console.print("Including page headlines: [yellow]enabled[/yellow]")
        
        # Process file
        result, api_images = await ocr_service.process_file(file_path, page_pattern, include_page_headlines)
        
        # Save result
        output_file, saved_images = output_manager.save_text_result(
            result, 
            file_path.stem, 
            file_path,
            include_page_headlines
        )
        
        console.print(f"✓ Saved result to: [blue]{output_file}[/blue]")
        console.print(f"📊 API returned {api_images} images, saved {saved_images} images")
        
    except Exception as e:
        console.print(f"❌ Error processing {file_path}: [red]{e}[/red]")
        raise typer.Exit(1)


async def _process_files(file_paths: List[Path], output_dir: Optional[Path] = None,
                        include_page_headlines: bool = False,
                        page_pattern: Optional[str] = None):
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
                         page_pattern: Optional[str] = None):
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
