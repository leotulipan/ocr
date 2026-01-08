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
