import requests


VALID_RANGES = {
    "1d", "5d", "1mo", "3mo", "6mo",
    "1y", "2y", "5y", "10y", "ytd", "max"
}

VALID_INTERVALS = {
    "1m", "2m", "5m", "15m", "30m",
    "60m", "90m", "1h", "1d", "5d",
    "1wk", "1mo", "3mo"
}


def fetch_stock_price(
    ticker: str,
    range: str = "1d",
    interval: str = "1m"
) -> dict:
    """
    Fetch stock/ETF market data from Yahoo Finance.

    Args:
        ticker: Stock or ETF symbol, e.g. "AAPL", "QQQ", "NVDA".
        range: Data range, e.g. "1d", "5d", "1mo", "1y", "ytd", "max".
        interval: Data granularity, e.g. "1m", "5m", "1h", "1d", "1wk".

    Returns:
        Dictionary with current market data plus optional OHLCV time-series candles.
    """

    symbol = ticker.strip().upper()
    range = range.strip().lower()
    interval = interval.strip().lower()

    if not symbol:
        return {"success": False, "error": "Ticker symbol is required."}

    if range not in VALID_RANGES:
        return {
            "success": False,
            "symbol": symbol,
            "error": f"Invalid range '{range}'.",
            "valid_ranges": sorted(VALID_RANGES),
        }

    if interval not in VALID_INTERVALS:
        return {
            "success": False,
            "symbol": symbol,
            "error": f"Invalid interval '{interval}'.",
            "valid_intervals": sorted(VALID_INTERVALS),
        }

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    params = {
        "range": range,
        "interval": interval,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code == 404:
            return {
                "success": False,
                "symbol": symbol,
                "error": f"Ticker symbol '{symbol}' was not found.",
            }

        response.raise_for_status()
        data = response.json()

        chart = data.get("chart", {})
        error = chart.get("error")

        if error:
            return {
                "success": False,
                "symbol": symbol,
                "error": error.get("description", "Yahoo Finance returned an error."),
            }

        results = chart.get("result") or []
        if not results:
            return {
                "success": False,
                "symbol": symbol,
                "error": "No market data returned. Symbol may be invalid.",
            }

        result = results[0]
        meta = result.get("meta", {})

        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]

        candles = []
        for i, ts in enumerate(timestamps):
            candles.append({
                "timestamp": ts,
                "open": quote.get("open", [None] * len(timestamps))[i],
                "high": quote.get("high", [None] * len(timestamps))[i],
                "low": quote.get("low", [None] * len(timestamps))[i],
                "close": quote.get("close", [None] * len(timestamps))[i],
                "volume": quote.get("volume", [None] * len(timestamps))[i],
            })

        current_price = meta.get("regularMarketPrice")
        previous_close = meta.get("previousClose")

        change_amount = None
        change_percent = None

        if current_price is not None and previous_close:
            change_amount = current_price - previous_close
            change_percent = (change_amount / previous_close) * 100

        return {
            "success": True,
            "symbol": meta.get("symbol", symbol),
            "price": round(current_price, 2) if current_price is not None else None,
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
            "market_state": meta.get("marketState"),
            "previous_close": round(previous_close, 2) if previous_close is not None else None,
            "change_amount": round(change_amount, 2) if change_amount is not None else None,
            "change_percent": round(change_percent, 2) if change_percent is not None else None,
            "day_high": meta.get("regularMarketDayHigh"),
            "day_low": meta.get("regularMarketDayLow"),
            "volume": meta.get("regularMarketVolume"),
            "timezone": meta.get("exchangeTimezoneName"),
            "requested_range": range,
            "requested_interval": interval,
            "candles": candles,
            "candle_count": len(candles),
            "data_source": "Yahoo Finance chart API",
            "note": "Yahoo may limit valid range/interval combinations. Intraday data is usually limited.",
        }

    except requests.exceptions.Timeout:
        return {"success": False, "symbol": symbol, "error": "Request timed out."}

    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": f"Financial API HTTP error: {e.response.status_code}",
        }

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "symbol": symbol,
            "error": f"Network error: {str(e)}",
        }

    except ValueError:
        return {
            "success": False,
            "symbol": symbol,
            "error": "Invalid JSON response from API.",
        }