from typing import Literal
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── LLM Provider ───────────────────────────────────────────────────────────
    # Currently strictly using OpenAI as requested
    llm_provider: Literal["openai"] = Field(
        default="openai", validation_alias="LLM_PROVIDER"
    )

    # OpenAI settings
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL"
    )

    # ── Models ─────────────────────────────────────────────────────────────────
    model_strong: str = Field(default="gpt-4o", validation_alias="MODEL_STRONG")
    model_fast: str = Field(default="gpt-4o-mini", validation_alias="MODEL_FAST")

    # ── Engine ─────────────────────────────────────────────────────────────────
    max_iterations: int = Field(default=5, validation_alias="MAX_ITERATIONS")
    accuracy_threshold: float = Field(default=0.75, validation_alias="ACCURACY_THRESHOLD")

    weight_normal: float = Field(default=0.50, validation_alias="WEIGHT_NORMAL")
    weight_edge: float = Field(default=0.30, validation_alias="WEIGHT_EDGE")
    weight_adversarial: float = Field(default=0.20, validation_alias="WEIGHT_ADVERSARIAL")

    # ── Sandbox ────────────────────────────────────────────────────────────────
    sandbox_timeout_seconds: int = Field(default=30, validation_alias="SANDBOX_TIMEOUT")
    sandbox_max_memory_mb: int = Field(default=256, validation_alias="SANDBOX_MAX_MEMORY_MB")

    # ── Memory ─────────────────────────────────────────────────────────────────
    memory_store_path: str = Field(default="./memory_store.json", validation_alias="MEMORY_STORE_PATH")
    max_memory_patterns: int = Field(default=100, validation_alias="MAX_MEMORY_PATTERNS")

    # ── API Server ─────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    api_reload: bool = Field(default=False, validation_alias="API_RELOAD")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "protected_namespaces": (),
    }


settings = Settings()
