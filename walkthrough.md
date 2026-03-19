# OCR Tool – Code Walkthrough

*2026-03-19T14:30:59Z by Showboat 0.6.1*
<!-- showboat-id: 413518c6-fea9-4826-bcc6-6a9ecc997812 -->

## Overview

This tool extracts text and images from documents (PDF, PPTX, DOCX) and images (PNG, JPG, AVIF) using Mistral AI's OCR API. It outputs structured Markdown files with YAML frontmatter metadata and can optionally rename files using AI-generated descriptive names.

The architecture is built around five ideas:

1. **Protocol-driven adapters** – a typed interface separates OCR logic from Mistral-specific code, so swapping providers requires only a new adapter.
2. **Two-phase filename generation** – OCR the first page cheaply; if confidence is low, OCR the rest and re-analyse.
3. **Three-source image materialisation** – images embedded in the API response (base64 map), inline data URIs, and external URLs are all extracted and saved locally.
4. **Smart caching** – the YAML frontmatter of every output file doubles as a cache, so re-running the tool never repeats API calls unnecessarily.
5. **Async-first** – every I/O path is async, enabling concurrent batch processing and a live folder-watcher.

## 1. Entry Points

There are two entry points.  `__main__.py` lets the package be run with `python -m ocr`.  The real CLI is in `main.py` and is wired up as a console script in `pyproject.toml`.

```bash
cat src/ocr/__main__.py
```

```output
"""Entry point for OCR CLI application."""

from .main import app

if __name__ == "__main__":
    app()
```

```bash
grep -n 'console_scripts\|entry.point\|scripts' pyproject.toml
```

```output
22:[project.scripts]
```

```bash
sed -n '22,24p' pyproject.toml
```

```output
[project.scripts]
ocr = "ocr.main:app"

```

## 2. CLI Application – `main.py`

`main.py` is the largest file (≈1 200 lines).  It wires together every subsystem.  Two Typer commands are registered on a shared `app` object: `run` and `watch`.

```bash
grep -n '^app\s*=\|^@app\.' src/ocr/main.py | head -20
```

```output
30:app = typer.Typer(no_args_is_help=True)
63:@app.callback()
98:@app.command("run")
965:@app.command()
```

```bash
sed -n '98,150p' src/ocr/main.py
```

```output
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


```

### Dispatching: single vs. batch

After parsing flags, `main()` calls `asyncio.run(_main(...))`.  Inside `_main` the paths are expanded (folders → file lists) and the code branches on file count.

```bash
grep -n 'expand_paths\|_process_single\|_process_multiple\|_process_concat' src/ocr/main.py | head -20
```

```output
71:def expand_paths(paths: List[Path]) -> List[Path]:
181:        files = expand_paths(paths)
194:            await _process_concat_files(
206:            await _process_single_file(
212:            await _process_multiple_files(
364:async def _process_single_file(
512:async def _process_multiple_files(
564:                    await _process_single_file(
654:                                await _process_single_file(
750:                        await _process_single_file(
795:async def _process_concat_files(
```

```bash
sed -n '181,220p' src/ocr/main.py
```

```output
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
```

## 3. Settings – `models/settings.py`

Settings are loaded via Pydantic once per CLI invocation and passed down to every subsystem.  The only required field is the API key; everything else has sensible defaults.

```bash
cat src/ocr/models/settings.py
```

```output
"""Application settings configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, ValidationError
from pathlib import Path

from ..utils.env_setup import get_env_file_path, setup_env_file


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    mistral_api_key: SecretStr
    max_retries: int = 3
    timeout: int = 30

    # Filename generation settings
    filename_generation_model: str = "mistral-small-2506"
    filename_generation_max_tokens: int = 500  # Larger for full-document analysis
    filename_generation_temperature: float = 0.0  # Deterministic

    # Image description settings
    include_image_descriptions: bool = False  # Enable image descriptions via bbox_annotation_format

    model_config = SettingsConfigDict(
        env_file=get_env_file_path(),
        env_file_encoding='utf-8',
        extra='ignore'
    )

    def __init__(self, **kwargs):
        """Initialize settings with automatic .env setup."""
        try:
            super().__init__(**kwargs)
        except ValidationError as e:
            # If validation fails (missing API key), setup .env file
            if "mistral_api_key" in str(e):
                setup_env_file()
                raise ValueError(
                    "Missing MISTRAL_API_KEY. Please add your API key to the .env file and try again."
                ) from e
            raise
```

## 4. OCR Adapter – `adapters/mistral_adapter.py`

`MistralOCRAdapter` implements the `OCRService` protocol.  Its job is to:

1. Validate the file (header-check for images, supported extension check for documents).
2. Base64-encode the file and build a Mistral API request.
3. Receive the response and flatten all pages into a single Markdown string.
4. Collect every embedded image into a map so `OutputManager` can save them.

The protocol it implements is tiny – just three methods – which makes the adapter easy to replace.

```bash
cat src/ocr/protocols/ocr_service.py
```

```output
"""Protocol definitions for OCR services."""

from typing import Protocol, List, Optional
from pathlib import Path


class OCRService(Protocol):
    """Protocol for OCR services."""

    async def process_file(self, file_path: Path, page_pattern: Optional[str] = None,
                          include_page_headlines: bool = False,
                          include_images: bool = True) -> tuple[str, int, int]:
        """Process a single file and return extracted text."""
        ...

    async def process_files(self, file_paths: List[Path]) -> List[str]:
        """Process multiple files and return extracted text for each."""
        ...

    async def process_folder(self, folder_path: Path) -> List[str]:
        """Process all supported files in a folder and return extracted text."""
        ...
```

### File validation and encoding

Before sending anything to the API, the adapter checks that image files have valid magic-number headers (JPEG `FF D8`, PNG `89 50`, AVIF `ftyp`).  PDFs and Office documents go through the document path without header checks.

```bash
grep -n '_validate_image_file\|_encode_file\|_get_mime_type\|_get_document_type' src/ocr/adapters/mistral_adapter.py
```

```output
34:    def _validate_image_file(self, file_path: Path) -> bool:
56:    def _encode_file(self, file_path: Path) -> str:
61:                if not self._validate_image_file(file_path):
71:    def _get_document_type(self, file_path: Path) -> str:
83:        doc_type = self._get_document_type(file_path)
91:    def _get_mime_type(self, file_path: Path) -> str:
252:        base64_content = self._encode_file(file_path)
253:        document_type = self._get_document_type(file_path)
255:        mime_type = self._get_mime_type(file_path)
```

```bash
sed -n '34,100p' src/ocr/adapters/mistral_adapter.py
```

