"""
raster_sampler.py

Sample environmental raster data at GPS point locations.
Uses MigrationAnalyzer's DEM tiles and SNODAS pickle cache.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Data paths — prefer environment_data/ next to app/, fall back to the
# MigrationAnalyzer/ folder where the elevation tiles + SNODAS pickle live
# in this repo. The app works whether or not the data has been moved.
# ---------------------------------------------------------------------------
def _resolve_env_data() -> Path:
    """Pick the first candidate that actually contains the env data."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent / "environment_data",           # canonical
        here.parent.parent.parent.parent.parent,                  # MigrationFiles/MigrationAnalyzer/
    ]
    for c in candidates:
        if (c / "elevation").is_dir() or (c / "snodas_colorado.pkl").exists():
            return c
    return candidates[0]  # canonical fallback (functions return NaN/zeros if absent)

_ENV_DATA = _resolve_env_data()
_DEM_DIR = _ENV_DATA / "elevation"
_SNODAS_PKL = _ENV_DATA / "snodas_colorado.pkl"

# SNODAS Colorado extraction window (must match download_snodas.py)
_CO_LAT_MIN, _CO_LAT_MAX = 36.5, 41.5
_CO_LON_MIN, _CO_LON_MAX = -109.5, -101.5
_CO_NROWS, _CO_NCOLS = 658, 903

# ---------------------------------------------------------------------------
# Caches — loaded lazily on first use
# ---------------------------------------------------------------------------
_dem_tiles: list = []
_dem_bounds: list = []
_snodas_cache: Optional[dict] = None


def _load_dem():
    """Load DEM GeoTIFF tile handles (lazy, once).

    USGS re-releases the same 1°×1° cell under different dates
    (``USGS_13_n42w106_<date>.tif``). We keep only ONE file per cell — the
    LARGEST, which reliably skips truncated / half-downloaded copies (a corrupt
    tile is far smaller than a complete one) and avoids loading redundant
    overlapping tiles into memory. This is what fixes elevation coming back empty
    when an old, truncated re-release sorted ahead of the good copies and got
    picked first. Files whose names don't encode an n{lat}w{lon} cell are kept."""
    global _dem_tiles, _dem_bounds
    if _dem_tiles:
        return

    import re
    import rasterio

    tifs = sorted(_DEM_DIR.glob("*.tif"))
    if not tifs:
        return

    best: dict[tuple[int, int], tuple] = {}
    passthrough: list = []
    for fp in tifs:
        m = re.search(r"n(\d+)w(\d+)", fp.name)
        if not m:
            passthrough.append(fp)
            continue
        key = (int(m.group(1)), int(m.group(2)))
        sz = fp.stat().st_size
        if key not in best or sz > best[key][1]:
            best[key] = (fp, sz)

    chosen = [fp for fp, _ in best.values()] + passthrough
    for fp in sorted(chosen, key=lambda p: p.name):
        ds = rasterio.open(str(fp))
        b = ds.bounds
        _dem_tiles.append(ds)
        _dem_bounds.append((b.left, b.bottom, b.right, b.top))


def _find_dem_tile(lat: float, lon: float):
    for i, (west, south, east, north) in enumerate(_dem_bounds):
        if south <= lat <= north and west <= lon <= east:
            return _dem_tiles[i]
    return None


def query_elevation(lat: float, lon: float) -> float:
    """Get DEM elevation (meters) at a single point. Returns NaN if no tile."""
    _load_dem()
    ds = _find_dem_tile(lat, lon)
    if ds is None:
        return np.nan
    from rasterio.transform import rowcol
    try:
        row, col = rowcol(ds.transform, lon, lat)
        if 0 <= row < ds.height and 0 <= col < ds.width:
            import rasterio
            window = rasterio.windows.Window(col, row, 1, 1)
            val = float(ds.read(1, window=window)[0, 0])
            if ds.nodata is not None and val == ds.nodata:
                return np.nan
            return val
    except Exception:
        pass
    return np.nan


