"""
infrastructure/config.py
Single source of truth for all environment variables and constants.
No business logic — pure configuration.
"""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TelegramConfig:
    token: str = ""
    allowed_chat_id: int = 0
    n8n_webhook_secret: str = ""

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        return cls(
            token=os.environ["TELEGRAM_TOKEN"],
            allowed_chat_id=int(os.environ["ALLOWED_CHAT_ID"]),
            n8n_webhook_secret=os.environ.get("N8N_WEBHOOK_SECRET", ""),
        )


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str = ""
    model: str = "gemini-3.1-pro-preview"

    @classmethod
    def from_env(cls) -> "GeminiConfig":
        return cls(
            api_key=os.environ["GEMINI_API_KEY"],
            model=os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview"),
        )


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str = ""
    endpoint: str = "https://api.deepseek.com/v1/chat/completions"
    model: str = "deepseek-chat"

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        return cls(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            endpoint=os.environ.get(
                "DEEPSEEK_ENDPOINT",
                "https://api.deepseek.com/v1/chat/completions",
            ),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )


@dataclass(frozen=True)
class MapsConfig:
    api_key: str = ""
    ubaya_lat: float = -7.3275
    ubaya_lng: float = 112.7858

    @classmethod
    def from_env(cls) -> "MapsConfig":
        return cls(
            api_key=os.environ["MAPS_API_KEY"],
            ubaya_lat=float(os.environ.get("UBAYA_LAT", "-7.3275")),
            ubaya_lng=float(os.environ.get("UBAYA_LNG", "112.7858")),
        )


@dataclass(frozen=True)
class FirestoreConfig:
    project: str = "kos-monitor"
    database_id: str = "kos-monitor-firestore"

    @classmethod
    def from_env(cls) -> "FirestoreConfig":
        return cls(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", "kos-monitor"),
            database_id=os.environ.get("FIRESTORE_DATABASE_ID", "kos-monitor-firestore"),
        )


@dataclass(frozen=True)
class MonitorConfig:
    """Filter thresholds for the n8n scraper monitor."""
    price_min: int = 300_000
    price_max: int = 800_000
    allowed_cities: tuple[str, ...] = ("surabaya", "sidoarjo")

    @classmethod
    def from_env(cls) -> "MonitorConfig":
        return cls(
            price_min=int(os.environ.get("MONITOR_PRICE_MIN", "300000")),
            price_max=int(os.environ.get("MONITOR_PRICE_MAX", "800000")),
            allowed_cities=tuple(
                c.strip().lower()
                for c in os.environ.get("MONITOR_CITIES", "surabaya,sidoarjo").split(",")
            ),
        )


@dataclass(frozen=True)
class AppConfig:
    """Top-level composition of all config sections."""
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)
    maps: MapsConfig = field(default_factory=MapsConfig)
    firestore: FirestoreConfig = field(default_factory=FirestoreConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            telegram=TelegramConfig.from_env(),
            gemini=GeminiConfig.from_env(),
            deepseek=DeepSeekConfig.from_env(),
            maps=MapsConfig.from_env(),
            firestore=FirestoreConfig.from_env(),
            monitor=MonitorConfig.from_env(),
        )