```output
    def _validate_image_file(self, file_path: Path) -> bool:
        """Validate that the file is a valid image file."""
        try:
            with open(file_path, "rb") as file:
                header = file.read(10)  # Read first 10 bytes
                
            ext = file_path.suffix.lower()
            if ext in ['.jpg', '.jpeg']:
                # Check for JPEG header: FF D8 FF
                return header.startswith(b'\xff\xd8\xff')
            elif ext == '.png':
                # Check for PNG header: 89 50 4E 47 0D 0A 1A 0A
                return header.startswith(b'\x89PNG\r\n\x1a\n')
            elif ext == '.avif':
                # Check for AVIF header: 00 00 00 20 66 74 79 70 61 76 69 66
                return header.startswith(b'\x00\x00\x00 ftypavif')
            else:
                # For other formats, assume valid
                return True
        except Exception:
            return False
    
    def _encode_file(self, file_path: Path) -> str:
        """Encode file to base64."""
        try:
            # Validate image files before encoding
            if file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.avif']:
                if not self._validate_image_file(file_path):
                    raise ValueError(f"Invalid or corrupted image file: {file_path}")
            
            with open(file_path, "rb") as file:
                return base64.b64encode(file.read()).decode('utf-8')
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise Exception(f"Error encoding file {file_path}: {e}")
    
    def _get_document_type(self, file_path: Path) -> str:
        """Determine document type based on file extension."""
        ext = file_path.suffix.lower()
        if ext in ['.pdf', '.pptx', '.docx']:
            return "document_url"
        elif ext in ['.png', '.jpg', '.jpeg', '.avif']:
            return "image_url"
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    
    def _get_url_field_name(self, file_path: Path) -> str:
        """Get the correct URL field name based on document type."""
        doc_type = self._get_document_type(file_path)
        if doc_type == "document_url":
            return "document_url"
        elif doc_type == "image_url":
            return "image_url"
        else:
            raise ValueError(f"Unsupported document type: {doc_type}")
    
    def _get_mime_type(self, file_path: Path) -> str:
        """Get MIME type based on file extension."""
        ext = file_path.suffix.lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.avif': 'image/avif',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
```

### Calling the Mistral OCR API

`process_file()` is the core OCR method.  It builds the API request with `include_image_base64=True` so the response embeds every image as base64 data.  After the call, page filtering is applied (if `--pages` was given), then `_generate_markdown()` assembles the final text and `_collect_images_map()` builds the filename-to-base64 dictionary that will be embedded in the output file.

```bash
sed -n '245,310p' src/ocr/adapters/mistral_adapter.py
```

```output
            raise FileNotFoundError(f"File not found: {file_path}")

        # Validate page pattern if provided
        if page_pattern and not PagePatternParser.validate_pattern(page_pattern):
            raise ValueError(f"Invalid page pattern: {page_pattern}")

        # Encode file to base64
        base64_content = self._encode_file(file_path)
        document_type = self._get_document_type(file_path)
        url_field = self._get_url_field_name(file_path)
        mime_type = self._get_mime_type(file_path)

        # Create data URL with base64 content
        data_url = f"data:{mime_type};base64,{base64_content}"

        # Process with Mistral OCR
        document_dict = {"type": document_type}
        document_dict[url_field] = data_url

        # Add bbox_annotation_format if image descriptions are enabled
        ocr_kwargs = {
            "model": "mistral-ocr-latest",
            "document": document_dict,
            "include_image_base64": include_images
        }

        if self.settings.include_image_descriptions:
            ocr_kwargs["bbox_annotation_format"] = response_format_from_pydantic_model(ImageDescription)

        response: OCRResponse = self.client.ocr.process(**ocr_kwargs)

        # Generate markdown with optional filtering and headlines
        markdown, total_images, pages_count = self._generate_markdown(response, page_pattern, include_page_headlines)

        return markdown, total_images, pages_count

    async def process_first_page(self, file_path: Path,
                                 include_page_headlines: bool = False,
                                 include_images: bool = True) -> tuple[str, int]:
        """Process only first page for filename generation analysis.

        Returns:
            Tuple of (markdown_content, total_images)
            Note: pages_processed is always 1 for this method, so not returned
        """
        markdown, total_images, _ = await self.process_file(file_path, page_pattern="1",
                                                             include_page_headlines=include_page_headlines,
                                                             include_images=include_images)
        return markdown, total_images

    async def process_files(self, file_paths: List[Path], page_pattern: Optional[str] = None,
                           include_page_headlines: bool = False) -> List[tuple[str, int, int]]:
        """Process multiple files and return extracted text for each.

        Returns:
            List of tuples (markdown_content, total_images, pages_processed)
        """
        results = []
        for file_path in file_paths:
            try:
                result = await self.process_file(file_path, page_pattern, include_page_headlines)
                results.append(result)
            except Exception as e:
                # Log error but continue with other files
                print(f"Error processing {file_path}: {e}")
                results.append((f"Error processing {file_path}: {e}", 0, 0))
```

### Generating Markdown from the response

`_generate_markdown()` iterates over `response.pages`.  For each page it optionally prepends a `## Page N` headline, appends the page's markdown, and collects any embedded images into the images map.  The map is then serialised as a JSON blob inside an HTML comment at the top of the document – this is how images survive as structured data in a plain-text file.

```bash
grep -n 'def _generate_markdown\|def _collect_images' src/ocr/adapters/mistral_adapter.py
```

```output
119:    def _collect_images_map(self, response: OCRResponse, pages_to_process: list[int]) -> tuple[dict, int]:
170:    def _generate_markdown(self, response: OCRResponse, page_pattern: Optional[str] = None,
```

```bash
sed -n '119,240p' src/ocr/adapters/mistral_adapter.py
```

