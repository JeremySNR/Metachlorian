"""Offline reverse geocoding: GPS → nearest populated place (GeoNames
cities with population ≥ 1000, CC BY 4.0, bundled). Deterministic, no network."""
from __future__ import annotations

import csv
import gzip
import io
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA = Path(__file__).parent / "data" / "geonames_cities1000.csv.gz"
COUNTRY = {"PT": "Portugal", "ES": "Spain", "FR": "France", "GB": "United Kingdom", "US": "United States", "DE": "Germany", "IT": "Italy",
           "NL": "Netherlands", "IE": "Ireland", "BE": "Belgium", "CH": "Switzerland", "AT": "Austria", "JP": "Japan", "AU": "Australia",
           "NZ": "New Zealand", "CA": "Canada", "MX": "Mexico", "BR": "Brazil", "ZA": "South Africa", "TH": "Thailand", "GR": "Greece",
           "TR": "Turkey", "MA": "Morocco", "AE": "United Arab Emirates", "IN": "India", "CN": "China", "SG": "Singapore", "NO": "Norway",
           "SE": "Sweden", "DK": "Denmark", "FI": "Finland", "IS": "Iceland", "PL": "Poland", "CZ": "Czechia", "HR": "Croatia"}


@lru_cache(maxsize=1)
def _table():
    with gzip.open(DATA, "rt", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    lat = np.radians(np.array([float(r["lat"]) for r in rows]))
    lon = np.radians(np.array([float(r["lon"]) for r in rows]))
    xyz = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], 1).astype(np.float32)
    return rows, xyz


def reverse(lat: float, lon: float) -> dict | None:
    """Nearest place and its distance in km (None for (0, 0) and missing data)."""
    if lat is None or lon is None or (abs(lat) < 1e-6 and abs(lon) < 1e-6) or not DATA.exists():
        return None
    rows, xyz = _table()
    la, lo = math.radians(lat), math.radians(lon)
    q = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)], np.float32)
    i = int(np.argmax(xyz @ q))
    cosang = float(np.clip(xyz[i] @ q, -1, 1))
    km = math.acos(cosang) * 6371.0
    r = rows[i]
    return {"city": r["name"], "region": r["admin1"], "district": r["admin2"], "country_code": r["cc"],
            "country": COUNTRY.get(r["cc"], r["cc"]), "distance_km": round(km, 1)}


_ = io
