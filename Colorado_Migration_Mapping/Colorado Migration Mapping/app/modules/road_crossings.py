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
        here.parent.parent.parent / "environment_data",                # canonical (Setup.bat renames the zip to this)
        here.parent.parent.parent / "Ext_FilesForMigrationAnalyzer",   # zip extracted but not renamed to environment_data
        here.parent.parent.parent.parent.parent,                       # MigrationFiles/MigrationAnalyzer/
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


def roads_file() -> Optional[Path]:
    """The resolved merged-roads layer, or None if no roads file was found under
    the environment-data directory. Lets the UI warn up front (instead of
    silently reporting zero crossings) when the data isn't installed."""
    return _MERGED_SHP


def env_data_dir() -> Path:
    """The environment-data directory the roads loader is pointed at, whether or
    not it actually contains a roads file. Used in the 'data not found' warning."""
    return _ENV_DATA

# MTFCC codes:
#   S1100 = primary road (interstate / US highway, limited access)
#   S1200 = secondary road (US highway, state highway, county highway)
#   S1400 = local neighborhood / rural road / city street
# "highway" = numbered primary/secondary road (S1100/S1200).
# "road"    = local road only (S1400).
# These are INDEPENDENT (changed 2026-09-02): an animal can cross a highway, a
# local road, both, or neither. Previously "road" was the superset
# S1100/S1200/S1400, so any highway crossing also counted as a road crossing
# (crosses_road was redundant whenever crosses_highway was True).
_HIGHWAY_CODES = {"S1100", "S1200"}
_ROAD_CODES = {"S1400"}

_roads_cache: dict[str, gpd.GeoDataFrame] = {}
_roads_full: Optional[gpd.GeoDataFrame] = None  # all road+highway codes, EPSG:4326


def _load_roads(category: str = "roads") -> Optional[gpd.GeoDataFrame]:
    """Return the road ('roads' = S1400) or highway ('highways' = S1100/S1200)
    subset in EPSG:4326, with a spatial index. The source gpkg is read from disk
    only ONCE (cached in _roads_full) and both subsets are sliced from it, so
    detecting road + highway crossings for a whole run costs a single file read."""
    if category in _roads_cache:
        return _roads_cache[category]

    if _MERGED_SHP is None or not _MERGED_SHP.exists():
        return None

    global _roads_full
    if _roads_full is None:
        gdf = gpd.read_file(str(_MERGED_SHP))
        gdf = gdf[gdf["MTFCC"].isin(_ROAD_CODES | _HIGHWAY_CODES)]
        _roads_full = gdf.to_crs("EPSG:4326")

    codes = _ROAD_CODES if category == "roads" else _HIGHWAY_CODES
    sub = _roads_full[_roads_full["MTFCC"].isin(codes)].copy()
    sub.sindex  # build spatial index
    _roads_cache[category] = sub
    return sub


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

    # Road (local, S1400) and highway (numbered, S1100/S1200) are checked
    # INDEPENDENTLY, so an animal can cross one, the other, both, or neither.
    roads = _load_roads("roads")
    if roads is not None and len(roads.sindex.query(track, predicate="intersects")) > 0:
        result["crosses_road"] = True

    highways = _load_roads("highways")
    if highways is not None and len(highways.sindex.query(track, predicate="intersects")) > 0:
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
