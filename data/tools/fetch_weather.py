import requests
import json

def fetch_weather(location: str) -> dict[str, any]:
    """Fetch current weather and a 24-hour forecast for a specific location.

    This tool utilizes a two-step process: first, it geocodes the location string into 
    latitude and longitude coordinates, then it retrieves localized weather data.

    IMPORTANT:
    - Uses Open-Meteo and OpenStreetMap/Geocode.maps.co.
    - AUTOMATED FALLBACK: If the primary geocoding service is busy, it automatically tries a secondary provider.
    - UNIT SYSTEM: Standardized to Imperial (Fahrenheit for temperature, MPH for wind, and Inches for precipitation).
    - RATE LIMITING: Uses specific browser headers to ensure reliable responses from geocoding services.

    Args:
        location (str): City name, full address, or landmark (e.g., "Fishers, IN" or "Paris, France").

    Returns:
        dict[str, any]: A structured dictionary containing:
            - location: The full resolved name of the address found.
            - current: Dictionary of current temp, humidity, wind, and conditions.
            - forecast: A list of objects for the next 24 hourly intervals.
    """
    weather_url = "https://api.open-meteo.com/v1/forecast"

    # WMO Weather interpretation codes
    wmo_description = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 
        53: "Moderate drizzle", 55: "Dense drizzle", 61: "Slight rain", 
        63: "Moderate rain", 65: "Heavy rain", 71: "Slight snow", 
        73: "Moderate snow", 75: "Heavy snow", 95: "Thunderstorm"
    }

    # Browser-like headers to avoid being blocked by geocoding services
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    lat, lon, display_name = None, None, None

    # --- Step 1: Geocoding with Fallback ---
    # Nominatim (Primary) and Geocode.maps.co (Secondary)
    for provider in ["https://nominatim.openstreetmap.org/search", "https://geocode.maps.co/search"]:
        try:
            params = {"q": location, "format": "json", "limit": 1}
            res = requests.get(provider, params=params, headers=headers, timeout=5)
            if res.status_code == 200 and (data := res.json()):
                lat, lon = data[0]["lat"], data[0]["lon"]
                display_name = data[0]["display_name"]
                break
        except Exception:
            continue 

    if not lat or not lon:
        return {"error": f"Location '{location}' not found."}

    # --- Step 2: Fetch Weather Data ---
    try:
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "hourly": "temperature_2m,precipitation_probability",
            "temperature_unit": "fahrenheit",  # Fixed string for Fahrenheit
            "wind_speed_unit": "mph",         # Updated to miles per hour
            "precipitation_unit": "inch",      # Updated to inches
            "timezone": "auto",
            "forecast_days": 1
        }
        
        response = requests.get(weather_url, params=weather_params, timeout=10)
        response.raise_for_status()
        raw = response.json()
        curr = raw["current"]

        return {
            "location": display_name,
            "current": {
                "temp": curr["temperature_2m"],
                "feels_like": curr["apparent_temperature"],
                "humidity": curr["relative_humidity_2m"],
                "wind_speed": curr["wind_speed_10m"],
                "condition": wmo_description.get(curr["weather_code"], "Unknown"),
                "time": curr["time"]
            },
            "forecast": [
                {
                    "time": raw["hourly"]["time"][i],
                    "temp": raw["hourly"]["temperature_2m"][i],
                    "precip_prob": raw["hourly"]["precipitation_probability"][i]
                }
                for i in range(len(raw["hourly"]["time"]))
            ]
        }

    except requests.exceptions.HTTPError as e:
        return {"error": f"Weather API error: {e.response.text}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}