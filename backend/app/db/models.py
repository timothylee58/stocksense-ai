import os
import datetime
from peewee import (
    SqliteDatabase, PostgresqlDatabase,
    Model, CharField, FloatField, DateTimeField,
    ForeignKeyField, IntegerField, AutoField
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stocksense.db")

def _init_db():
    if DATABASE_URL.startswith("postgres"):
        # postgres://user:pass@host:port/dbname
        url = DATABASE_URL.replace("postgres://", "").replace("postgresql://", "")
        user_pass, rest = url.split("@", 1)
        host_port, dbname = rest.rsplit("/", 1)
        user, password = user_pass.split(":", 1)
        host, port = (host_port.split(":", 1) + ["5432"])[:2]
        return PostgresqlDatabase(dbname, user=user, password=password, host=host, port=int(port))
    # Default: SQLite
    path = DATABASE_URL.replace("sqlite:///", "")
    return SqliteDatabase(path, pragmas={"journal_mode": "wal", "foreign_keys": 1})

db = _init_db()


class BaseModel(Model):
    class Meta:
        database = db


class TickerModel(BaseModel):
    class Meta:
        table_name = "tickers"

    id = AutoField()
    symbol = CharField(unique=True, max_length=10)
    name = CharField(null=True)
    sector = CharField(null=True)
    created_at = DateTimeField(default=datetime.datetime.utcnow)


class PredictionModel(BaseModel):
    class Meta:
        table_name = "predictions"

    id = AutoField()
    ticker = ForeignKeyField(TickerModel, backref="predictions", on_delete="CASCADE")
    timestamp = DateTimeField(default=datetime.datetime.utcnow)
    signal = CharField(max_length=10)       # BUY / SELL / HOLD
    confidence = FloatField()
    current_price = FloatField()
    forecast_price = FloatField()
    sentiment_score = FloatField(default=0.5)
    model_version = CharField(default="lstm_v1")


class WatchlistItemModel(BaseModel):
    class Meta:
        table_name = "watchlist_items"
        indexes = ((("user_id", "ticker"), True),)  # unique together

    id = AutoField()
    user_id = CharField(default="default", max_length=64)
    ticker = ForeignKeyField(TickerModel, backref="watchlist_items", on_delete="CASCADE")
    added_at = DateTimeField(default=datetime.datetime.utcnow)


def init_tables():
    """Create tables if they don't exist."""
    with db:
        db.create_tables([TickerModel, PredictionModel, WatchlistItemModel], safe=True)
