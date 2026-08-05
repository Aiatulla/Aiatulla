from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.llm.cassette import CassetteMode


class Settings(BaseSettings):
    """Application settings, read from environment variables or a local .env file.

    Every value here has a development default so a fresh clone runs without setup.
    Production overrides them through real environment variables.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "repo-radar"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+asyncpg://repo_radar:local_dev_only@localhost:5433/repo_radar"
    DEBUG: bool = False

    # Model access. The key is optional because the default mode replays cassettes
    # and needs no credentials, which is what lets a fresh clone run the suite
    # offline and for free. Recording is the only path that requires a real key.
    LLM_MODEL: str = "gemini-2.0-flash"
    GEMINI_API_KEY: str | None = None
    LLM_CASSETTE_DIR: Path = Path(__file__).resolve().parent.parent / "tests" / "cassettes"
    LLM_CASSETTE_MODE: CassetteMode = CassetteMode.REPLAY
    # 3000 is the Next.js dev server default, 8080 covers a static or containerised
    # frontend. Production must override this: a wildcard here would let any site
    # call the API with the visitor's credentials attached.
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]


settings = Settings()
