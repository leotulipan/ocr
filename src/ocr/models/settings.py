"""Application settings configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    mistral_api_key: SecretStr
    max_retries: int = 3
    timeout: int = 30
    
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')
