"""Central pydantic Settings for process entry points.

Loads ``local/.env`` (then transitional repo-root ``.env``) into the process
environment via :func:`get_settings`. Providers / execution continue to read
``os.environ`` only; they must not import this module.

``liveTradingEnabled`` is intentionally **not** a Settings field — it stays a
hard-coded ``False`` in the execution profile (SIMULATE red line).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .dotenv import load_dotenv


class Settings(BaseSettings):
    """Runtime knobs read from env / ``local/.env``. Missing file is fine."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    stock_platform_db_url: str = Field(
        default="sqlite:///./local/stock_platform.db",
        alias="STOCK_PLATFORM_DB_URL",
    )
    stock_platform_performance_log: str = Field(
        default="./local/recommend_decisions.jsonl",
        alias="STOCK_PLATFORM_PERFORMANCE_LOG",
    )
    stock_platform_performance_proxy_log: str = Field(
        default="./local/performance_proxy.jsonl",
        alias="STOCK_PLATFORM_PERFORMANCE_PROXY_LOG",
    )
    stock_platform_holdings_path: str = Field(
        default="./local/holdings.json",
        alias="STOCK_PLATFORM_HOLDINGS_PATH",
    )
    stock_platform_loop_health_dir: str = Field(
        default="./local/health",
        alias="STOCK_PLATFORM_LOOP_HEALTH_DIR",
    )
    stock_platform_ops_ledger_dir: str = Field(
        default="./local/logs",
        alias="STOCK_PLATFORM_OPS_LEDGER_DIR",
    )
    stock_platform_broker: str = Field(default="paper", alias="STOCK_PLATFORM_BROKER")
    stock_platform_provider_preset: str | None = Field(
        default=None, alias="STOCK_PLATFORM_PROVIDER_PRESET"
    )
    stock_platform_engine_market_db: str | None = Field(
        default=None, alias="STOCK_PLATFORM_ENGINE_MARKET_DB"
    )
    stock_platform_tushare_token: str | None = Field(
        default=None, alias="STOCK_PLATFORM_TUSHARE_TOKEN"
    )


@lru_cache(maxsize=1)
def get_settings(*, force_reload: bool = False) -> Settings:
    """Load dotenv once, then build Settings from the (possibly updated) env.

    Call this at every process entry (CLI / workbench) before reading env.
    """
    if force_reload:
        get_settings.cache_clear()
    load_dotenv()
    return Settings()


def settings_as_env_defaults(settings: Settings | None = None) -> dict[str, str]:
    """Flatten Settings into a plain ``KEY=value`` map for diagnostics."""
    s = settings or get_settings()
    out: dict[str, str] = {}
    data: dict[str, Any] = s.model_dump(by_alias=True)
    for key, value in data.items():
        if value is None:
            continue
        out[str(key)] = str(value)
    return out


__all__ = ["Settings", "get_settings", "settings_as_env_defaults"]
