import os
import secrets
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = Path(os.getenv("NW_DATA_DIR", ROOT_DIR / "data"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
    )

    app_name: str = "Novel Workbench API"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:8765"]
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'novel_workbench.db'}"
    secret_key_path: Path = DATA_DIR / ".secret_key"
    mcp_access_token: str = Field(default="", alias="NW_MCP_ACCESS_TOKEN")


def _resolve_mcp_token(settings: "Settings") -> str:
    if settings.mcp_access_token:
        return settings.mcp_access_token
    token_file = DATA_DIR / ".mcp_token"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if token_file.exists():
        return token_file.read_text().strip()
    token = secrets.token_urlsafe(32)
    token_file.write_text(token)
    return token


settings = Settings()
settings.mcp_access_token = _resolve_mcp_token(settings)