```output
    def _collect_images_map(self, response: OCRResponse, pages_to_process: list[int]) -> tuple[dict, int]:
        """Collect a mapping of image filename -> {mime, base64} from the OCR response pages."""
        images_map = {}
        total_images = 0
        for i in pages_to_process:
            page = response.pages[i]
            images = getattr(page, "images", []) or []
            total_images += len(images)
            for j, img in enumerate(images):
                # Try different attribute names for OCRImageObject
                filename = getattr(img, "filename", None) or getattr(img, "name", None) or getattr(img, "id", None)
                # According to Mistral documentation, image data is in image_base64 attribute
                b64 = getattr(img, "image_base64", None) or getattr(img, "base64", None)
                mime = getattr(img, "mime", None) or getattr(img, "content_type", None)
                # Extract base64 data from data URL if present
                if b64 and b64.startswith('data:'):
                    if ';base64,' in b64:
                        b64 = b64.split(';base64,', 1)[1]
                    else:
                        continue
                
                if not b64:
                    continue
                # Generate filename if not present
                if not filename:
                    # Use MIME type to determine extension
                    if mime and "/" in mime:
                        mime_ext = mime.split("/")[-1]
                        if mime_ext == "jpeg":
                            ext = "jpg"
                        elif mime_ext == "png":
                            ext = "png"
                        elif mime_ext == "avif":
                            ext = "avif"
                        else:
                            ext = mime_ext
                    else:
                        ext = "jpg"  # Default to jpg
                    filename = f"img-{j}.{ext}"
                if not mime:
                    if filename.lower().endswith((".jpg", ".jpeg")):
                        mime = "image/jpeg"
                    elif filename.lower().endswith(".png"):
                        mime = "image/png"
                    elif filename.lower().endswith(".avif"):
                        mime = "image/avif"
                    else:
                        mime = "image/jpeg"  # Default to jpeg
                images_map[filename] = {"mime": mime, "base64": b64}
        return images_map, total_images

    def _generate_markdown(self, response: OCRResponse, page_pattern: Optional[str] = None,
                          include_page_headlines: bool = False) -> tuple[str, int, int]:
        """Generate markdown from OCR response with optional filtering and headlines.

        Returns:
            Tuple of (markdown_content, total_images, pages_processed)
        """
        if not page_pattern:
            # Process all pages
            pages_to_process = list(range(len(response.pages)))
        else:
            # Filter pages based on pattern
            total_pages = len(response.pages)
            selected_pages = PagePatternParser.parse_pattern(page_pattern, total_pages)
            pages_to_process = [i for i in range(len(response.pages)) if i + 1 in selected_pages]

        if not pages_to_process:
            return "No pages match the specified pattern.", 0, 0

        markdown_parts = []
        for i in pages_to_process:
            page_num = i + 1  # Convert to 1-indexed
            page_content = response.pages[i].markdown

            # Add image descriptions if available
            if self.settings.include_image_descriptions:
                page = response.pages[i]
                images = getattr(page, "images", []) or []
                for img in images:
                    img_id = getattr(img, "id", None) or getattr(img, "filename", None)
                    img_annotation = getattr(img, "image_annotation", None)

                    if img_id and img_annotation:
                        # Parse annotation if it's JSON
                        try:
                            if isinstance(img_annotation, str):
                                annotation_data = json.loads(img_annotation)
                                description = annotation_data.get("description", img_annotation)
                            else:
                                description = str(img_annotation)
                        except json.JSONDecodeError:
                            description = str(img_annotation)

                        # Replace image reference with image + description
                        image_pattern = f"![{img_id}]({img_id})"
                        if image_pattern in page_content:
                            page_content = page_content.replace(
                                image_pattern,
                                f"{image_pattern}\n\n**Image Description:** {description}\n"
                            )

            if include_page_headlines:
                markdown_parts.append(f"### Page {page_num}\n{page_content}")
            else:
                markdown_parts.append(page_content)

        markdown_body = "\n\n".join(markdown_parts)
        pages_count = len(pages_to_process)

        # Prepend images map as an HTML comment block for OutputManager to consume
        images_map, total_images = self._collect_images_map(response, pages_to_process)
        if images_map:
            header = f"<!--IMAGES_MAP\n{json.dumps(images_map)}\n-->\n\n"
            return header + markdown_body, total_images, pages_count
        return markdown_body, total_images, pages_count
    
    async def process_file(self, file_path: Path, page_pattern: Optional[str] = None,
                          include_page_headlines: bool = False,
                          include_images: bool = True) -> tuple[str, int, int]:
        """Process a single file and return extracted text.

```

## 5. Filename Generation – `services/filename_generator.py`

When `--rename` or `--dry-run` is passed, the tool uses a second Mistral model call to derive a human-readable filename.  The generator uses `mistral-small-2506` by default.  A prompt loaded from `filename_generator_prompt.md` instructs the model to extract an ISO date, company name, and one-line summary, then return them as JSON with a confidence score.

```bash
cat src/ocr/services/filename_generator.py
```

```output
"""Intelligent filename generation service using Mistral AI."""

import json
import re
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime
from mistralai import Mistral

from ..models.settings import Settings
from ..models.metadata import FilenameMetadata

if getattr(sys, 'frozen', False):
    _PROMPT_FILE = Path(sys._MEIPASS) / "ocr" / "services" / "filename_generator_prompt.md"
else:
    _PROMPT_FILE = Path(__file__).parent / "filename_generator_prompt.md"


class FilenameGenerator:
    """Generate intelligent filenames from OCR content."""

    SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8")

    def __init__(self, settings: Settings, client: Optional[Mistral] = None):
        """Initialize filename generator.

        Args:
            settings: Application settings
            client: Optional pre-initialized Mistral client for sharing with OCR adapter
        """
        self.client = client or Mistral(api_key=settings.mistral_api_key.get_secret_value())
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
        current_filename: Optional[str] = None,
        file_created_date: Optional[str] = None,
        file_modified_date: Optional[str] = None
    ) -> FilenameMetadata:
        """Analyze markdown content and extract filename components.

        Args:
            markdown_content: The OCR'd markdown content to analyze
            pages_analyzed: Number of pages analyzed (1 for first page, -1 for all)
            current_filename: Optional current filename to use as additional context
            file_created_date: Optional file creation date from filesystem (ISO format)
            file_modified_date: Optional file modification date from filesystem (ISO format)
        """
        try:
            # Build user message with optional current filename and file dates
            user_message = "Analyze this document content and generate filename:"
            if current_filename:
                user_message += f"\n\nCurrent filename: {current_filename}"
            if file_created_date or file_modified_date:
                user_message += "\n\nFilesystem dates:"
                if file_created_date:
                    user_message += f"\n  - File created: {file_created_date}"
                if file_modified_date:
                    user_message += f"\n  - File modified: {file_modified_date}"
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
```

### The two-phase confidence loop

The generator is called from `_generate_filename_for_file()` in `main.py`.  The algorithm is:

1. OCR the **first page only** (fast, cheap).
2. Call `analyze_content()` — get back a `FilenameMetadata` with a `confidence` score between 0.0 and 1.0.
3. If `confidence >= threshold` (default 0.7) → done.
4. Otherwise, OCR **all remaining pages** and re-analyse with the full document text.

This two-phase approach keeps API usage low for well-structured documents (invoices, contracts) while still handling ambiguous files gracefully.

```bash
grep -n '_generate_filename_for_file' src/ocr/main.py | head -5
```

```output
258:async def _generate_filename_for_file(
401:            filename_metadata, markdown_content, pages_processed = await _generate_filename_for_file(
592:                                filename_metadata, markdown_content, pages_processed = await _generate_filename_for_file(
683:                        filename_metadata, markdown_content, pages_processed = await _generate_filename_for_file(
1035:                    filename_metadata, markdown_content, pages_processed = await _generate_filename_for_file(
```

```bash
sed -n '258,362p' src/ocr/main.py
```

```output
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

```

## 6. Output Manager – `utils/output_manager.py`

`OutputManager.save_text_result()` is called after OCR and filename generation are complete.  It is responsible for:

- Deciding the output path (always in a `.ocr/` subdirectory next to the source file; `.pg1.md` for single pages, `.md` for multi-page).
- Building and prepending YAML frontmatter.
- Extracting images from three sources and rewriting Markdown references to point at local files.

The three image sources are handled in `_materialize_images()`.

```bash
grep -n 'def save_text_result\|def _materialize_images\|def _download_image\|IMAGES_MAP\|data:image\|http' src/ocr/utils/output_manager.py | head -30
```

```output
8:import aiohttp
43:    async def _materialize_images(self, markdown_content: str, base_dir: Path, prefix: str) -> Tuple[str, int]:
60:        images_header_re = re.compile(r"^<!--IMAGES_MAP\n(?P<json>{[\s\S]*?})\n-->\n\n", re.MULTILINE)
79:            r'(?P<mime>data:image/(?P<ext>[^;]+));base64,(?P<b64>[A-Za-z0-9+/=]+)'
108:        # External URLs - async download with aiohttp
110:            r'!\[(?P<alt>.*?)\]\((?P<url>https?://[^\s)]+)\)'
119:            async with aiohttp.ClientSession() as session:
212:    async def _download_image(self, session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
213:        """Download image from URL using aiohttp."""
215:            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
225:    async def save_text_result(self, content: str, filename: str, source_file: Path = None,
258:            images_header_re = re.compile(r"^<!--IMAGES_MAP\n(?P<json>{[\s\S]*?})\n-->\n\n", re.MULTILINE)
```

