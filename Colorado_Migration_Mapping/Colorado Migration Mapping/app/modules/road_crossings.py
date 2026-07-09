"""
road_crossings.py

Detect whether animal movement tracks cross roads or highways
using TIGER Census road shapefiles from MigrationAnalyzer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

# The merged roads layer, in preference order. A GeoPackage is preferred because
# a full-statewide All-Roads merge is ~1M+ features — past shapefile's 2 GB / 10-
# char-field limits. The .shp name is kept for backward compatibility with the
# existing partial merge. Build a new one with merge_tiger_roads.py.
_ROADS_FILENAMES = ("all_roads_merged.gpkg", "all_roads_merged.shp")


def _resolve_env_data() -> Path:
    """Prefer environment_data/ next to app/; fall back to MigrationFiles/MigrationAnalyzer/."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent / "environment_data",           # canonical
        here.parent.parent.parent.parent.parent,                  # MigrationFiles/MigrationAnalyzer/
    ]
    for c in candidates:
        if any((c / fn).exists() for fn in _ROADS_FILENAMES):
            return c
    return candidates[0]


def _resolve_roads_file() -> Optional[Path]:
    """First existing roads layer in _ENV_DATA (gpkg preferred, then shp)."""
    for fn in _ROADS_FILENAMES:
        p = _ENV_DATA / fn
        if p.exists():
            return p
    return None


_ENV_DATA = _resolve_env_data()
_MERGED_SHP = _resolve_roads_file()

# MTFCC codes:
#   S1100 = primary road (interstate / US highway, limited access)
#   S1200 = secondary road (US highway, state highway, county highway)
#   S1400 = local neighborhood / rural road / city street
# A "highway" is a numbered primary or secondary road (S1100/S1200). A "road" is
# ANY of those PLUS local roads (S1400) — so an animal that crosses only a county
# or local road is still counted as crossing a road. Previously S1400 (the vast
# majority of features) was excluded, so most real road crossings reported False.
_HIGHWAY_CODES = {"S1100", "S1200"}
_ROAD_CODES = {"S1100", "S1200", "S1400"}

_roads_cache: dict[str, gpd.GeoDataFrame] = {}


def _load_roads(category: str = "roads") -> Optional[gpd.GeoDataFrame]:
    if category in _roads_cache:
        return _roads_cache[category]

    if _MERGED_SHP is None or not _MERGED_SHP.exists():
        return None

    codes = _ROAD_CODES if category == "roads" else _HIGHWAY_CODES
    gdf = gpd.read_file(str(_MERGED_SHP))
    gdf = gdf[gdf["MTFCC"].isin(codes)].to_crs("EPSG:4326")
    gdf.sindex  # build spatial index
    _roads_cache[category] = gdf
    return gdf


def detect_crossings(
    lon: np.ndarray,
    lat: np.ndarray,
) -> dict:
    """
    Check if a movement track crosses any roads or highways.

    Returns dict with keys 'crosses_road' and 'crosses_highway' (bool).
    """
    result = {"crosses_road": False, "crosses_highway": False}

    if len(lon) < 2:
        return result

    coords = list(zip(lon.astype(float), lat.astype(float)))
    valid = [(x, y) for x, y in coords if np.isfinite(x) and np.isfinite(y)]
    if len(valid) < 2:
        return result

    track = LineString(valid)

    # Check roads (S1100 + S1200)
    roads = _load_roads("roads")
    if roads is not None:
        candidates = roads.sindex.query(track, predicate="intersects")
        if len(candidates) > 0:
            result["crosses_road"] = True
            # Check if any of those are highways specifically
            hit_codes = set(roads.iloc[candidates]["MTFCC"].values)
            if hit_codes & _HIGHWAY_CODES:
                result["crosses_highway"] = True

    return result


def detect_crossings_batch(
    df: pd.DataFrame,
    animal_col: str = "id_bio_year",
    lon_col: str = "lon",
    lat_col: str = "lat",
) -> dict[str, dict]:
    """
    Detect road/highway crossings for all animals at once.
    Returns {animal_key: {"crosses_road": bool, "crosses_highway": bool}}.
    """
    results = {}

    for animal_key, grp in df.groupby(animal_col):
        grp = grp.dropna(subset=[lon_col, lat_col])
        # Order the track chronologically so the connecting segments follow the
        # animal's actual movement (groupby preserves input order, which may not
        # be time-sorted). ISO-string timestamps sort chronologically too.
        if "timestamp" in grp.columns:
            grp = grp.sort_values("timestamp")
        if len(grp) < 2:
            results[animal_key] = {"crosses_road": False, "crosses_highway": False}
            continue
        results[animal_key] = detect_crossings(
            grp[lon_col].values,
            grp[lat_col].values,
        )

    return results
