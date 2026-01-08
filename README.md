# OCR Tool

A command-line OCR tool using Mistral AI for document processing with intelligent filename generation.

## Features

- 📄 **Document OCR**: Extract text from PDFs, images, and Office documents (PPTX, DOCX)
- 🤖 **Intelligent Filename Generation**: Automatically generates descriptive filenames from document content
- 💾 **Smart Caching**: Reuses OCR results to avoid redundant API calls
- 🎯 **Flexible Page Selection**: Process specific pages or page ranges
- 📝 **Markdown Output**: Save results with YAML frontmatter metadata
- 🖼️ **Image Extraction**: Automatically extracts and saves embedded images
- 🔧 **System-Wide Installation**: Install once, use anywhere

## Installation

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Install Globally

```bash
# Clone the repository
git clone <repository-url>
cd OCR

# Install globally with uv
uv tool install --editable .

# Verify installation
ocr --version
```

### Development Installation

```bash
# Clone and install in development mode
git clone <repository-url>
cd OCR
uv pip install -e .
```

## Configuration

### API Key Setup

The tool requires a Mistral AI API key. On first run, it will automatically create a configuration file at:

**Windows:** `C:\Users\{your-username}\.env`
**Linux/Mac:** `~/.env`

Edit this file and add your API key:

```env
# OCR Configuration File
# Get your API key from: https://console.mistral.ai/

MISTRAL_API_KEY=your-mistral-api-key-here
```

**Note:** You can also place a `.env` file in your current working directory, which will take precedence over the home directory configuration.

### Get Your API Key