```bash
sed -n '43,130p' src/ocr/utils/output_manager.py
```

```output
    async def _materialize_images(self, markdown_content: str, base_dir: Path, prefix: str) -> Tuple[str, int]:
        """
        Extract embedded base64 images and download URL images referenced in markdown.
        Save them under base_dir/images with filenames prefixed by `prefix`, and rewrite
        the markdown to point to local files.

        Returns:
            updated_markdown, count_images_saved
        """
        if not markdown_content:
            return markdown_content, 0

        images_dir = None  # Create lazily only when needed
        saved_count = 0
        counter = 0

        # Optional header from adapter with an images map
        images_header_re = re.compile(r"^<!--IMAGES_MAP\n(?P<json>{[\s\S]*?})\n-->\n\n", re.MULTILINE)
        images_map = {}
        def parse_images_map(md: str) -> str:
            nonlocal images_map
            m = images_header_re.match(md)
            if not m:
                return md
            try:
                images_map = json.loads(m.group("json"))
            except Exception:
                images_map = {}
            # strip header
            return md[m.end():]

        markdown_content = parse_images_map(markdown_content)

        # Embedded data URIs
        data_uri_re = re.compile(
            r'!\[(?P<alt>.*?)\]\('
            r'(?P<mime>data:image/(?P<ext>[^;]+));base64,(?P<b64>[A-Za-z0-9+/=]+)'
            r'\)'
        )

        def replace_data_uri(m: re.Match) -> str:
            nonlocal saved_count, counter, images_dir
            alt = m.group("alt")
            ext = m.group("ext").lower().split("+")[0]
            b64 = m.group("b64")
            counter += 1
            filename = f"{prefix}_{counter}.{ext}"
            # Create images directory only when needed
            if images_dir is None:
                images_dir = self._ensure_images_dir(base_dir)
            out_path = images_dir / filename
            try:
                data = base64.b64decode(b64)
                with open(out_path, "wb") as f:
                    f.write(data)
                saved_count += 1
                print(f"saved image: images/{filename}")
                return f"![{alt}](images/{filename})"
            except Exception as e:
                print(f"Error saving data URI image {filename}: {e}")
                # Leave original if anything fails
                return m.group(0)

        updated = data_uri_re.sub(replace_data_uri, markdown_content)

        # External URLs - async download with aiohttp
        url_img_re = re.compile(
            r'!\[(?P<alt>.*?)\]\((?P<url>https?://[^\s)]+)\)'
        )

        # First pass: collect all URLs
        url_matches = list(url_img_re.finditer(updated))

        if url_matches:
            # Download all URLs concurrently
            downloaded_images = {}
            async with aiohttp.ClientSession() as session:
                download_tasks = []
                for m in url_matches:
                    url = m.group("url")
                    download_tasks.append(self._download_image(session, url))

                # Wait for all downloads to complete
                results = await asyncio.gather(*download_tasks, return_exceptions=True)

                # Map URLs to downloaded content
                for m, result in zip(url_matches, results):
                    if not isinstance(result, Exception) and result is not None:
```

```bash
sed -n '130,210p' src/ocr/utils/output_manager.py
```

```output
                    if not isinstance(result, Exception) and result is not None:
                        downloaded_images[m.group("url")] = result

            # Second pass: replace with downloaded images
            def replace_url(m: re.Match) -> str:
                nonlocal saved_count, counter, images_dir
                alt = m.group("alt")
                url = m.group("url")

                # Check if we successfully downloaded this URL
                content = downloaded_images.get(url)
                if content is None:
                    # Download failed, leave original
                    return m.group(0)

                counter += 1
                ext = self._guess_ext_from_url(url)
                filename = f"{prefix}_{counter}{ext}"
                # Create images directory only when needed
                if images_dir is None:
                    images_dir = self._ensure_images_dir(base_dir)
                out_path = images_dir / filename
                try:
                    with open(out_path, "wb") as f:
                        f.write(content)
                    saved_count += 1
                    print(f"downloaded image: {url} -> images/{filename}")
                    return f"![{alt}](images/{filename})"
                except Exception as e:
                    print(f"Error saving image {filename}: {e}")
                    return m.group(0)

            updated = url_img_re.sub(replace_url, updated)

        # Materialize images from images_map by replacing bare filenames in links if present
        if images_map:
            file_img_re = re.compile(r'!\[(?P<alt>.*?)\]\((?P<fname>[^)\s]+)\)')

            def replace_file_link(m: re.Match) -> str:
                nonlocal saved_count, counter, images_dir
                alt = m.group("alt")
                fname = m.group("fname")
                info = images_map.get(fname)
                if not info:
                    return m.group(0)
                b64 = info.get("base64")
                mime = info.get("mime", "application/octet-stream")

                # derive extension from mime or original fname
                if "/" in mime:
                    mime_ext = mime.split("/")[-1]
                    # Convert MIME type extensions to file extensions
                    if mime_ext == "jpeg":
                        ext = ".jpg"
                    elif mime_ext == "png":
                        ext = ".png"
                    elif mime_ext == "avif":
                        ext = ".avif"
                    else:
                        ext = "." + mime_ext
                else:
                    ext = Path(fname).suffix or ".png"
                counter += 1
                filename = f"{prefix}_{counter}{ext}"
                # Create images directory only when needed
                if images_dir is None:
                    images_dir = self._ensure_images_dir(base_dir)
                out_path = images_dir / filename
                try:
                    data = base64.b64decode(b64)
                    with open(out_path, "wb") as f:
                        f.write(data)
                    saved_count += 1
                    print(f"saved image (map): images/{filename}")
                    return f"![{alt}](images/{filename})"
                except Exception as e:
                    print(f"Error saving image {filename}: {e}")
                    return m.group(0)

            updated = file_img_re.sub(replace_file_link, updated)
        return updated, saved_count
```

## 7. Cache Manager – `utils/cache_manager.py`

Every saved output file carries its generation metadata in its YAML frontmatter.  `CacheManager` reads that frontmatter back to avoid redundant work on subsequent runs.

There are three cache levels:

| Method | What it returns | Used to avoid |
|---|---|---|
| `get_cached_filename()` | `FilenameMetadata` | Re-calling the Mistral chat API |
| `get_cached_markdown()` | Raw OCR markdown | Re-calling the Mistral OCR API |
| `get_cached_ocr_file()` | Path to the `.ocr/*.md` file | Searching the filesystem |

The cache is stored in the same `.ocr/` subdirectory that `OutputManager` writes to, so no separate cache store is needed.

```bash
grep -n 'def get_cached\|def extract_metadata\|def get_cached_ocr' src/ocr/utils/cache_manager.py
```

```output
17:    def get_cached_ocr_file(source_file: Path) -> Optional[Path]:
40:    def extract_metadata(ocr_file: Path) -> Optional[OCRMetadata]:
111:    def get_cached_filename(source_file: Path, force: bool = False) -> Optional[FilenameMetadata]:
127:    def get_cached_markdown(source_file: Path) -> Optional[str]:
```

```bash
sed -n '17,150p' src/ocr/utils/cache_manager.py
```

