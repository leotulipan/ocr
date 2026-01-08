"""Environment setup utilities for .env file management."""

import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console


def find_env_file() -> Optional[Path]:
    """
    Find .env file in the following order:
    1. Current directory
    2. User home directory (C:\\Users\\{username}\\.env)

    Returns:
        Path to .env file if found, None otherwise
    """
    # Check current directory first
    current_env = Path.cwd() / '.env'
    if current_env.exists():
        return current_env

    # Check user home directory
    home_env = Path.home() / '.env'
    if home_env.exists():
        return home_env

    return None


def setup_env_file() -> Path:
    """
    Setup .env file for the application.

    If no .env file exists in current directory or home directory,
    copies .env.example to user home directory and notifies user.

    Returns:
        Path to the .env file (existing or newly created)
    """
    console = Console()

    # Check if .env already exists
    env_file = find_env_file()
    if env_file:
        return env_file

    # No .env found, create one from .env.example
    home_env = Path.home() / '.env'

    # Find .env.example file (should be in package directory)
    # Try multiple locations
    example_locations = [
        Path.cwd() / '.env.example',
        Path(__file__).parent.parent.parent.parent / '.env.example',  # Project root
    ]

    env_example = None
    for location in example_locations:
        if location.exists():
            env_example = location
            break

    if env_example:
        # Copy .env.example to home directory
        shutil.copy(env_example, home_env)
        console.print(f"\n[yellow]⚠️  Configuration required![/yellow]")
        console.print(f"[cyan]A configuration file has been created at:[/cyan]")
        console.print(f"[green]{home_env}[/green]\n")
        console.print("[yellow]Please edit this file and add your Mistral API key.[/yellow]")
        console.print("[cyan]Get your API key from:[/cyan] https://console.mistral.ai/\n")
    else:
        # Create a basic .env file manually
        with open(home_env, 'w') as f:
            f.write("# OCR Configuration File\n")
            f.write("# Get your API key from: https://console.mistral.ai/\n\n")
            f.write("MISTRAL_API_KEY=your-mistral-api-key-here\n")

        console.print(f"\n[yellow]⚠️  Configuration required![/yellow]")
        console.print(f"[cyan]A configuration file has been created at:[/cyan]")
        console.print(f"[green]{home_env}[/green]\n")
        console.print("[yellow]Please edit this file and add your Mistral API key.[/yellow]")
        console.print("[cyan]Get your API key from:[/cyan] https://console.mistral.ai/\n")

    return home_env


def get_env_file_path() -> str:
    """
    Get the path to use for .env file loading.

    Returns:
        String path to .env file for pydantic-settings
    """
    env_file = find_env_file()
    if env_file:
        return str(env_file)

    # If no .env exists, setup will be called by Settings initialization
    # Return home directory path as default
    return str(Path.home() / '.env')
