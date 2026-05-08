from __future__ import annotations
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional
from ..config import settings
from ..proxy import make_client

logger = logging.getLogger(__name__)


@dataclass
class CityCoord:
    name: str
    lat: float
    lon: float


DEFAULT_CITIES: list[CityCoord] = [
    CityCoord("Wellington",    -41.2865,  174.7762),
    CityCoord("Hong Kong",      22.3193,  114.1694),
    CityCoord("Toronto",        43.6532,  -79.3832),
    CityCoord("Singapore",       1.3521,  103.8198),
    CityCoord("Madrid",         40.4168,   -3.7038),
    CityCoord("Tokyo",          35.6762,  139.6503),
    CityCoord("Los Angeles",    34.0522, -118.2437),
    CityCoord("Mexico City",    19.4326,  -99.1332),
    CityCoord("Beijing",        39.9042,  116.4074),
    CityCoord("Chengdu",        30.5728,  104.0668),
    CityCoord("Shanghai",       31.2304,  121.4737),
    CityCoord("Mumbai",         19.0760,   72.8777),
    CityCoord("Seattle",        47.6062, -122.3321),
    CityCoord("Seoul",          37.5665,  126.9780),
    CityCoord("Munich",         48.1351,   11.5820),
    CityCoord("London",         51.5074,   -0.1278),
    CityCoord("Amsterdam",      52.3676,    4.9041),
    CityCoord("Jakarta",        -6.2088,  106.8456),
    CityCoord("Houston",        29.7604,  -95.3698),
    CityCoord("Dallas",         32.7767,  -96.7970),
    CityCoord("Chicago",        41.8781,  -87.6298),
    CityCoord("San Francisco",  37.7749, -122.4194),
    CityCoord("Atlanta",        33.7490,  -84.3880),
    CityCoord("Paris",          48.8566,    2.3522),
    CityCoord("Ankara",         39.9334,   32.8597),
    CityCoord("Warsaw",         52.2297,   21.0122),
    CityCoord("Milan",          45.4642,    9.1900),
    CityCoord("Istanbul",       41.0082,   28.9784),
    CityCoord("Sao Paulo",     -23.5505,  -46.6333),
    CityCoord("Manila",         14.5995,  120.9842),
    CityCoord("Denver",         39.7392, -104.9903),
    CityCoord("Phoenix",        33.4484, -112.0740),
    CityCoord("Miami",          25.7617,  -80.1918),
    CityCoord("New York",       40.7128,  -74.0060),
    CityCoord("Boston",         42.3601,  -71.0589),
    CityCoord("Buenos Aires",  -34.6037,  -58.3816),
    CityCoord("Santiago",      -33.4489,  -70.6693),
    CityCoord("Bogota",          4.7110,  -74.0721),
    CityCoord("Lima",          -12.0464,  -77.0428),
    CityCoord("Cairo",          30.0444,   31.2357),
    CityCoord("Nairobi",        -1.2921,   36.8219),
    CityCoord("Lagos",           6.5244,    3.3792),
    CityCoord("Cape Town",     -33.9249,   18.4241),
    CityCoord("Johannesburg",  -26.2041,   28.0473),
    CityCoord("Dubai",          25.2048,   55.2708),
    CityCoord("Riyadh",         24.7136,   46.6753),
    CityCoord("Karachi",        24.8607,   67.0011),
    CityCoord("Bangkok",        13.7563,  100.5018),
    CityCoord("Kuala Lumpur",    3.1390,  101.6869),
    CityCoord("Sydney",        -33.8688,  151.2093),
    CityCoord("Melbourne",     -37.8136,  144.9631),
    CityCoord("Auckland",      -36.8485,  174.7633),
    CityCoord("Delhi",          28.7041,   77.1025),
    CityCoord("Kolkata",        22.5726,   88.3639),
    CityCoord("Dhaka",          23.8103,   90.4125),
    CityCoord("Taipei",         25.0330,  121.5654),
    CityCoord("Osaka",          34.6937,  135.5023),
    CityCoord("Wuhan",          30.5928,  114.3055),
    CityCoord("Chongqing",      29.4316,  106.9123),
    CityCoord("Rome",           41.9028,   12.4964),
    CityCoord("Barcelona",      41.3851,    2.1734),
    CityCoord("Berlin",         52.5200,   13.4050),
    CityCoord("Vienna",         48.2082,   16.3738),
    CityCoord("Lisbon",         38.7223,   -9.1393),
    CityCoord("Athens",         37.9838,   23.7275),
    CityCoord("Moscow",         55.7558,   37.6176),
    CityCoord("Casablanca",     33.5731,   -7.5898),
    CityCoord("Hanoi",          21.0278,  105.8342),
    CityCoord("Ho Chi Minh",    10.8231,  106.6297),
    CityCoord("Austin",         30.2672,  -97.7431),
    CityCoord("Tel Aviv",       32.0853,   34.7818),
    CityCoord("Jeddah",         21.5433,   39.1728),
    CityCoord("Lucknow",        26.8467,   80.9462),
    CityCoord("Guangzhou",      23.1291,  113.2644),
    CityCoord("Shenzhen",       22.5431,  114.0579),
    CityCoord("Qingdao",        36.0671,  120.3826),
    CityCoord("Panama City",     8.9936,  -79.5197),
    CityCoord("Busan",          35.1796,  129.0756),
    CityCoord("Helsinki",       60.1699,   24.9384),
]