```output
    def get_cached_ocr_file(source_file: Path) -> Optional[Path]:
        """Find existing OCR markdown file for source file."""
        # Check in .ocr subdirectory
        ocr_dir = source_file.parent / ".ocr"
        if not ocr_dir.exists():
            # Fall back to old location for backward compatibility
            ocr_file = source_file.parent / f"{source_file.stem}_ocr.md"
            if ocr_file.exists():
                return ocr_file
            return None

        # Check for .pg1.md (single page) first, then .md (multi-page)
        pg1_file = ocr_dir / f"{source_file.stem}.pg1.md"
        if pg1_file.exists():
            return pg1_file

        md_file = ocr_dir / f"{source_file.stem}.md"
        if md_file.exists():
            return md_file

        return None

    @staticmethod
    def extract_metadata(ocr_file: Path) -> Optional[OCRMetadata]:
        """Extract metadata from OCR markdown file."""
        try:
            with open(ocr_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Try YAML frontmatter first (new format)
            yaml_match = re.match(r'^---\n(.*?)\n---\n\n', content, re.DOTALL)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                metadata_dict = yaml.safe_load(yaml_content)

                # Parse filename_metadata if present
                filename_metadata = None
                if "filename_metadata" in metadata_dict and metadata_dict["filename_metadata"]:
                    fm_data = metadata_dict["filename_metadata"]

                    # Handle backward compatibility: convert old string confidence to float
                    confidence_raw = fm_data.get("confidence")
                    confidence = None
                    if confidence_raw is not None:
                        if isinstance(confidence_raw, (int, float)):
                            confidence = float(confidence_raw)
                        elif isinstance(confidence_raw, str):
                            # Convert old string values to float
                            confidence_map = {"high": 0.9, "medium": 0.5, "low": 0.2}
                            confidence = confidence_map.get(confidence_raw.lower(), 0.5)

                    filename_metadata = FilenameMetadata(
                        generated_filename=fm_data.get("generated_filename", ""),
                        generation_timestamp=datetime.fromisoformat(fm_data.get("generation_timestamp", datetime.now().isoformat())),
                        generation_method=fm_data.get("generation_method", "unknown"),
                        confidence=confidence,
                        extracted_date=fm_data.get("extracted_date"),
                        extracted_company=fm_data.get("extracted_company"),
                        extracted_summary=fm_data.get("extracted_summary"),
                        pages_analyzed=fm_data.get("pages_analyzed", 1)
                    )

                # Parse rename_history if present
                rename_history = []
                for entry in metadata_dict.get("rename_history", []) or []:
                    rename_history.append(RenameEvent(
                        from_name=entry["from_name"],
                        to_name=entry["to_name"],
                        timestamp=datetime.fromisoformat(entry["timestamp"]),
                        confidence=entry.get("confidence"),
                    ))

                return OCRMetadata(
                    source_file=metadata_dict.get("source_file"),
                    processed_at=datetime.fromisoformat(metadata_dict.get("processed_at", datetime.now().isoformat())),
                    content_length=metadata_dict.get("content_length", 0),
                    include_page_headlines=metadata_dict.get("include_page_headlines", False),
                    images_saved=metadata_dict.get("images_saved", 0),
                    filename_metadata=filename_metadata,
                    rename_history=rename_history,
                )

            # Fallback to legacy HTML comment format
            html_match = re.match(r'^<!--\n(.*?)\n-->\n\n', content, re.DOTALL)
            if html_match:
                metadata_json = json.loads(html_match.group(1))
                return OCRMetadata.from_legacy_json(metadata_json)

            return None

        except Exception:
            return None

    @staticmethod
    def get_cached_filename(source_file: Path, force: bool = False) -> Optional[FilenameMetadata]:
        """Get cached filename metadata if available."""
        if force:
            return None

        ocr_file = CacheManager.get_cached_ocr_file(source_file)
        if not ocr_file:
            return None

        metadata = CacheManager.extract_metadata(ocr_file)
        if not metadata or not metadata.filename_metadata:
            return None

        return metadata.filename_metadata

    @staticmethod
    def get_cached_markdown(source_file: Path) -> Optional[str]:
        """Get cached markdown content without re-OCRing."""
        ocr_file = CacheManager.get_cached_ocr_file(source_file)
        if not ocr_file:
            return None

        try:
            with open(ocr_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Strip YAML frontmatter
            content = re.sub(r'^---\n.*?\n---\n\n', '', content, count=1, flags=re.DOTALL)

            # Strip legacy HTML comment header if present
            content = re.sub(r'^<!--\n.*?\n-->\n\n', '', content, count=1, flags=re.DOTALL)

            # Strip images map if present
            content = re.sub(r'^<!--IMAGES_MAP\n.*?\n-->\n\n', '', content, count=1, flags=re.DOTALL)

            return content

        except Exception:
            return None
```

## 8. File Renamer – `utils/file_renamer.py`

When a rename is confirmed, `FileRenamer.rename_file_pair()` renames **both** the source document **and** its `.ocr/*.md` counterpart atomically.  The rename history is appended to the YAML frontmatter so that `--undo` can reverse it later.

Key safety features:

- **Collision detection** — if the target filename already exists a counter suffix (`_2`, `_3`, …) is appended.
- **Rollback** — if the second rename fails after the first succeeded, the first rename is reversed.
- **Confirmation prompt** — `--confirm` shows a Rich console prompt before any file is touched.

```bash
grep -n 'def rename_file_pair\|def resolve_collision\|def confirm_rename\|def log_rename' src/ocr/utils/file_renamer.py
```

```output
17:    def resolve_collision(target_path: Path) -> Path:
39:    def rename_file_pair(
125:    def log_rename_to_frontmatter(
153:    def log_rename_to_file(
169:    def confirm_rename(source_file: Path, new_name: str) -> bool:
```

```bash
sed -n '17,125p' src/ocr/utils/file_renamer.py
```