def _load_snodas():
    """Load the SNODAS Colorado pickle (lazy, once). ~3.7 GB."""
    global _snodas_cache
    if _snodas_cache is not None:
        return

    if not _SNODAS_PKL.exists():
        _snodas_cache = {}
        return

    with open(str(_SNODAS_PKL), "rb") as f:
        _snodas_cache = pickle.load(f)


def _snodas_rowcol(lat: float, lon: float) -> tuple[int, int]:
    """Convert lat/lon to SNODAS Colorado grid row/col."""
    row = int((_CO_LAT_MAX - lat) / (_CO_LAT_MAX - _CO_LAT_MIN) * _CO_NROWS)
    col = int((lon - _CO_LON_MIN) / (_CO_LON_MAX - _CO_LON_MIN) * _CO_NCOLS)
    row = max(0, min(row, _CO_NROWS - 1))
    col = max(0, min(col, _CO_NCOLS - 1))
    return row, col


def query_snow(lat: float, lon: float, date_str: str) -> dict:
    """
    Get SNODAS snow data at a point for a given date.

    Parameters
    ----------
    date_str : str  "YYYYMMDD" format

    Returns dict with keys: snow_depth_m, swe_m, snow_density_kgm3
    """
    _load_snodas()
    result = {"snow_depth_m": 0.0, "swe_m": 0.0, "snow_density_kgm3": 0.0}

    if not _snodas_cache or date_str not in _snodas_cache:
        return result

    day = _snodas_cache[date_str]
    row, col = _snodas_rowcol(lat, lon)

    depth = float(day["depth"][row, col])
    swe = float(day["swe"][row, col])
    density = (swe / depth * 1000.0) if depth > 0.01 else 0.0

    result["snow_depth_m"] = depth
    result["swe_m"] = swe
    result["snow_density_kgm3"] = density
    return result


# ---------------------------------------------------------------------------
# Batch sampling — the main entry point for the app
# ---------------------------------------------------------------------------

# Snow variables (snow_depth_m, swe_m, snow_density_kgm3) were removed from the
# Tab 1 UI on 2026-06-22 — most users don't sample them, and those who need snow
# can upload a .wld file containing it. The SNODAS sampling code below is kept
# (harmless, still callable) so the capability can be restored by re-adding the
# entries here. Loading a project that already has snow columns still surfaces
# them (see the enrichment-column detection in main.py).
AVAILABLE_VARIABLES = {
    "elevation_m": "DEM Elevation (m)",
}


