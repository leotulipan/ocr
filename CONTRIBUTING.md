# Contributing

## Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd OCR

# Install dependencies (including dev tools)
uv sync --group dev

# Install in editable mode
uv pip install -e .
```

## Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=ocr --cov-report=html

# Run specific test file
uv run pytest tests/test_page_parser.py
```

**Note:** All tests are unit tests that run without a Mistral API key. Integration tests (end-to-end OCR with real API calls) are not yet implemented. For manual integration testing, use `ocr_test/max_mustermann_brief.png` -- expected rename: `2026-03-19 - Max Mustermann - Anfrage Datenschutz.png`.

## Linting

```bash
# Check for issues
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check --fix src/ tests/

# Check formatting
uv run ruff format --check src/ tests/

# Auto-format
uv run ruff format src/ tests/
```

## Code Style

- Line length: 120 characters
- Python 3.12+ features encouraged
- Type hints for function signatures
- Async/await for all I/O operations

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure `uv run pytest` and `uv run ruff check src/ tests/` pass
4. Submit a PR with a clear description of changes

## Project Structure

```
src/ocr/          # Main package
tests/            # Test suite
.github/workflows/ # CI/CD pipelines
```
