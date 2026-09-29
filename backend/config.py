from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    price_cache_ttl: int = 3600
    info_cache_ttl: int = 86400
    financials_cache_ttl: int = 604800
    news_cache_ttl: int = 14400
    price_history_cache_ttl: int = 1800
    sector_stats_ttl: int = 86400
    max_sector_peers: int = 40
    data_dir: str = "data"
    llm_model: str = "claude-sonnet-4-6"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def data_path(self) -> Path:
        base = Path(__file__).parent.parent
        p = base / self.data_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> str:
        return str(self.data_path / "equity_research.db")

    @property
    def has_llm(self) -> bool:
        key = self.anthropic_api_key
        return bool(
            key
            and key.startswith("sk-ant")
            and len(key) > 20
            and "..." not in key
        )


settings = Settings()
