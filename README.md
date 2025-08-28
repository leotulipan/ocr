# OCR Tool

A command-line OCR tool using Mistral AI for document processing.

### Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

#### Global Installation (Recommended)

**Option 1: Using uv tool install (Works globally)**
```bash
# Clone the repository
git clone <repository-url>
cd OCR

# Build the wheel package
uv build --wheel

# Install globally using uv tool
uv tool install dist/ocr-0.1.0-py3-none-any.whl

# Update shell PATH (if needed)
uv tool update-shell

# Test global installation
ocr --help
```

**Option 2: Development Installation**
```bash
# Clone the repository
git clone <repository-url>
cd OCR

# Install in development mode
uv pip install -e .

# Run the tool
uv run ocr --help
```

### Usage

```bash
# Process a single file
ocr process-file --file document.pdf

# Process multiple files
ocr process-files --files file1.pdf file2.pdf

# Process a folder
ocr process-folder --folder /path/to/folder

# Include page headlines
ocr process-file --file document.pdf --page-headlines

# Specify page range
ocr process-file --file document.pdf --pages "1-3,5-7"

# Specify output directory
ocr process-file --file document.pdf --output /path/to/output
```

### Environment Setup

Create a `.env` file in the project root:
```
MISTRAL_API_KEY=your_mistral_api_key_here
```

### Uninstall

```bash
# Remove global installation
uv tool uninstall ocr

# Remove development installation
uv pip uninstall ocr
```

### Troubleshooting

**OneDrive Issues**: If you encounter permission errors during installation, move the project to a local directory (e.g., `C:\Users\leona\Scripts\OCR`) instead of OneDrive.

**Global Command Not Found**: If `ocr` command is not found after installation:
1. Run `uv tool update-shell` to update PATH
2. Restart your terminal
3. Check if `C:\Users\leona\.local\bin` is in your PATH

#### Initial Setup

was done with these settings

```bash
uv init --name "Template"--no-description --author-from git --bare --app
uv add python-dotenv loguru requests argparse
uv venv
```

when you have uv installed you do not need to run these commands again