1. Visit [Mistral AI Console](https://console.mistral.ai/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key to your `.env` file

## Usage

### Basic OCR

```bash
# Process a single file
ocr process-file --file document.pdf

# Process multiple files
ocr process-files --files file1.pdf file2.pdf file3.pdf

# Process all files in a folder
ocr process-folder --folder /path/to/documents
```

### Page Selection

```bash
# Process specific pages
ocr process-file --file document.pdf --pages "1-3"

# Process page ranges
ocr process-file --file document.pdf --pages "1-5,10-15"

# Process from page 5 to end
ocr process-file --file document.pdf --pages "5-"

# Include page numbers as headlines
ocr process-file --file document.pdf --page-headlines
```

### Output Options

```bash
# Save to specific directory
ocr process-file --file document.pdf --output /path/to/output

# By default, single files save in .ocr subdirectory:
# document.pdf → .ocr/document.pg1.md (single page)
# document.pdf → .ocr/document.md (multiple pages)
```

## Intelligent Filename Generation

### Overview

The tool can analyze document content and generate descriptive filenames following the pattern:

```
{ISO-date} - {Company} - {Summary}.{ext}
```

**Examples:**
- `2024-12-01 - Medivere - Befund Julia.pdf`
- `2024-09-03 - WKO - Mahnung Privat.pdf`
- `2020-06-15 - Erste Bank - Eingänge.xlsx`

### Usage

```bash
# Generate and apply intelligent filename
ocr process-file --file invoice.pdf --rename

# Preview suggested filename (dry-run)
ocr process-file --file invoice.pdf --dry-run

# Ask for confirmation before renaming
ocr process-file --file invoice.pdf --rename --confirm

# Force regenerate filename (ignore cache)
ocr process-file --file invoice.pdf --rename --force

# Batch rename all files in a folder
ocr process-folder --folder ./invoices --rename
```

### How It Works

1. **Smart Analysis**: Processes the first page to extract date, company name, and document type
2. **Confidence Check**: If confidence is low, processes all pages for better accuracy
3. **Caching**: Stores generated filenames in metadata to avoid regeneration
4. **Safe Renaming**: Renames both original file AND OCR markdown file to keep them in sync
5. **Collision Handling**: Automatically adds counter suffix (`_2`, `_3`, etc.) if filename exists

### Filename Generation Flags

| Flag | Description |
|------|-------------|
| `--rename` | Enable intelligent filename generation and renaming |
| `--dry-run` | Show suggested filename without renaming |
| `--confirm` | Ask for confirmation before each rename |
| `--force` | Force regenerate filename even if cached |

## Output Format

OCR results are saved in a `.ocr` subdirectory as Markdown files with YAML frontmatter:

### File Structure

```
your-document.pdf
.ocr/
├── your-document.pg1.md    # Single-page document
├── your-document.md        # Multi-page document
└── images/                 # Extracted images
    ├── your-document_1.jpg
    └── your-document_2.png
```

### Markdown Format

```markdown
---
source_file: /path/to/document.pdf
original_filename: scan001.pdf
processed_at: 2026-01-08T15:30:45.123456
content_length: 15432
include_page_headlines: false
images_saved: 5
filename_metadata:
  generated_filename: 2024-12-01 - Company - Invoice
  generation_timestamp: 2026-01-08T15:30:50
  generation_method: mistral-small-2506
  confidence: high
  extracted_date: 2024-12-01
  extracted_company: Company Name
  extracted_summary: Invoice
  pages_analyzed: 1
---

# Document content here...
```

**Note:** The `original_filename` field preserves the filename before any renaming, allowing you to track the original file name even after intelligent renaming.

## Supported File Types

- **Documents**: PDF, PPTX, DOCX
- **Images**: PNG, JPG, JPEG, AVIF

## Commands Reference

### process-file

Process a single file with OCR.

```bash
ocr process-file [OPTIONS]
```

**Options:**
- `--file, -f PATH` - File to process (required)
- `--output, -o PATH` - Output directory (optional)
- `--page-headlines` - Include page numbers as markdown headlines
- `--pages TEXT` - Page pattern (e.g., '1-3', '5-', '4,5')
- `--rename` - Enable intelligent filename generation
- `--dry-run` - Show suggested filename without renaming
- `--confirm` - Ask for confirmation before renaming
- `--force` - Force regenerate filename even if cached

### process-files

Process multiple files with OCR.

```bash
ocr process-files --files FILE1 FILE2 ... [OPTIONS]
```

### process-folder

Process all supported files in a folder.

```bash
ocr process-folder --folder PATH [OPTIONS]
```

### Global Options

- `--version, -v` - Show version and exit
- `--help` - Show help message

## Cost & Performance

### API Costs (Approximate)

- **First OCR with rename**: ~$0.011 per file
  - OCR: ~$0.01
  - Filename generation: ~$0.001
- **Cached filename reuse**: $0 (no API calls)
- **Force regenerate**: ~$0.001 (chat only, reuses OCR)

### Performance Features

- **Smart Caching**: Reuses existing OCR markdown to avoid redundant processing
- **First-Page Analysis**: Only OCRs first page initially for filename generation
- **Incremental Processing**: Only processes full document if initial confidence is low

## Examples

### Example 1: Basic OCR Workflow

```bash
# Process a document
ocr process-file --file contract.pdf

# Output: .ocr/contract.pg1.md or .ocr/contract.md
```

### Example 2: Intelligent Renaming

```bash
# Generate smart filename
ocr process-file --file scan001.pdf --rename

# Before: scan001.pdf
# After:  2024-12-01 - Acme Corp - Service Agreement.pdf
```

### Example 3: Batch Processing with Renaming

```bash
# Process and rename all PDFs in a folder
ocr process-folder --folder ./invoices --rename

# Each file gets a descriptive name based on its content
```

### Example 4: Preview Before Renaming

```bash
# See what the filename would be without changing anything
ocr process-file --file document.pdf --dry-run

# Output: Suggested filename: 2024-09-15 - Company - Report.pdf
```

## Troubleshooting

### Missing API Key

If you see an error about missing `MISTRAL_API_KEY`:

1. Check that `.env` file exists in your home directory
2. Verify the API key is correctly set
3. Make sure there are no quotes around the key value

### Command Not Found

If `ocr` command is not recognized after installation:

**Windows:**
1. Run `uv tool update-shell`
2. Restart your terminal
3. Check if `%USERPROFILE%\.local\bin` is in your PATH

**Linux/Mac:**
1. Run `uv tool update-shell`
2. Restart your terminal or run `source ~/.bashrc` (or `~/.zshrc`)

### Permission Errors

If you encounter permission errors on Windows with OneDrive:
- Move the project to a local directory (e.g., `C:\Users\{username}\Projects\OCR`)

### Filename Not Generated

If filename generation returns "Document":
- Check that the document has readable text content
- Try using `--force` to regenerate
- Ensure the document contains a date, company name, or description

## Uninstall

```bash
# Remove global installation
uv tool uninstall ocr
```

## Development

### Build from Source

```bash
# Build wheel package
uv build --wheel

# Install from wheel
uv tool install dist/ocr-0.2.2-py3-none-any.whl
```

### Running Tests

```bash
# Install development dependencies
uv sync --group dev

# Run tests (when available)
pytest
```

## Resources

- [Mistral AI Documentation](https://docs.mistral.ai/)
- [Mistral OCR Guide](https://docs.mistral.ai/capabilities/document_ai/basic_ocr/)
- [Mistral OCR Tutorial](https://colab.research.google.com/github/mistralai/cookbook/blob/main/mistral/ocr/tool_usage.ipynb)
- [Batch OCR Examples](https://colab.research.google.com/github/mistralai/cookbook/blob/main/mistral/ocr/batch_ocr.ipynb)
- [Mistral OCR Deep Dive](https://www.cohorte.co/blog/mistral-ocr-a-deep-dive-into-next-generation-document-understanding)

## Version History

### v0.2.2 (Current)
- **New `.ocr` subdirectory structure**: All OCR markdown files now saved in `.ocr` subdirectory for better organization
- **Page-based naming**: Single-page documents use `.pg1.md` suffix, multi-page use `.md` suffix
- **Original filename tracking**: Added `original_filename` field in metadata to preserve pre-rename filenames
- **Dry-run fix**: OCR markdown files now created even in `--dry-run` mode

### v0.2.1
- Added automatic `.env` file setup in user home directory
- Improved configuration file handling with fallback support
- Enhanced user guidance for API key setup

### v0.2.0
- Added intelligent filename generation using Mistral chat API
- Implemented smart caching for OCR results
- Added CLI flags: `--rename`, `--dry-run`, `--confirm`, `--force`
- Switched to YAML frontmatter for metadata
- Added version tracking with `--version` flag

### v0.1.0
- Initial release with basic OCR functionality
- Support for PDFs, images, and Office documents
- Page selection and filtering
- Image extraction and materialization

## License

[Your License Here]

## Author

Leonard Tulipan (leo@leotulipan.at)
