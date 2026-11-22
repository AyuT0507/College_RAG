from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_name: str = "College AI Assistant"
    secret_key: str = "development-only-change-me"
    token_encryption_key: str = ""
    database_url: str = "sqlite:///./data/college_ai.db"
    chroma_path: str = "./chroma_db"
    upload_dir: str = "./data/uploads"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    google_client_secrets_file: str = "./credentials/google-client-secret.json"
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    website_allowed_domains: str = "iiitdmj.ac.in,www.iiitdmj.ac.in"
    allowed_email_domain: str = "iiitdmj.ac.in"
    max_upload_mb: int = 25


@lru_cache
def get_settings() -> Settings:
    return Settings()
