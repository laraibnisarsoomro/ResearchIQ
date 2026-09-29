from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column
from backend.db.database import Base


class CompanyCache(Base):
    __tablename__ = "company_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    data_type: Mapped[str] = mapped_column(String(50))  # info|financials|balance_sheet|cashflow|news
    data_json: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class UniverseEntry(Base):
    __tablename__ = "universe"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(100))
    sub_industry: Mapped[str] = mapped_column(String(200), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SectorStatsCache(Base):
    __tablename__ = "sector_stats_cache"

    sector: Mapped[str] = mapped_column(String(100), primary_key=True)
    stats_json: Mapped[str] = mapped_column(Text)
    peer_count: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CompanyRatiosCache(Base):
    __tablename__ = "company_ratios_cache"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    sector: Mapped[str] = mapped_column(String(100))
    ratios_json: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    market_cap: Mapped[float] = mapped_column(Float, default=0.0)