```output
    def resolve_collision(target_path: Path) -> Path:
        """Generate unique filename if collision exists."""
        if not target_path.exists():
            return target_path

        # Add counter suffix: filename_2.ext, filename_3.ext, etc.
        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        counter = 2
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

            # Safety limit to prevent infinite loop
            if counter > 9999:
                raise RuntimeError(f"Could not resolve collision for {target_path}")

    @staticmethod
    def rename_file_pair(
        source_file: Path,
        new_basename: str,
        dry_run: bool = False
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Rename both original file and its OCR markdown file in .ocr subdirectory.

        Returns:
            (new_source_path, new_ocr_path) or (None, None) if dry run
        """
        # Construct new path for source file
        new_source_path = source_file.parent / f"{new_basename}{source_file.suffix}"

        # Find OCR file in .ocr subdirectory
        ocr_dir = source_file.parent / ".ocr"
        ocr_file = None
        new_ocr_path = None

        if ocr_dir.exists():
            # Check for .pg1.md first, then .md
            pg1_file = ocr_dir / f"{source_file.stem}.pg1.md"
            md_file = ocr_dir / f"{source_file.stem}.md"

            if pg1_file.exists():
                ocr_file = pg1_file
                new_ocr_path = ocr_dir / f"{new_basename}.pg1.md"
            elif md_file.exists():
                ocr_file = md_file
                new_ocr_path = ocr_dir / f"{new_basename}.md"
        else:
            # Fall back to old location for backward compatibility
            old_ocr = source_file.parent / f"{source_file.stem}_ocr.md"
            if old_ocr.exists():
                ocr_file = old_ocr
                new_ocr_path = source_file.parent / f"{new_basename}_ocr.md"

        # Resolve collisions
        new_source_path = FileRenamer.resolve_collision(new_source_path)

        # If collision was resolved, update OCR path accordingly
        if new_ocr_path and new_source_path.stem != new_basename:
            if ocr_file and ocr_file.parent == ocr_dir:
                # Update OCR path in .ocr directory
                suffix = ".pg1.md" if ocr_file.name.endswith(".pg1.md") else ".md"
                new_ocr_path = ocr_dir / f"{new_source_path.stem}{suffix}"
            else:
                # Old location
                new_ocr_path = source_file.parent / f"{new_source_path.stem}_ocr.md"

        if new_ocr_path:
            new_ocr_path = FileRenamer.resolve_collision(new_ocr_path)

        if dry_run:
            return (new_source_path, new_ocr_path)

        try:
            # Capture timestamps before rename
            source_stat = os.stat(source_file)
            ocr_stat = os.stat(ocr_file) if ocr_file and ocr_file.exists() else None

            # Rename original file
            source_file.rename(new_source_path)
            # Restore timestamps
            os.utime(new_source_path, (source_stat.st_atime, source_stat.st_mtime))

            # Rename OCR file if exists
            if ocr_file and ocr_file.exists() and new_ocr_path:
                ocr_file.rename(new_ocr_path)
                if ocr_stat:
                    os.utime(new_ocr_path, (ocr_stat.st_atime, ocr_stat.st_mtime))

            return (new_source_path, new_ocr_path)

        except Exception as e:
            # Rollback if partial rename occurred
            if new_source_path.exists() and source_file != new_source_path:
                try:
                    rollback_stat = os.stat(new_source_path)
                    new_source_path.rename(source_file)
                    os.utime(source_file, (rollback_stat.st_atime, rollback_stat.st_mtime))
                except Exception:
                    pass  # Best effort rollback
            raise RuntimeError(f"Failed to rename files: {e}") from e

    @staticmethod
    def log_rename_to_frontmatter(
```

## 9. Watch Mode – `services/folder_watcher.py` + `services/processing_queue.py`

`ocr watch <folder>` monitors a directory for new files using the `watchdog` library.

The two classes involved are:

