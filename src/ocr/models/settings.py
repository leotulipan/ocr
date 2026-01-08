"""Application settings configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    mistral_api_key: SecretStr
    max_retries: int = 3
    timeout: int = 30

    # Filename generation settings
    filename_generation_model: str = "mistral-small-2506"
    filename_generation_max_tokens: int = 500  # Larger for full-document analysis
    filename_generation_temperature: float = 0.0  # Deterministic

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')
