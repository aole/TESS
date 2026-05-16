import requests
import json

def fetch_stock_price(ticker: str) -> dict[str, any]:
    """
    Fetch the current market price and daily statistics for a given stock ticker.

    This tool retrieves real-time (or near real-time) financial data from public 
    market providers. It captures the current price, day high/low, and volume 
    without requiring an authenticated API key.

    IMPORTANT:
    - NO API KEY REQUIRED: Uses public finance query endpoints.
    - TICKER FORMAT: Use standard market symbols (e.g., "AAPL", "SPY", "TSLA").
    - NETWORK HEADERS: Requires specific browser emulation to bypass bot detection 
      on financial servers.
    - MARKET HOURS: Prices may be delayed or represent "Post-Market" values 
      depending on the time of execution.

    Args:
        ticker (str): The stock or ETF symbol to look up (e.g., "NVDA", "QQQ").

    Returns:
        dict[str, any]: A dictionary containing:
            - symbol: The ticker symbol searched.
            - price: Current market price.
            - change: Percent change from previous close.
            - day_range: High and low for the current session.
            - currency: The currency the stock is traded in (e.g., USD).
    """
    # Yahoo Finance V8 endpoint is generally the most stable without a key
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    try:
        # Step 1: Request market data
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 404:
            return {"error": f"Ticker symbol '{ticker}' not found."}
        
        response.raise_for_status()
        data = response.json()

        # Step 2: Extract relevant fields from the nested JSON structure
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        
        if not meta:
            return {"error": "Could not parse market data. Symbol may be invalid."}

        current_price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose")
        
        # Calculate percentage change
        change_pct = 0
        if current_price and prev_close:
            change_pct = ((current_price - prev_close) / prev_close) * 100

        return {
            "symbol": ticker.upper(),
            "price": round(current_price, 2) if current_price else None,
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
            "change_percent": f"{change_pct:+.2f}%",
            "day_high": meta.get("regularMarketDayHigh"),
            "day_low": meta.get("regularMarketDayLow"),
            "market_state": "Open" if meta.get("marketState") == "REGULAR" else "Closed/Post-Market"
        }

    except requests.exceptions.HTTPError as e:
        return {"error": f"Financial API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Unexpected error retrieving stock data: {str(e)}"}