- **`FolderWatcher`** – wraps `watchdog.Observer`.  When a `FileCreatedEvent` or `FileMovedEvent` fires for a supported file type, it waits for the file to stabilise (three consecutive size checks prove the transfer is done) then hands it off to the `ProcessingQueue`.
- **`ProcessingQueue`** – an asyncio queue with a semaphore-bounded pool.  Each job retries up to three times with exponential backoff (1 s → 2 s → 4 s) and tracks its status (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`).  Duplicate prevention ensures a file that is already queued or processed does not get enqueued again.

```bash
grep -n 'def on_created\|def on_moved\|wait_for_file_stability\|mark_processed\|semaphore\|asyncio.sleep\|exponential' src/ocr/services/folder_watcher.py src/ocr/services/processing_queue.py
```

```output
src/ocr/services/folder_watcher.py:48:    def mark_processed(self, file_path: Path):
src/ocr/services/folder_watcher.py:52:    async def wait_for_file_stability(self, file_path: Path):
src/ocr/services/folder_watcher.py:68:            await asyncio.sleep(1)
src/ocr/services/folder_watcher.py:108:            self.wait_for_file_stability(file_path),
src/ocr/services/folder_watcher.py:153:    def on_created(self, event):
src/ocr/services/folder_watcher.py:165:    def on_moved(self, event):
src/ocr/services/processing_queue.py:43:    - Concurrent processing with semaphore
src/ocr/services/processing_queue.py:44:    - Retry with exponential backoff (3 attempts)
src/ocr/services/processing_queue.py:55:        self.semaphore = asyncio.Semaphore(max_concurrent)
src/ocr/services/processing_queue.py:95:        async with self.semaphore:
src/ocr/services/processing_queue.py:113:                        await asyncio.sleep(delay)
src/ocr/services/processing_queue.py:156:            await asyncio.sleep(0.5)
```

```bash
sed -n '52,115p' src/ocr/services/folder_watcher.py
```

```output
    async def wait_for_file_stability(self, file_path: Path):
        """Wait for a file to stop changing (file transfer complete).

        Args:
            file_path: Path to the file to monitor
        """
        if not file_path.exists():
            return

        console.print(f"[cyan]Detected: {file_path.name}[/cyan]")

        # Wait for file size to stabilize (3 consecutive checks with same size)
        stable_count = 0
        prev_size = -1

        while stable_count < 3:
            await asyncio.sleep(1)

            if not file_path.exists():
                console.print(f"[yellow]File disappeared: {file_path.name}[/yellow]")
                return

            try:
                current_size = file_path.stat().st_size
                if current_size == prev_size:
                    stable_count += 1
                else:
                    stable_count = 0
                    prev_size = current_size
            except Exception as e:
                console.print(f"[yellow]Error checking file stability: {e}[/yellow]")
                return

        console.print(f"[green]Ready: {file_path.name}[/green]")

        # File is stable, trigger processing
        try:
            await self.on_file_ready(file_path)
        except Exception as e:
            console.print(f"[red]Error processing {file_path.name}: {e}[/red]")

    def _handle_new_file(self, file_path: Path):
        """Handle a new file event.

        Args:
            file_path: Path to the new file
        """
        # Filter by supported extensions
        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return

        if self._loop is None:
            return

        # Schedule coroutine on the main event loop from watchdog's background thread
        future = asyncio.run_coroutine_threadsafe(
            self.wait_for_file_stability(file_path),
            self._loop
        )
        self._stability_futures.add(future)
        future.add_done_callback(self._stability_futures.discard)

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start watching the folder."""
```

```bash
sed -n '85,130p' src/ocr/services/processing_queue.py
```

```output
    ) -> bool:
        """Process a single job with retry logic.

        Args:
            job: The job to process
            processor: Async function that processes the file

        Returns:
            True if successful, False if failed after retries
        """
        async with self.semaphore:
            while job.attempts < job.max_attempts:
                job.attempts += 1
                job.status = JobStatus.PROCESSING
                job.started_at = datetime.now()

                try:
                    await processor(job.file_path)
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.now()
                    return True
                except Exception as e:
                    job.error = str(e)
                    console.print(f"[yellow]Attempt {job.attempts}/{job.max_attempts} failed for {job.file_path.name}: {e}[/yellow]")

                    if job.attempts < job.max_attempts:
                        # Exponential backoff: 1s, 2s, 4s
                        delay = 2 ** (job.attempts - 1)
                        await asyncio.sleep(delay)

            # All attempts failed
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            console.print(f"[red]Failed to process {job.file_path.name} after {job.max_attempts} attempts: {job.error}[/red]")
            return False

    async def start_processing(
        self,
        processor: Callable[[Path], Awaitable[None]]
    ):
        """Start processing jobs from the queue.

        Args:
            processor: Async function that processes files
        """
        while not self._shutdown:
```

## 10. Supporting Utilities

### Page Parser – `utils/page_parser.py`

Converts the `--pages` flag string into a set of 1-indexed page numbers.  Handles single pages, ranges (`1-3`), open-ended ranges (`5-`, `-3`), comma-separated lists, and the keywords `all`, `*`, `pg1`, `first`.

```bash
grep -n 'def parse_pattern\|def validate_pattern' src/ocr/utils/page_parser.py
```

```output
11:    def parse_pattern(pattern: str, total_pages: int) -> Set[int]:
77:    def validate_pattern(pattern: str) -> bool:
```

```bash
sed -n '11,77p' src/ocr/utils/page_parser.py
```

```output
    def parse_pattern(pattern: str, total_pages: int) -> Set[int]:
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
        parts = pattern.split(',')
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
                
            # Handle range patterns (e.g., "1-3", "5-")
            if '-' in part:
                range_parts = part.split('-')
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
```

### Error Handler – `utils/error_handler.py`

Centralises error display and maps every exception type to a specific exit code so that callers (shell scripts, CI pipelines) can react programmatically.

```bash
grep -n 'EXIT_CODE\|exit_code\|AuthenticationError\|RateLimitError\|QuotaExceeded\|InvalidFile\|def handle_error' src/ocr/utils/error_handler.py | head -25
```

```output
8:    InvalidFileError,
10:    AuthenticationError,
11:    RateLimitError,
12:    QuotaExceededError,
24:    def handle_error(error: Exception, verbose: bool = False) -> int:
34:        if isinstance(error, AuthenticationError):
37:        elif isinstance(error, RateLimitError):
40:        elif isinstance(error, QuotaExceededError):
43:        elif isinstance(error, InvalidFileError):
57:    def _show_auth_error(error: AuthenticationError):
73:    def _show_rate_limit_error(error: RateLimitError):
91:    def _show_quota_error(error: QuotaExceededError):
107:    def _show_file_error(error: InvalidFileError):
```

```bash
sed -n '24,56p' src/ocr/utils/error_handler.py
```

```output
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
```

### Lock Manager – `utils/lock_manager.py`

Prevents the watch-mode processor from picking up the same file twice when multiple events fire concurrently.  Locks are file-based (`<filename>.lock` next to the source) and are auto-cleared after 5 minutes to avoid stale locks surviving a crash.

```bash
sed -n '1,90p' src/ocr/utils/lock_manager.py
```

```output
"""File-based locking to prevent duplicate processing."""

import os
import time
from pathlib import Path
from typing import Optional


class LockManager:
    """Manage file locks to prevent duplicate processing.

    Uses file-based locking with stale lock detection to ensure only one
    process can work on a file at a time.
    """

    LOCK_TIMEOUT_SECONDS = 300  # 5 minutes

    @staticmethod
    def get_lock_path(file_path: Path) -> Path:
        """Get the lock file path for a given source file.

        Args:
            file_path: Path to the source file

        Returns:
            Path to the lock file in .ocr subdirectory
        """
        ocr_dir = file_path.parent / ".ocr"
        ocr_dir.mkdir(exist_ok=True)
        return ocr_dir / f".{file_path.stem}.lock"

    @staticmethod
    def acquire_lock(file_path: Path) -> bool:
        """Attempt to acquire a lock for processing a file.

        Args:
            file_path: Path to the file to lock

        Returns:
            True if lock was acquired, False if already locked
        """
        lock_path = LockManager.get_lock_path(file_path)

        # Check for stale lock
        if lock_path.exists():
            try:
                stat = lock_path.stat()
                lock_age = time.time() - stat.st_mtime
                if lock_age > LockManager.LOCK_TIMEOUT_SECONDS:
                    # Stale lock detected, remove it
                    lock_path.unlink()
                else:
                    # Valid lock exists
                    return False
            except Exception:
                # If we can't read the lock, try to remove it
                try:
                    lock_path.unlink()
                except Exception:
                    return False

        # Try to create lock file exclusively
        try:
            # Using O_CREAT | O_EXCL ensures atomic creation
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)

            # Write timestamp and PID to lock file
            with open(lock_path, 'w') as f:
                f.write(f"{time.time()}\n{os.getpid()}\n")

            return True
        except FileExistsError:
            # Another process created the lock between our check and creation
            return False
        except Exception:
            return False

    @staticmethod
    def release_lock(file_path: Path) -> bool:
        """Release a lock for a file.

        Args:
            file_path: Path to the file to unlock

        Returns:
            True if lock was released, False if lock didn't exist
        """
        lock_path = LockManager.get_lock_path(file_path)

```

## 11. Data Models – `models/metadata.py`

All persistent state flows through three Pydantic models:

- **`FilenameMetadata`** — the result of a filename generation call: generated name, confidence, extracted fields, which model was used, and how many pages were analysed.
- **`RenameEvent`** — a single rename operation logged in the frontmatter history: before/after names, timestamp, confidence at time of rename.
- **`OCRMetadata`** — the complete YAML frontmatter block: source file path, processing timestamp, image count, a reference to the `FilenameMetadata`, and the full `rename_history` list.

`OCRMetadata.to_yaml_dict()` serialises everything to a plain dict for embedding in the frontmatter.  `from_legacy_json()` handles files produced by pre-v0.2.0 versions that used an HTML comment header instead of YAML.

```bash
cat src/ocr/models/metadata.py
```

```output
"""Metadata models for OCR processing."""

from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class FilenameMetadata(BaseModel):
    """Metadata for generated filenames."""

    generated_filename: str
    generation_timestamp: datetime
    generation_method: str = Field(default="mistral-small-2506")
    confidence: Optional[float] = None  # 0.0 (low) to 1.0 (high), e.g., 0.5 for medium
    extracted_date: Optional[str] = None
    extracted_company: Optional[str] = None
    extracted_summary: Optional[str] = None
    pages_analyzed: int = 1


class RenameEvent(BaseModel):
    """A single rename operation record."""

    from_name: str
    to_name: str
    timestamp: datetime
    confidence: Optional[float] = None


class OCRMetadata(BaseModel):
    """Complete metadata for OCR output files."""

    source_file: Optional[str] = None
    original_filename: Optional[str] = None  # Original filename before any renaming
    processed_at: datetime
    content_length: int
    include_page_headlines: bool = False
    images_saved: int = 0
    filename_metadata: Optional[FilenameMetadata] = None
    rename_history: list[RenameEvent] = Field(default_factory=list)

    @classmethod
    def from_legacy_json(cls, data: dict) -> "OCRMetadata":
        """Create from existing JSON metadata (backward compatibility)."""
        # Handle datetime parsing
        processed_at_str = data.get("processed_at")
        if isinstance(processed_at_str, str):
            processed_at = datetime.fromisoformat(processed_at_str)
        else:
            processed_at = datetime.now()

        # Parse rename_history if present
        rename_history = []
        for entry in data.get("rename_history", []):
            rename_history.append(RenameEvent(
                from_name=entry["from_name"],
                to_name=entry["to_name"],
                timestamp=datetime.fromisoformat(entry["timestamp"]),
                confidence=entry.get("confidence"),
            ))

        return cls(
            source_file=data.get("source_file"),
            original_filename=data.get("original_filename"),
            processed_at=processed_at,
            content_length=data.get("content_length", 0),
            include_page_headlines=data.get("include_page_headlines", False),
            images_saved=data.get("images_saved", 0),
            filename_metadata=None,  # Legacy files don't have this
            rename_history=rename_history,
        )

    def to_yaml_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        result = {
            "source_file": self.source_file,
            "original_filename": self.original_filename,
            "processed_at": self.processed_at.isoformat(),
            "content_length": self.content_length,
            "include_page_headlines": self.include_page_headlines,
            "images_saved": self.images_saved,
        }

        if self.rename_history:
            result["rename_history"] = [
                {
                    "from_name": event.from_name,
                    "to_name": event.to_name,
                    "timestamp": event.timestamp.isoformat(),
                    "confidence": event.confidence,
                }
                for event in self.rename_history
            ]

        if self.filename_metadata:
            result["filename_metadata"] = {
                "generated_filename": self.filename_metadata.generated_filename,
                "generation_timestamp": self.filename_metadata.generation_timestamp.isoformat(),
                "generation_method": self.filename_metadata.generation_method,
                "confidence": self.filename_metadata.confidence,
                "extracted_date": self.filename_metadata.extracted_date,
                "extracted_company": self.filename_metadata.extracted_company,
                "extracted_summary": self.filename_metadata.extracted_summary,
                "pages_analyzed": self.filename_metadata.pages_analyzed,
            }

        return result
```

## 12. Complete Data Flow

Putting it all together: here is what happens when you run `ocr run invoice.pdf --rename`.

```
ocr run invoice.pdf --rename
         │
         ▼
main.py  main()  ──────────────────────────────────┐
  asyncio.run(_main(...))                           │
         │                                          │
         ▼                                          │
  expand_paths([invoice.pdf])                       │
  Settings() ── reads .env ── MISTRAL_API_KEY       │
  MistralOCRAdapter(settings, shared_client)        │
  FilenameGenerator(settings, shared_client)        │
  OutputManager()                                   │
         │                                          │
         ▼                                          │
  _process_single_file()                            │
         │                                          │
         ▼                                          │
  _generate_filename_for_file()                     │
   ├── CacheManager.get_cached_filename()           │
   │   └── miss → continue                         │
   ├── CacheManager.get_cached_markdown()           │
   │   └── miss → continue                         │
   ├── ocr_service.process_first_page()             │
   │      └── MistralAdapter:                      │
   │           _validate_image_file()              │
   │           _encode_file()        ── base64     │
   │           POST /ocr (page 1 only)             │
   │           _generate_markdown()                │
   │           _collect_images_map() → JSON header │
   ├── filename_generator.analyze_content()         │
   │      └── POST /chat (mistral-small-2506)      │
   │           → {date, company, summary, conf=0.8}│
   └── confidence 0.8 >= 0.7 → accept             │
         │                                          │
         ▼                                          │
  ocr_service.process_file() (all pages, images)   │
         │                                          │
         ▼                                          │
  OutputManager.save_text_result()                  │
   ├── strip <!--IMAGES_MAP ... --> header          │
   ├── _materialize_images()                        │
   │    ├── images_map → .ocr/images/invoice_1.jpg │
   │    └── rewrite ![](img-0.jpg) → local path    │
   ├── build OCRMetadata + YAML frontmatter         │
   └── write .ocr/invoice.md                        │
         │                                          │
         ▼                                          │
  FileRenamer.rename_file_pair()                    │
   ├── resolve_collision()                          │
   ├── invoice.pdf  →  2024-01-15 - Acme - Invoice.pdf
   ├── .ocr/invoice.md → .ocr/2024-01-15 - Acme - Invoice.md
   └── log_rename_to_frontmatter()                  │
                                                    │
  ◄──────────────────────────────────────────────────┘
```

## 13. Output File Format

A finished `.ocr/*.md` file looks like this:

```markdown
---
source_file: /path/to/invoice.pdf
original_filename: invoice.pdf
processed_at: 2024-01-15T10:30:00
content_length: 4521
include_page_headlines: true
images_saved: 2
filename_metadata:
  generated_filename: 2024-01-15 - Acme Corp - Invoice
  generation_timestamp: 2024-01-15T10:30:01
  generation_method: mistral-small-2506
  confidence: 0.9
  extracted_date: "2024-01-15"
  extracted_company: Acme Corp
  extracted_summary: Invoice for consulting services Q4
  pages_analyzed: 1
rename_history:
  - from_name: invoice.pdf
    to_name: 2024-01-15 - Acme Corp - Invoice.pdf
    timestamp: 2024-01-15T10:30:02
    confidence: 0.9
---

### Page 1
...extracted markdown content...

![Figure 1](images/invoice_1.jpg)
```

The YAML block is both human-readable documentation and the cache that `CacheManager` reads on the next run.

## 14. Key Design Decisions

| Decision | Rationale |
|---|---|
| Shared Mistral client | One HTTP connection pool across OCR and chat calls; avoids authentication overhead per request |
| YAML frontmatter as cache | Zero extra infrastructure — the output file IS the cache |
| Two-phase OCR | Cheap first-page scan covers most structured documents; expensive full scan only when needed |
| Three-source image extraction | Mistral returns images three different ways depending on document type; all must be handled |
| `.ocr/` subdirectory | Keeps source folders clean; single directory to `.gitignore` |
| `asyncio.run()` at CLI boundary | Keeps all business logic async while preserving a simple synchronous CLI surface |
| Protocol-based adapter | Swapping OCR providers requires only a new file implementing three methods |
| File-based locks | Works across processes (watch mode + manual run) without requiring a separate lock server |

## 15. Adding a New OCR Provider

Because the codebase uses a protocol-based design, adding a provider (e.g. Google Document AI) requires:

1. Create `src/ocr/adapters/google_adapter.py` implementing `OCRService`.
2. Implement `process_file()`, `process_files()`, `process_folder()` with the same return signature: `Tuple[str, int, int]` (markdown, image count, pages processed).
3. Embed the images map in the same `<!--IMAGES_MAP ... -->` format so `OutputManager` can materialise them without changes.
4. In `main.py` swap the adapter instantiation line — everything else (caching, renaming, output) continues to work unchanged.

```bash
grep -n 'MistralOCRAdapter\|FilenameGenerator\|OutputManager\|CacheManager' src/ocr/main.py | grep -v '^\s*#' | head -15
```

```output
18:from .adapters.mistral_adapter import MistralOCRAdapter
19:from .utils.output_manager import OutputManager
20:from .services.filename_generator import FilenameGenerator
21:from .utils.cache_manager import CacheManager
260:    ocr_service: MistralOCRAdapter,
261:    filename_generator: FilenameGenerator,
262:    output_manager: OutputManager,
297:    cached_filename = CacheManager.get_cached_filename(file_path, force=force_filename)
309:    markdown_content = CacheManager.get_cached_markdown(file_path) if not force_ocr else None
383:        ocr_service = MistralOCRAdapter(settings, shared_client)
386:        output_manager = OutputManager(output_dir, save_at_input_location)
398:            filename_generator = FilenameGenerator(settings, shared_client)
534:        output_manager = OutputManager(output_dir, save_at_input_location)
588:                                ocr_service = MistralOCRAdapter(settings, shared_client)
589:                                filename_generator = FilenameGenerator(settings, shared_client)
```

```bash
sed -n '375,400p' src/ocr/main.py
```

```output
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
```
