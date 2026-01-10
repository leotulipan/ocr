# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A command-line OCR tool that uses Mistral AI's OCR API to extract text and images from documents (PDF, PPTX, DOCX) and images (PNG, JPG, AVIF). The tool outputs markdown files with YAML frontmatter metadata and materializes embedded images locally. It features intelligent filename generation using Mistral's chat API to analyze document content and suggest descriptive filenames.

## Development Setup

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Install dependencies in development mode
uv pip install -e .

# Run the tool
uv run ocr --help

# Run with a file
uv run ocr document.pdf

# Build wheel package
uv build --wheel

# Install globally for system-wide access
uv tool install --editable .
```

### Environment Variables

The application automatically creates a `.env` file in the user's home directory on first run if the API key is missing. You can also create a `.env` file in the project root or current working directory (takes precedence):

```
MISTRAL_API_KEY=your_mistral_api_key_here
```

**Note:** The application uses `MISTRAL_API_KEY` (see `src/ocr/models/settings.py`). The `.env` file is created automatically via `utils/env_setup.py` if missing.

## Running Commands

### Basic OCR Processing
```bash
# Process a single file
uv run ocr document.pdf
# or when installed globally
ocr document.pdf

# Process multiple files
ocr file1.pdf file2.pdf file3.pdf

# Process entire folder
ocr ./invoices/

# Process with page selection
ocr document.pdf --pages "1-3"
ocr document.pdf --pages "5-"

# Show version
ocr --version

# CLI help
ocr --help
```

### Intelligent Filename Generation
```bash
# Generate and apply intelligent filename
ocr invoice.pdf --rename

# Preview suggested filename (dry-run with simple output)
ocr invoice.pdf --dry-run

# Preview with verbose output (shows all processing steps)
ocr invoice.pdf --dry-run --verbose

# Set custom confidence threshold (default: 0.7)
ocr invoice.pdf --rename --confidence 0.8

# Rename with confirmation prompt
ocr invoice.pdf --rename --confirm

# Force regenerate filename (ignore cache)
ocr invoice.pdf --rename --force

# Batch rename all files in folder (simple output)
ocr ./invoices/ --rename --dry-run

