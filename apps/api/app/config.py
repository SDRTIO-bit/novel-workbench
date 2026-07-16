import os
from pathlib import Path
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


settings = Settings()
