import requests

def get_current_location() -> dict[str, any]:
    """
    Retrieves the system's geographical location using freeipapi.com.
    This service supports HTTPS for free and requires no API key.
    
    Returns:
        dict[str, any]: City, region, country, and coordinates.
    """
    # freeipapi.com is SSL-enabled and very reliable for free tier use
    url = "https://freeipapi.com/api/json"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 429:
            return {"error": "Rate limit exceeded. Please wait before retrying."}
            
        response.raise_for_status()
        data = response.json()

        # freeipapi uses slightly different keys (e.g., cityName instead of city)
        return {
            "city": data.get("cityName"),
            "region": data.get("regionName"),
            "country": data.get("countryName"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "zip": data.get("zipCode"),
            "ip": data.get("ipAddress")
        }

    except Exception as e:
        return {"error": f"Location detection failed: {str(e)}"}