# Batch rename with verbose output
ocr ./invoices/ --rename --dry-run --verbose
```


## Architecture

### Core Structure

The codebase follows a clean architecture pattern with clear separation of concerns:

```
src/ocr/
├── main.py                      # Typer CLI - unified command handler (v0.3.0)
├── __main__.py                  # Entry point
├── adapters/                    # External service implementations
│   └── mistral_adapter.py       # Mistral AI OCR API integration
├── models/                      # Data models
│   ├── settings.py              # Pydantic settings with .env support
│   └── metadata.py              # OCRMetadata and FilenameMetadata models
├── protocols/                   # Interface definitions
│   └── ocr_service.py           # OCRService protocol
├── services/                    # Business logic
│   └── filename_generator.py   # Intelligent filename generation with Mistral chat API
├── utils/                       # Utility modules
│   ├── output_manager.py        # File output and image materialization
│   ├── cache_manager.py         # OCR metadata caching to avoid re-processing
│   ├── file_renamer.py          # Safe file renaming with collision detection
│   ├── page_parser.py           # Page pattern parsing (e.g., "1-3,5-")
│   └── env_setup.py             # Automatic .env file setup
└── workers/                     # (Reserved for future use)
```

### Key Components

**MistralOCRAdapter** (`adapters/mistral_adapter.py`)
- Implements the OCRService protocol
- Handles file encoding to base64 and MIME type detection
- Validates image file headers before processing (prevents corrupted files)
- Processes files/folders using Mistral's OCR API with `include_image_base64=True`
- Filters pages based on patterns via `PagePatternParser` (e.g., "1-3,5-")
- Embeds image metadata in markdown as HTML comment with JSON-encoded images map
- Provides `process_first_page()` method for efficient filename generation

**FilenameGenerator** (`services/filename_generator.py`)
- Uses Mistral chat API (`mistral-small-2506`) to analyze document content
- Extracts structured information: ISO date, company name, summary
- **NEW (v0.7.0)**: Accepts current filename as HIGH PRIORITY context for extraction
- Returns `FilenameMetadata` with confidence level (0.0-1.0 scale)
- Follows pattern: `{ISO-date} - {Company} - {Summary}`
- Sanitizes filenames to remove Windows/Unix forbidden characters
- Two-phase approach: first page analysis, then full document if confidence < threshold (default 0.7)
- Confidence threshold configurable via `--confidence` CLI option

**OutputManager** (`utils/output_manager.py`)
- Manages output file locations with `.ocr` subdirectory structure (v0.2.2+)
- Single-page documents: `.pg1.md`, multi-page: `.md`
- Extracts images map from markdown HTML comment header
- Materializes images from three sources:
  1. Base64 data URIs in markdown
  2. External HTTP/HTTPS URLs in markdown
  3. Images map (filenames → base64 data from Mistral API)
- Saves images to `images/` subdirectory alongside markdown files
- Rewrites markdown image references to local file paths
- Adds YAML frontmatter metadata header (includes `filename_metadata` and `original_filename`)

**CacheManager** (`utils/cache_manager.py`)
- Locates existing OCR markdown files in `.ocr` subdirectory
- Extracts metadata from YAML frontmatter (or legacy HTML comments)
- Returns cached `FilenameMetadata` to avoid regeneration
- Returns cached markdown content to avoid re-OCR
- Supports both new `.ocr` subdirectory and legacy file locations

**FileRenamer** (`utils/file_renamer.py`)
- Safely renames both source file and OCR markdown file in sync
- Detects and resolves filename collisions with counter suffix (`_2`, `_3`, etc.)
- Handles both `.ocr` subdirectory and legacy file locations
- Provides confirmation prompts via Rich console
- Includes rollback on failure

**Settings** (`models/settings.py`)
- Uses pydantic-settings to load configuration from `.env`
- Required: `MISTRAL_API_KEY`
- Optional: `max_retries` (default: 3), `timeout` (default: 30)
- Filename generation settings: `filename_generation_model`, `filename_generation_max_tokens`, `filename_generation_temperature`
- Auto-creates `.env` file via `env_setup.py` if missing

### Data Flow

#### Standard OCR Processing
1. **CLI Command** → `main.py` receives unified command with files/folders/patterns (v0.3.0)
2. **Path Expansion** → `expand_paths()` converts folders to file lists
3. **Settings Loading** → `Settings()` reads `.env` and validates configuration
4. **Adapter Initialization** → `MistralOCRAdapter` created with settings
5. **File Processing**:
   - File validated and encoded to base64 with data URL
   - Mistral OCR API called with `include_image_base64=True`
   - Response filtered by page pattern if provided via `PagePatternParser`
   - Markdown generated with optional page headlines
   - Images map embedded as HTML comment in markdown
6. **Output Handling**:
   - `OutputManager` determines output location (`.ocr` subdirectory)
   - Images extracted and saved from map/data URIs/URLs
   - Markdown rewritten with local image paths
   - YAML frontmatter metadata header added
   - Files saved to `.ocr/filename.md` or `.ocr/filename.pg1.md`

#### Intelligent Filename Generation Flow
1. **Cache Check** → `CacheManager` checks for existing `FilenameMetadata`
2. **First Page Analysis** (if not cached):
   - OCR first page only via `process_first_page()`
   - `FilenameGenerator` analyzes content + current filename using Mistral chat API (v0.7.0+)
   - Current filename treated as HIGH PRIORITY source for dates and keywords
   - Returns `FilenameMetadata` with confidence level (0.0-1.0)
3. **Confidence Check**:
   - If confidence < threshold (default 0.7, configurable via `--confidence`), process all pages and re-analyze
   - If confidence >= threshold, proceed with generated filename
4. **Output Modes** (v0.7.0+):
   - **Simple mode** (default): Clean one-line output per file: `filename (Confidence: X.X)`
   - **Verbose mode** (`--verbose`): Show all processing steps, progress bars, and detailed logs
5. **Output Saving**:
   - Save OCR markdown with `filename_metadata` in YAML frontmatter
   - This creates cache for future runs
6. **File Renaming** (if `--rename`):
   - `FileRenamer` checks for collisions
   - Renames both source file and OCR markdown in sync
   - Adds counter suffix if collision detected

### Output Structure

Files are saved in a `.ocr` subdirectory next to the source file:

```
document.pdf
.ocr/
├── document.md          # Multi-page OCR result
├── document.pg1.md      # Single-page OCR result
└── images/              # Materialized images
    ├── document_1.jpg
    └── document_2.png
