"""
Loads configuration from config.yaml, with .env values taking precedence
for anything secret or environment-specific. No hardcoded values anywhere
else in the codebase should be needed -- everything routes through Settings.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_yaml() -> dict:
    with open(_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _env_or(key: str, default):
    val = os.getenv(key)
    if val is None:
        return default
    # best-effort type coercion to match the yaml default's type
    if isinstance(default, bool):
        return val.lower() in ("1", "true", "yes")
    if isinstance(default, int):
        return int(val)
    if isinstance(default, float):
        return float(val)
    return val


@dataclass
class Settings:
    # Sheets
    google_sheet_id: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_ID", ""))
    service_account_path: str = field(
        default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "config/service_account.json")
    )

    # LLM
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "nvidia"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    )
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "meta/llama-3.1-70b-instruct"))

    # Pipeline limits
    max_profiles_per_run: int = field(default_factory=lambda: int(os.getenv("MAX_PROFILES_PER_RUN", 25)))
    min_delay_seconds: int = field(default_factory=lambda: int(os.getenv("MIN_DELAY_SECONDS", 60)))
    max_delay_seconds: int = field(default_factory=lambda: int(os.getenv("MAX_DELAY_SECONDS", 200)))
    note_char_limit: int = field(default_factory=lambda: int(os.getenv("NOTE_CHAR_LIMIT", 200)))
    followup_days: int = field(default_factory=lambda: int(os.getenv("FOLLOWUP_DAYS", 14)))

    # State / logging
    state_db_path: str = field(default_factory=lambda: os.getenv("STATE_DB_PATH", "core/outreach.db"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_path: str = field(default_factory=lambda: os.getenv("LOG_PATH", "logs/outreach.log"))
    screenshot_dir: str = field(
        default_factory=lambda: os.getenv("SCREENSHOT_ON_FAILURE_DIR", "logs/screenshots")
    )

    yaml_config: dict = field(default_factory=_load_yaml)


settings = Settings()
