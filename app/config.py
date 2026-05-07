from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    private_key: Optional[str] = None
    wallet_address: Optional[str] = None
    funder_address: Optional[str] = None

    poly_api_key: Optional[str] = None
    poly_secret: Optional[str] = None
    poly_passphrase: Optional[str] = None

    owm_api_key: Optional[str] = None

    proxy_url: Optional[str] = None

    mode: Literal["demo", "paper", "live"] = "demo"
    trade_size: float = 5.0
    min_edge: float = 0.15
    scan_interval: int = 180
    daily_loss_limit: float = 50.0
    max_open_positions: int = 30
    bankroll: float = 242.0

    host: str = "0.0.0.0"
    port: int = 8000
    db_url: str = "sqlite+aiosqlite:///./data/dale.db"
    log_level: str = "INFO"

    @property
    def proxies(self) -> Optional[str]:
        return self.proxy_url or None


settings = Settings()