# Deduplica por nome
_seen: set[str] = set()
_deduped: list[CityCoord] = []
for _c in DEFAULT_CITIES:
    if _c.name not in _seen:
        _seen.add(_c.name)
        _deduped.append(_c)
DEFAULT_CITIES = _deduped


@dataclass
class Forecast:
    city: str
    target_at: dt.datetime
    mu_c: float
    sigma_c: float
    source: str = "ensemble"
    raw: Optional[dict] = None


def _horizon_sigma(hours: float) -> float:
    """Sigma calibrado por horizonte de previsao."""
    if hours <= 6:   return 0.8
    if hours <= 12:  return 1.1
    if hours <= 24:  return 1.5
    if hours <= 48:  return 2.1
    if hours <= 72:  return 2.7
    if hours <= 96:  return 3.3
    return 4.0


async def _owm_max(city: CityCoord, target_date: dt.date) -> Optional[float]:
    """Temperatura MAXIMA diaria do OpenWeatherMap."""
    if not settings.owm_api_key:
        return None
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": city.lat, "lon": city.lon,
              "appid": settings.owm_api_key, "units": "metric", "cnt": 40}
    try:
        async with make_client() as cx:
            r = await cx.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("OWM error %s: %s", city.name, e)
        return None

    date_str = target_date.strftime("%Y-%m-%d")
    day_temps = [float(it["main"]["temp_max"])
                 for it in data.get("list", [])
                 if it.get("dt_txt", "")[:10] == date_str]
    return max(day_temps) if day_temps else None


async def _openmeteo_max(city: CityCoord, target_date: dt.date) -> Optional[float]:
    """Temperatura maxima diaria do Open-Meteo (gratis, sem chave)."""
    url = "https://api.open-meteo.com/v1/forecast"
    date_str = target_date.strftime("%Y-%m-%d")
    params = {"latitude": city.lat, "longitude": city.lon,
              "daily": "temperature_2m_max", "timezone": "UTC",
              "start_date": date_str, "end_date": date_str}
    try:
        async with make_client(timeout=10) as cx:
            r = await cx.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.debug("Open-Meteo error %s: %s", city.name, e)
        return None

    temps = data.get("daily", {}).get("temperature_2m_max", [])
    return float(temps[0]) if temps and temps[0] is not None else None


async def fetch_forecast(city: CityCoord, target_at: dt.datetime) -> Optional[Forecast]:
    """
    Ensemble OWM + Open-Meteo usando temperatura maxima diaria.
    Quando as fontes divergem alargamos o sigma em vez de descartar — assim
    nao perdemos oportunidades em horizontes longos onde elas naturalmente discordam.
    """
    target_date = target_at.date() if hasattr(target_at, 'date') else target_at
    if hasattr(target_date, 'date'):
        target_date = target_date.date()

    horizon_h = max(1.0, (
        dt.datetime.combine(target_date, dt.time(12), tzinfo=dt.timezone.utc)
        - dt.datetime.now(dt.timezone.utc)
    ).total_seconds() / 3600)
    base_sigma = _horizon_sigma(horizon_h)

    owm  = await _owm_max(city, target_date)
    omeo = await _openmeteo_max(city, target_date)

    if owm is None and omeo is None:
        return None

    if owm is None:
        return Forecast(city=city.name,
                        target_at=dt.datetime.combine(target_date, dt.time(12), tzinfo=dt.timezone.utc),
                        mu_c=round(omeo, 1), sigma_c=base_sigma, source="open-meteo")
    if omeo is None:
        return Forecast(city=city.name,
                        target_at=dt.datetime.combine(target_date, dt.time(12), tzinfo=dt.timezone.utc),
                        mu_c=round(owm, 1), sigma_c=base_sigma, source="owm")

    delta = abs(owm - omeo)
    mu    = (owm + omeo) / 2.0
    if delta <= 1.0:
        sigma = round(base_sigma * 0.75, 2)
    elif delta <= 2.5:
        sigma = round(base_sigma, 2)
    else:
        sigma = round((base_sigma ** 2 + (delta / 2.0) ** 2) ** 0.5, 2)
        logger.debug("Ensemble divergente %s: OWM=%.1f OMeo=%.1f d=%.1f sigma=%.1f",
                     city.name, owm, omeo, delta, sigma)

    return Forecast(
        city=city.name,
        target_at=dt.datetime.combine(target_date, dt.time(12), tzinfo=dt.timezone.utc),
        mu_c=round(mu, 1), sigma_c=sigma,
        source=f"ensemble(owm={owm:.1f},omeo={omeo:.1f},d={delta:.1f})",
    )
