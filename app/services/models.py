from sqlalchemy import Column, Integer, String, Float, BigInteger, DateTime, Boolean, Date
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

DB_URL = "sqlite+aiosqlite:///db.sqlite3"
engine = create_async_engine(DB_URL, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase, AsyncAttrs):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    city_name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timezone = Column(Integer, nullable=False)
    time_fajr = Column(DateTime, nullable=True)
    alarm_fajr = Column(Boolean, default=False)
    push_fajr = Column(Boolean, default=False)
    time_sunrise = Column(DateTime, nullable=True)
    alarm_sunrise = Column(Boolean, default=False)
    push_sunrise = Column(Boolean, default=False)
    time_dhuhr = Column(DateTime, nullable=True)
    alarm_dhuhr = Column(Boolean, default=False)
    push_dhuhr = Column(Boolean, default=False)
    time_asr = Column(DateTime, nullable=True)
    alarm_asr = Column(Boolean, default=False)
    push_asr = Column(Boolean, default=False)
    time_maghrib = Column(DateTime, nullable=True)
    alarm_maghrib = Column(Boolean, default=False)
    push_maghrib = Column(Boolean, default=False)
    time_isha = Column(DateTime, nullable=True)
    alarm_isha = Column(Boolean, default=False)
    push_isha = Column(Boolean, default=False)
    date_now = Column(Date, nullable=True)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)