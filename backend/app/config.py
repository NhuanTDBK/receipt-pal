from pydantic import Field
from pydantic.aliases import AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str

    # Database
    database_url: str  # postgresql+asyncpg://user:pass@host/db

    # Gemini / OpenAI-compatible — accepts GEMINI_MODEL or MODEL env var
    gemini_api_key: str
    gemini_model: str = Field(
        default="gemini-2.0-flash-lite",
        validation_alias=AliasChoices("gemini_model", "model"),
    )
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # RocksDB
    rocksdb_path: str = "./data/rocksdb"

    # Conversation
    conversation_timeout_minutes: int = 30

    # Optional Redis for FSM (falls back to MemoryStorage)
    redis_url: str | None = None

    # Bot operational settings
    telegram_force_ipv4: bool = True
    telegram_network_retry_attempts: int = 3
    telegram_network_retry_base_delay: float = 1.0
    telegram_polling_restart_delay: float = 3.0


settings = Settings()
