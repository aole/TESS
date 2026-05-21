import requests
from datetime import datetime

def fetch_stock_price(ticker: str) -> dict:
    symbol = ticker.strip().upper()
    if not symbol:
        return {"error": "Ticker symbol is required."}

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    
    # 1d range with 1h interval retrieves very few data points (approx. 7 per trading day)
    params = {
        "range": "1d",
        "interval": "1h",
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = data.get("chart", {}).get("result")
        if not results:
            return {"error": f"No data found for {symbol}."}

        result = results[0]
        timestamps = result.get("timestamp", [])
        quote = result.get("indicators", {}).get("quote", [{}])[0]

        candles = []
        for i, ts in enumerate(timestamps):
            # Format timestamp into a readable Date/Time string
            dt_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            
            # Format prices to 2 decimal places if they exist
            o = quote.get("open", [])[i]
            h = quote.get("high", [])[i]
            l = quote.get("low", [])[i]
            c = quote.get("close", [])[i]

            candles.append({
                "datetime": dt_str,
                "open": round(o, 2) if o is not None else None,
                "high": round(h, 2) if h is not None else None,
                "low": round(l, 2) if l is not None else None,
                "close": round(c, 2) if c is not None else None,
            })

        return {
            "ticker": symbol,
            "data": candles
        }

    except Exception as e:
        return {"error": f"Failed to fetch data: {str(e)}"}