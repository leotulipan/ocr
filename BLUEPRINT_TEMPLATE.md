# Python CLI Application Blueprint

## Core Architecture Patterns

### 1. UV Project Management
```bash
uv init --name "project" --no-description --author-from git --bare --app
uv add <package>  # Dependencies via pyproject.toml
uv run <script>   # Consistent environment execution
uv sync          # Reproducible environments via uv.lock
uv build         # Distribution packages
```

### 2. CLI Structure (Typer)
Type-hint driven CLI with automatic validation:
```python
import typer
from pathlib import Path
from typing import Optional

app = typer.Typer()

@app.command()
def process(
    file: Path = typer.Option(..., "--file", "-f", exists=True),
    output: Optional[str] = typer.Option(None, "--output", "-o")
):
    """Process input file with validation."""  # Docstring for help text
    if not validate_inputs(file):
        raise typer.Exit(1)
    return run_pipeline(file, output)

if __name__ == "__main__":
    app()
```

### 3. Project Structure
```
project/
├── src/project/
│   ├── __init__.py
│   ├── __main__.py      # Entry point
│   ├── main.py          # Core orchestration
│   ├── utils/
│   │   ├── exceptions.py
│   │   ├── output_manager.py
│   │   └── validators.py
│   ├── protocols/       # Protocol definitions
│   ├── adapters/        # External service interfaces
│   ├── models/          # Pydantic data models
│   └── workers/         # Async processing
├── tests/
├── docs/               # MkDocs documentation
├── pyproject.toml
├── uv.lock
├── .env
├── TASKS.md
└── build.py            # PyInstaller script
```

### 4. Component Architecture
- **Protocols**: Define interfaces using structural subtyping
- **Adapters**: Protocol-based external service integration
- **Unified Data Models**: Pydantic for validation and serialization
- **Output Manager**: Centralized file I/O with metadata tracking
- **Worker Pool**: Async/concurrent processing with queues

```python
from typing import Protocol

class TranscriptionService(Protocol):
    """Protocol for transcription services."""
    async def transcribe(self, audio: bytes) -> str:
        """Transcribe audio to text."""
        ...
```

### 5. Async Processing & HTTP
```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def fetch_data(url: str) -> dict:
    """Fetch data with automatic retry logic."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def process_pipeline():
    """Main async pipeline with worker pool."""
    queue = asyncio.Queue()
    workers = [asyncio.create_task(worker(queue)) for _ in range(WORKERS)]
    await queue.join()
```

### 6. Rich CLI Output
```python
from rich.console import Console
from rich.progress import track
from rich.table import Table

console = Console()

def process_files(files: list[Path]):
    """Process files with progress bar."""
    for file in track(files, description="Processing..."):
        # Processing logic
        console.print(f"✓ Processed [green]{file.name}[/green]")
```

### 7. Configuration
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    """Application settings with environment variable support."""
    api_key: SecretStr
    max_retries: int = 3
    
    model_config = SettingsConfigDict(env_file='.env')
```

### 8. Error Handling
```python
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10)
)
async def api_call():
    """API call with sophisticated retry strategy."""
    ...
```

### 9. Testing with Async Support
```python
import pytest
import pytest_asyncio

@pytest_asyncio.fixture
async def client():
    """Async fixture for test client."""
    async with httpx.AsyncClient() as client:
        yield client

@pytest.mark.asyncio
async def test_api_call(client):
    """Test async API call."""
    result = await fetch_data("https://api.example.com")
    assert result is not None
```

### 10. Documentation
**Every function/class needs docstrings:**
```python
def process_data(input_file: Path, output_format: str) -> dict:
    """
    Process input data and return formatted output.
    
    Args:
        input_file: Path to input file
        output_format: Desired output format (json, csv, xml)
    
    Returns:
        Processed data as dictionary
    
    Raises:
        ValueError: If input file format is unsupported
    """
```

**MkDocs configuration** (`mkdocs.yml`):
```yaml
site_name: Project Documentation
theme:
  name: material
plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            show_source: true
```

### 11. FastAPI Integration (Optional, only when we want to expose an API - check TASKS.md if unsure)
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class ProcessRequest(BaseModel):
    """Request model for processing endpoint."""
    file_path: str
    options: dict

@app.post("/process")
async def process_endpoint(request: ProcessRequest):
    """Process file via API endpoint."""
    try:
        result = await process_file(request.file_path)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 12. Build & Distribution
```toml
[project]
dependencies = [
    "typer>=0.9.0",
    "httpx>=0.25.0",
    "rich>=13.0.0",
    "tenacity>=8.2.0",
    "pydantic-settings>=2.0.0",
    "fastapi>=0.100.0",  # if needed
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
    "mkdocs-material>=9.0.0",
    "mkdocstrings[python]>=0.24.0",
]

[project.scripts]
project-cli = "project.main:app"

[tool.ruff]
line-length = 88
target-version = "py312"
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "SIM", "ARG"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 13. Configuration

Priority Order: CLI args > env vars > config file > defaults
Locations: .env in project/user/system directories
Validation: Pydantic Settings for type-safe config

```python
pythonclass Settings(BaseSettings):
    api_key: SecretStr
    model_config = SettingsConfigDict(env_file='.env')
```

### 14. Task Management

Chack or create a TASKS.md before starting any programming listing out tasks and subtasks
Split into sprints (noting future sprints under the corresponding heading)

TASKS.md Structure:
```markdown
## Done 
[x] example done task
## In Progress 
[ ] example programming task
  [ ]  subtask example
## Future 
[ ] example future task

## Implementation Plan
```

### 15. Testing Strategy

pytest with async support
pytest-cov for coverage
pytest-mock for external dependencies
Fixtures for common test data

## Design Principles
1. **Type-Driven Development**: Leverage type hints for validation
2. **Protocol-Oriented**: Use protocols for flexible interfaces
3. **Documentation-First**: Comprehensive docstrings for auto-docs
4. **Async-Native**: httpx and async/await throughout
5. **Rich User Experience**: Progress bars, tables, colored output
6. **Resilient Operations**: Sophisticated retry strategies with tenacity
7. **Test Coverage**: Async-aware testing with fixtures

## Modern Python Stack
- **`typer`**: Type-hint driven CLI framework
- **`httpx`**: Async HTTP client
- **`rich`**: Beautiful terminal output
- **`tenacity`**: Advanced retry logic
- **`pytest-asyncio`**: Async test support
- **`ruff`**: Fast, comprehensive linting
- **`mkdocs-material`**: Auto-generated documentation
- **`fastapi`**: Modern web API framework (when needed)
- **Protocols**: Structural subtyping for flexibility
- **Pydantic**: Data validation and settings management