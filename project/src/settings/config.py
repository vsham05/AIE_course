import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    app_name: str = "SQLGen API"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8000
    

    classifier_model_dir: str = "artifacts/bert_bird_finetuned/checkpoint-6188"

    ollama_base_url: str = "http://localhost:11434"
    
    llm_model_name: str = "qwen3:1.7b"
    
    ollama_timeout: int = 90
    llm_temperature: float = 0.1
    
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    """Кэшированный инстанс настроек (singleton)."""
    return Settings()