def sample_rasters(
    df: pd.DataFrame,
    variables: list[str],
    lat_col: str = "lat",
    lon_col: str = "lon",
    ts_col: str = "timestamp",
    progress_callback=None,
) -> pd.DataFrame:
    """
    Sample selected raster variables at every GPS fix in the DataFrame.

    Parameters
    ----------
    df : DataFrame with lat, lon, timestamp columns
    variables : list of variable names from AVAILABLE_VARIABLES
    progress_callback : optional callable(pct: int, msg: str) for progress updates

    Returns the DataFrame with new columns appended.
    """
    df = df.copy()
    n = len(df)

    if not variables or n == 0:
        return df

    # Names of DEM tiles that failed to read (corrupt/truncated). Surfaced to the
    # caller via df.attrs so the Tab 1 processing log can warn about points that
    # couldn't be sampled and point at the tile to re-download.
    dem_tile_errors: list[str] = []

    needs_elevation = "elevation_m" in variables
    needs_snow = any(v in variables for v in ("snow_depth_m", "swe_m", "snow_density_kgm3"))

    lats = df[lat_col].values.astype(float)
    lons = df[lon_col].values.astype(float)

    # Pre-parse timestamps for SNODAS date lookup
    if needs_snow:
        _load_snodas()
        ts = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
        date_strs = ts.dt.strftime("%Y%m%d").values

    # Initialize output arrays
    if needs_elevation:
        elev_arr = np.full(n, np.nan)
    snow_vars = {}
    for v in ("snow_depth_m", "swe_m", "snow_density_kgm3"):
        if v in variables:
            snow_vars[v] = np.zeros(n)

    # --- Elevation: use rasterio.sample() for fast batch point queries ---
    if needs_elevation:
        import rasterio
        from rasterio.transform import rowcol
        _load_dem()
        if _dem_tiles:
            tile_groups: dict[int, list[int]] = {}
            for i in range(n):
                lat_i, lon_i = lats[i], lons[i]
                if not (np.isfinite(lat_i) and np.isfinite(lon_i)):
                    continue
                for ti, (west, south, east, north) in enumerate(_dem_bounds):
                    if south <= lat_i <= north and west <= lon_i <= east:
                        tile_groups.setdefault(ti, []).append(i)
                        break

            for ti, indices in tile_groups.items():
                ds = _dem_tiles[ti]
                coords = [(float(lons[i]), float(lats[i])) for i in indices]
                try:
                    vals = list(ds.sample(coords))
                    for j, i in enumerate(indices):
                        v = float(vals[j][0])
                        if ds.nodata is not None and v == ds.nodata:
                            continue
                        elev_arr[i] = v
                except Exception:
                    # A corrupt/truncated DEM tile (a bad TIFF block →
                    # TIFFReadEncodedTile failed) makes the whole batch read
                    # raise. Fall back to per-point windowed reads so ONLY the
                    # unreadable pixels are lost (left NaN) — not every point in
                    # the tile, and never the entire elevation variable. Without
                    # this, one bad tile made Tab 1 log "raster sampling failed"
                    # and drop elevation for the whole dataset.
                    try:
                        dem_tile_errors.append(Path(ds.name).name)
                    except Exception:
                        dem_tile_errors.append(str(ti))
                    for i in indices:
                        try:
                            row, col = rowcol(ds.transform, float(lons[i]), float(lats[i]))
                            if 0 <= row < ds.height and 0 <= col < ds.width:
                                win = rasterio.windows.Window(col, row, 1, 1)
                                v = float(ds.read(1, window=win)[0, 0])
                                if ds.nodata is None or v != ds.nodata:
                                    elev_arr[i] = v
                        except Exception:
                            continue

            if progress_callback:
                progress_callback(50 if needs_snow else 95, "Elevation sampled")

    # --- SNODAS: vectorized grid lookup ---
    if needs_snow and _snodas_cache:
        rows = np.clip(
            ((_CO_LAT_MAX - lats) / (_CO_LAT_MAX - _CO_LAT_MIN) * _CO_NROWS).astype(int),
            0, _CO_NROWS - 1,
        )
        cols = np.clip(
            ((lons - _CO_LON_MIN) / (_CO_LON_MAX - _CO_LON_MIN) * _CO_NCOLS).astype(int),
            0, _CO_NCOLS - 1,
        )

        unique_dates = set(date_strs)
        available_dates = unique_dates & set(_snodas_cache.keys())

        for date_str in available_dates:
            mask = date_strs == date_str
            day = _snodas_cache[date_str]
            r = rows[mask]
            c = cols[mask]

            depth_vals = day["depth"][r, c]
            swe_vals = day["swe"][r, c]

            if "snow_depth_m" in snow_vars:
                snow_vars["snow_depth_m"][mask] = depth_vals
            if "swe_m" in snow_vars:
                snow_vars["swe_m"][mask] = swe_vals
            if "snow_density_kgm3" in snow_vars:
                with np.errstate(divide="ignore", invalid="ignore"):
                    density = np.where(depth_vals > 0.01, swe_vals / depth_vals * 1000.0, 0.0)
                snow_vars["snow_density_kgm3"][mask] = density

        if progress_callback:
            progress_callback(95, "Snow data sampled")

    # Attach columns to DataFrame
    if needs_elevation:
        df["elevation_m"] = elev_arr
    for v, arr in snow_vars.items():
        df[v] = arr

    if progress_callback:
        progress_callback(100, "Done")

    if dem_tile_errors:
        df.attrs["dem_tile_errors"] = sorted(set(dem_tile_errors))

    return df
