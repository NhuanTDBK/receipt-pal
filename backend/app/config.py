from pydantic import Field
from pydantic.aliases import AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Telegram
    telegram_bot_token: str

    # Database
    database_url: str  # postgresql+asyncpg://user:pass@host/db

    # OpenAI-compatible LLM provider
    openai_api_key: str = Field(
        validation_alias=AliasChoices("openai_api_key", "gemini_api_key"),
    )
    openai_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        validation_alias=AliasChoices("openai_base_url", "gemini_base_url"),
    )
    model: str = Field(
        default="gemini-2.0-flash-lite",
        validation_alias=AliasChoices("model", "gemini_model"),
    )

    # RocksDB
    rocksdb_path: str = "./data/rocksdb"

    # Conversation
    conversation_timeout_minutes: int = 30

    # Optional Redis for FSM (falls back to MemoryStorage)
    redis_url: str | None = None

    # Langfuse (optional — LLM observability)
    # SDK reads these from env automatically; fields here are for validation only.
    langfuse_secret_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Bot operational settings
    telegram_force_ipv4: bool = True
    telegram_network_retry_attempts: int = 3
    telegram_network_retry_base_delay: float = 1.0
    telegram_polling_restart_delay: float = 3.0

    # Scheduler settings
    enable_scheduler: bool = True
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"
    daily_memory_schedule: str = "02:00"  # HH:MM format
    weekly_memory_schedule: str = "03:00"  # Monday at 3 AM
    monthly_memory_schedule: str = "04:00"  # 1st of month at 4 AM
    weekly_report_schedule: str = "20:00"  # Sunday at 8 PM


settings = Settings()
