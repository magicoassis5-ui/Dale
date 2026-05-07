from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from ..config import settings
from ..proxy import make_client

logger = logging.getLogger(__name__)


@dataclass
class CityCoord:
    name: str
    lat: float
    lon: float


# Default cities matching the print (20). Lat/lon hardcoded to avoid extra API calls.
DEFAULT_CITIES: list[CityCoord] = [
    CityCoord("Wellington", -41.2865, 174.7762),
    CityCoord("Hong Kong", 22.3193, 114.1694),
    CityCoord("Toronto", 43.6532, -79.3832),
    CityCoord("Singapore", 1.3521, 103.8198),
    CityCoord("Madrid", 40.4168, -3.7038),
    CityCoord("Tokyo", 35.6762, 139.6503),
    CityCoord("Los Angeles", 34.0522, -118.2437),
    CityCoord("Mexico City", 19.4326, -99.1332),
    CityCoord("Wellington-NZ", -41.2865, 174.7762),
    CityCoord("Beijing", 39.9042, 116.4074),
    CityCoord("Chengdu", 30.5728, 104.0668),
    CityCoord("Shanghai", 31.2304, 121.4737),
    CityCoord("Toronto2", 43.7, -79.4),
    CityCoord("Mumbai", 19.0760, 72.8777),
    CityCoord("Seattle", 47.6062, -122.3321),
    CityCoord("Madrid2", 40.4, -3.7),
    CityCoord("Seoul", 37.5665, 126.9780),
    CityCoord("Munich", 48.1351, 11.5820),
    CityCoord("London", 51.5074, -0.1278),
    CityCoord("Amsterdam", 52.3676, 4.9041),
    CityCoord("Jakarta", -6.2088, 106.8456),
]


@dataclass
class Forecast:
    city: str
    target_at: dt.datetime
    mu_c: float
    sigma_c: float
    raw: Optional[dict] = None


# Empirical sigma in °C for a forecast horizon (hours). Calibrated from typical OWM error.
def horizon_sigma(hours: float) -> float:
    if hours <= 6:
        return 1.0
    if hours <= 24:
        return 1.6
    if hours <= 48:
        return 2.4
    if hours <= 96:
        return 3.5
    return 4.5


async def fetch_forecast(city: CityCoord, target_at: dt.datetime) -> Optional[Forecast]:
    """Get OWM forecast nearest target_at. Returns Forecast or None on error."""
    if not settings.owm_api_key:
        return None
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": city.lat,
        "lon": city.lon,
        "appid": settings.owm_api_key,
        "units": "metric",
    }
    try:
        async with make_client() as cx:
            r = await cx.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("OWM error for %s: %s", city.name, e)
        return None

    items = data.get("list", [])
    if not items:
        return None
    target_ts = target_at.timestamp()
    nearest = min(items, key=lambda it: abs(it["dt"] - target_ts))
    mu = float(nearest["main"]["temp"])
    horizon = max(0.5, (nearest["dt"] - dt.datetime.now(dt.timezone.utc).timestamp()) / 3600.0)
    return Forecast(
        city=city.name,
        target_at=dt.datetime.fromtimestamp(nearest["dt"], tz=dt.timezone.utc),
        mu_c=mu,
        sigma_c=horizon_sigma(horizon),
        raw=nearest,
    )