```

YAML frontmatter includes:
- `source_file`: Absolute path to original file
- `original_filename`: Filename before any renaming
- `processed_at`: Timestamp
- `content_length`: Length of markdown content
- `include_page_headlines`: Boolean flag
- `images_saved`: Count of materialized images
- `filename_metadata`: Object with generation details, confidence, extracted fields

### Supported File Types

- **Documents**: `.pdf`, `.pptx`, `.docx` (via `document_url` field in Mistral API)
- **Images**: `.png`, `.jpg`, `.jpeg`, `.avif` (via `image_url` field in Mistral API)

## Important Implementation Details

### Image Handling

The adapter uses `include_image_base64=True` in the Mistral API call to receive embedded images. Images are returned in the response pages and are collected into a map that is embedded in the markdown as:

```html
<!--IMAGES_MAP
{"img-0.jpg": {"mime": "image/jpeg", "base64": "..."}, ...}
-->
```

This map is parsed by OutputManager to materialize the images into local files.

### Page Pattern Syntax

The `--pages` flag accepts patterns:
- Single page: `"5"`
- Range: `"1-3"` (pages 1, 2, 3)
- Open-ended range: `"5-"` (page 5 to end), `"-3"` (pages 1 to 3)
- Multiple: `"1-3,5,7-"` (pages 1, 2, 3, 5, and 7 to end)

### CLI Architecture (v0.3.0 Unified Command)

The CLI was simplified in v0.3.0 to use a single unified command instead of subcommands:
- **Before**: `ocr process-file --file document.pdf`
- **After**: `ocr document.pdf`

The `main()` function in `main.py`:
1. Accepts variadic `paths` argument (files, folders, or both)
2. Calls `expand_paths()` to convert folders to file lists
3. Determines if single-file or batch mode based on file count
4. Routes to `_process_single_file()` or `_process_multiple_files()`

Both single and batch modes support all flags (`--rename`, `--dry-run`, `--confirm`, `--force`).

### Async Architecture

All processing methods are async and called via `asyncio.run()` in the CLI commands. This allows for future parallelization of API calls. The `FilenameGenerator` uses `client.chat.complete_async()` for non-blocking chat API calls.

## Common Development Tasks

### Adding a new OCR provider

1. Create new adapter in `adapters/` implementing the `OCRService` protocol
2. Implement `process_file()`, `process_files()`, and `process_folder()` methods
3. Return markdown with optional images map header (see `MistralOCRAdapter` for format)
4. Update `main.py` to instantiate new adapter instead of `MistralOCRAdapter`

### Modifying output format

- **Metadata format**: Edit `OutputManager.save_text_result()` to change YAML frontmatter structure
- **Image extraction**: Edit `OutputManager._materialize_images()` to change how images are extracted and saved
- **Filename pattern**: Edit `FilenameGenerator.SYSTEM_PROMPT` to change AI analysis instructions

### Adding new CLI options

1. Add parameters to `main()` function in `main.py` with `typer.Option()`
2. Pass new parameters to `_process_single_file()` and `_process_multiple_files()`
3. Update adapter/output manager method signatures as needed

### Modifying filename generation logic

The filename generation prompt is in `FilenameGenerator.SYSTEM_PROMPT`. Key points:
- Uses Mistral chat API for content analysis
- Returns JSON with `date`, `company`, `summary`, `confidence`
- Two-phase approach: first page, then all pages if confidence is low
- Confidence threshold check is in `main.py:_process_single_file()` (line ~183)

### Working with caching

- Cache lookup: `CacheManager.get_cached_filename()` and `CacheManager.get_cached_markdown()`
- Cache is stored in YAML frontmatter of `.ocr/*.md` files
- To force regeneration: use `--force` flag which bypasses cache
- Cache location: `.ocr` subdirectory next to source files

## Version Information

Current version: **v0.7.0** (see `src/ocr/__init__.py`)

Major changes by version:
- **v0.7.0**: Enhanced output formatting with `--verbose` mode, configurable confidence threshold (`--confidence`), filename-based metadata extraction
- **v0.6.0**: Image descriptions enabled by default, rename confirmation, file concatenation
- **v0.5.0**: AI-powered image descriptions
- **v0.4.0**: Numeric confidence scoring
- **v0.3.0**: Unified CLI command (removed subcommands)
- **v0.2.2**: `.ocr` subdirectory structure, page-based naming (`.pg1.md` vs `.md`)
- **v0.2.0**: Intelligent filename generation, YAML frontmatter
- **v0.1.0**: Initial OCR functionality