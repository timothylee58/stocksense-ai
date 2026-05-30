from fastapi import APIRouter, HTTPException
from app.db.models import TickerModel, WatchlistItemModel

router = APIRouter()
DEFAULT_USER = "default"


@router.get("/watchlist")
def get_watchlist():
    items = (
        WatchlistItemModel
        .select(WatchlistItemModel, TickerModel)
        .join(TickerModel)
        .where(WatchlistItemModel.user_id == DEFAULT_USER)
        .order_by(WatchlistItemModel.added_at.desc())
    )
    return {"watchlist": [item.ticker.symbol for item in items]}


@router.post("/watchlist/{ticker}")
def add_to_watchlist(ticker: str):
    ticker = ticker.upper()
    ticker_row, _ = TickerModel.get_or_create(symbol=ticker)
    _, created = WatchlistItemModel.get_or_create(
        user_id=DEFAULT_USER, ticker=ticker_row
    )
    return {"added": created, "ticker": ticker}


@router.delete("/watchlist/{ticker}")
def remove_from_watchlist(ticker: str):
    ticker = ticker.upper()
    try:
        ticker_row = TickerModel.get(TickerModel.symbol == ticker)
        deleted = (
            WatchlistItemModel
            .delete()
            .where(
                WatchlistItemModel.user_id == DEFAULT_USER,
                WatchlistItemModel.ticker == ticker_row,
            )
            .execute()
        )
        return {"removed": deleted > 0, "ticker": ticker}
    except TickerModel.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist")
