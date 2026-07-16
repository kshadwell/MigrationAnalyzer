"""
data_ingestion.py

Handles loading raw GPS telemetry data and computing all movement parameters,
replicating the Migration Mapper App 1 pipeline in Python.

Input CSV columns expected:
    Species, Project, TrakAID, LoclAID, Sex, AgeClass,
    DT_MST, Long, Lat, UTME, UTMN, UTM_Zn,
    Cllr_Spd, DOP, NumSats
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "animal_id_col": "LoclAID",
    "timestamp_col": "DT_MST",
    "timestamp_format": "%Y-%m-%d %H:%M:%S",
    "input_crs": "EPSG:4326",
    "lon_col": "Long",
    "lat_col": "Lat",
    "utme_col": "UTME",
    "utmn_col": "UTMN",
    "utm_zone_col": "UTM_Zn",
    "tmax_seconds": 176400,          # 49 hours — new burst threshold
    "n_ref_points": 20,              # NSD reference points
    "bio_year_start_month": 2,
    "bio_year_start_day": 1,
    "max_speed_kmh": 10.8,           # problem-point speed threshold
    "mort_distance_m": 50,           # mortality distance threshold
    "mort_time_hours": 48,           # mortality time window
    "dop_cutoff": 10,                # DOP quality filter
    "sat_cutoff": 6,                 # minimum satellites
}

# Maps Wildlife Tracker app-download column names → MigrationMapper names
APP_DOWNLOAD_COLUMN_MAP: dict[str, str] = {
    "animalIdLocal": "LoclAID",
    "animalTrackerId": "TrakAID",
    "species": "Species",
    "projectName": "Project",
    "sex": "Sex",
    "captureAgeClass": "AgeClass",
    "mtReadable": "DT_MST",
    "speedCollar": "Cllr_Spd",
    "dop": "DOP",
    "numSats": "NumSats",
    "longitude": "Long",
    "latitude": "Lat",
    "utm_datum_and_zone": "UTM_D_Z",
    "utmZone": "UTM_Zn",
    "UTME": "UTME",
    "UTMN": "UTMN",
    "dau": "DAU",
    "captureGmu": "CptrGMU",
    "captureDau": "CptrDAU",
}


# ---------------------------------------------------------------------------
# 0. Auto-detect and remap app-download columns
# ---------------------------------------------------------------------------

def detect_and_remap_columns(df: pd.DataFrame, log: list[str]) -> pd.DataFrame:
    """
    If the CSV looks like a Wildlife Tracker app download (has columns like
    'animalIdLocal', 'mtReadable', etc.), remap them to MigrationMapper names.
    """
    app_cols = set(APP_DOWNLOAD_COLUMN_MAP.keys())
    present = app_cols & set(df.columns)
    if len(present) >= 3:
        log.append(f"Detected app-download format ({len(present)} matching columns)")
        existing = set(df.columns)
        rename = {}
        for src, dst in APP_DOWNLOAD_COLUMN_MAP.items():
            if src not in df.columns:
                continue
            # Renaming src→dst when dst already exists (and isn't src itself)
            # would create two identically-named columns, which corrupts the
            # DataFrame's internal block layout and later raises a confusing
            # "IndexError: tuple index out of range" on *any* column access.
            # Skip the rename and keep the column that's already MAPP-named.
            if dst in existing and dst != src:
                log.append(
                    f"  Skipped rename {src} → {dst}: '{dst}' already exists "
                    f"(keeping existing '{dst}', leaving '{src}' as-is)"
                )
                continue
            rename[src] = dst
        if rename:
            df = df.rename(columns=rename)
            mapped_names = [f"  {k} → {v}" for k, v in rename.items()]
            log.append("Column mapping applied:\n" + "\n".join(mapped_names))

    # Final safety net: if duplicate column names exist for any other reason,
    # drop later duplicates (keep first) so downstream column access can't hit
    # the BlockManager corruption above.
    if df.columns.duplicated().any():
        dups = sorted(set(df.columns[df.columns.duplicated()]))
        log.append(f"WARNING: dropping duplicate columns (kept first of): {', '.join(map(str, dups))}")
        df = df.loc[:, ~df.columns.duplicated()]
    return df


# ---------------------------------------------------------------------------
# 0b. Quality filtering (DOP, NumSats, bad coordinates)
# ---------------------------------------------------------------------------

def quality_filter(
    df: pd.DataFrame,
    dop_cutoff: float = 10,
    sat_cutoff: int = 6,
    lon_col: str = "Long",
    lat_col: str = "Lat",
    log: list[str] | None = None,
    is_projected: bool = False,
) -> pd.DataFrame:
    """
    Quality screening before geometry/movement math.

    DOP and satellite failures are NO LONGER dropped here — they are kept so
    they remain visible on Tab 2 and are instead FLAGGED as problem points
    later (see :func:`flag_problem_points`). This function only:
      1. Logs the DOP > dop_cutoff and NumSats < sat_cutoff counts (kept).
      2. Removes fixes with positive longitude (Germany/test points) or NA
         coordinates — these are unmappable and cannot enter geometry math,
         so they must still be dropped.

    The ``dop_cutoff`` / ``sat_cutoff`` args are retained for the logging only;
    the actual flagging uses the same cutoffs in ``flag_problem_points``.
    """
    if log is None:
        log = []

    before = len(df)
    log.append(f"Records before quality filtering: {before:,}")

    # DOP — counted here, flagged (not dropped) in flag_problem_points.
    if dop_cutoff is None:
        log.append("DOP cutoff blank — DOP flagging disabled")
    elif "DOP" in df.columns:
        high_dop = int(df["DOP"].gt(dop_cutoff).sum())
        log.append(f"Records with high DOP (>{dop_cutoff}): {high_dop:,} (kept, will be flagged)")
    else:
        log.append("DOP column not found — skipping DOP check")

    # Satellites — counted here, flagged (not dropped) in flag_problem_points.
    if sat_cutoff is None:
        log.append("Satellite cutoff blank — satellite flagging disabled")
    elif "NumSats" in df.columns:
        low_sats = int(df["NumSats"].lt(sat_cutoff).sum())
        log.append(f"Records with low satellites (<{sat_cutoff}): {low_sats:,} (kept, will be flagged)")
    else:
        log.append("NumSats column not found — skipping satellite check")

    # Bad coordinates (positive longitude = Germany/test, or NA) — unmappable,
    # still removed. Skip the hemisphere check for projected CRS (easting values
    # are always positive).
    if lon_col in df.columns and lat_col in df.columns:
        na_coords = int(df[lon_col].isna().sum() + df[lat_col].isna().sum())
        if is_projected:
            if na_coords > 0:
                log.append(f"WARNING: Found {na_coords} records with NA coordinates — removing")
                df = df[df[lon_col].notna() & df[lat_col].notna()]
            else:
                log.append("PASS: No NA coordinates (projected CRS — hemisphere check skipped)")
        else:
            bad_lon = int((df[lon_col] > 0).sum())
            bad_total = bad_lon + na_coords
            if bad_total > 0:
                log.append(f"WARNING: Found {bad_total} records with bad coordinates — removing")
                df = df[(df[lon_col] < 0) & df[lon_col].notna() & df[lat_col].notna()]
            else:
                log.append("PASS: All coordinates in Western hemisphere")

    after = len(df)
    removed = before - after
    log.append(f"Records after quality filtering: {after:,} (removed {removed:,} unmappable)")

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 0c. Validation checks
# ---------------------------------------------------------------------------

def validate_for_migration_mapper(
    df: pd.DataFrame,
    animal_id_col: str = "LoclAID",
    timestamp_col: str | list[str] = "DT_MST",
    lon_col: str = "Long",
    lat_col: str = "Lat",
    log: list[str] | None = None,
    is_projected: bool = False,
) -> bool:
    """
    Run the same validation checks as the R script.
    Returns True if all critical checks pass.
    """
    if log is None:
        log = []
    if isinstance(timestamp_col, str):
        timestamp_col = [timestamp_col]

    log.append("")
    log.append("Running Migration Mapper compatibility checks...")
    log.append("=" * 50)

    passed = True

    # Check 1: Required columns
    required = [animal_id_col] + timestamp_col + [lon_col, lat_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        log.append(f"FAIL: Missing required columns: {', '.join(missing)}")
        passed = False
    else:
        log.append(f"PASS: All required columns present ({', '.join(required)})")

    # Check 1b: NA/empty values in required fields
    for col in required:
        if col in df.columns:
            na_count = df[col].isna().sum()
            empty_count = (df[col].astype(str).str.strip() == "").sum() if df[col].dtype == object else 0
            total_bad = int(na_count + empty_count)
            if total_bad > 0:
                log.append(f"FAIL: Found {total_bad} NA/empty values in {col}")
                passed = False
    if passed:
        log.append("PASS: No NA/NULL values in required fields")

    # Check 2: No positive longitude (geographic CRS only)
    if not is_projected and lon_col in df.columns:
        germany = int((df[lon_col] > 0).sum())
        if germany > 0:
            log.append(f"FAIL: Found {germany} points with positive longitude (Germany/test data)")
            passed = False
        else:
            log.append("PASS: All coordinates in Western hemisphere")
    elif is_projected:
        log.append("INFO: Projected CRS — hemisphere check skipped")

    # Check 3: Coordinate ranges
    if lon_col in df.columns and lat_col in df.columns:
        x_min, x_max = df[lon_col].min(), df[lon_col].max()
        y_min, y_max = df[lat_col].min(), df[lat_col].max()
        if is_projected:
            log.append(f"INFO: Easting range: {x_min:.2f} to {x_max:.2f}")
            log.append(f"INFO: Northing range: {y_min:.2f} to {y_max:.2f}")
        else:
            log.append(f"INFO: Longitude range: {x_min:.2f} to {x_max:.2f}")
            log.append(f"INFO: Latitude range: {y_min:.2f} to {y_max:.2f}")

    # Check 4: DateTime format
    ts_present = [c for c in timestamp_col if c in df.columns]
    if ts_present and len(df) > 0:
        if len(ts_present) == 1:
            sample = str(df[ts_present[0]].iloc[0])
        else:
            sample = " ".join(str(df[c].iloc[0]) for c in ts_present)
        import re
        if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", sample):
            log.append(f"PASS: DateTime format valid (sample: {sample})")
        else:
            log.append(f"WARNING: DateTime format may not be standard: {sample}")

    # Check 5: Enough data
    if len(df) < 100:
        log.append(f"WARNING: Only {len(df)} records — may be too few for analysis")

    log.append("=" * 50)
    if passed:
        log.append("VALIDATION PASSED")
    else:
        log.append("VALIDATION FAILED — Fix data issues before proceeding!")

    return passed


# ---------------------------------------------------------------------------
# 1. load_data
# ---------------------------------------------------------------------------

def load_data(
    filepath: str | Path,
    animal_id_col: Optional[str] = None,
    timestamp_col: Optional[str | list[str]] = None,
    timestamp_format: str = "%Y-%m-%d %H:%M:%S",
    lon_col: str = "Long",
    lat_col: str = "Lat",
    utme_col: str = "UTME",
    utmn_col: str = "UTMN",
    utm_zone_col: str = "UTM_Zn",
    crs: str = "EPSG:4326",
    df: Optional[pd.DataFrame] = None,
) -> gpd.GeoDataFrame:
    """
    Load GPS telemetry data from a CSV or shapefile.

    Detects format from file extension. Standardizes column names to:
        animal_id, timestamp, lon, lat, x, y (UTM easting/northing).

    If UTM columns are absent, auto-detects the UTM zone from the median
    lon/lat and projects coordinates.

    Parameters
    ----------
    filepath : str or Path
        Path to the input file (.csv, .shp, .gpkg, .geojson, etc.).
    df : pandas.DataFrame, optional
        Pre-loaded DataFrame to use instead of re-reading ``filepath``.
        Lets callers (e.g. :func:`process_data`) avoid a second file parse
        when they already have the data in memory. Must already contain
        lon/lat columns (or whatever the ``lon_col`` / ``lat_col`` args
        name). The file is only consulted to decide between the CSV and
        shapefile branches below.
    animal_id_col : str, optional
        Source column for animal ID. Defaults to 'LoclAID'.
    timestamp_col : str, optional
        Source column for timestamp. Defaults to 'DT_MST'.
    timestamp_format : str
        strptime format string for parsing timestamps.
    lon_col, lat_col : str
        Source column names for longitude / latitude.
    utme_col, utmn_col, utm_zone_col : str
        Source column names for UTM easting, northing, and zone.
    crs : str
        CRS of the lon/lat columns (default WGS-84).

    Returns
    -------
    gpd.GeoDataFrame
        Points in WGS-84 (EPSG:4326) with standardized columns.
    """
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    # CSV path covers two cases now: an actual .csv on disk, OR a caller
    # that handed us a pre-loaded DataFrame (df=...) regardless of source
    # extension. The shapefile branch only runs when we have to read the
    # geometry from disk ourselves.
    if ext == ".csv" or df is not None:
        if df is None:
            df = pd.read_csv(filepath, low_memory=False)
        else:
            df = df.copy()
        # Resolve defaults
        _animal_col = animal_id_col or "LoclAID"
        _ts_col = timestamp_col or "DT_MST"
        if isinstance(_ts_col, str):
            _ts_col = [_ts_col]

        # Combine multiple timestamp columns into one before renaming
        if len(_ts_col) > 1:
            present = [c for c in _ts_col if c in df.columns]
            if present:
                df["timestamp"] = df[present].astype(str).agg(" ".join, axis=1)
        elif len(_ts_col) == 1 and _ts_col[0] in df.columns:
            df = df.rename(columns={_ts_col[0]: "timestamp"})

        # Rename to standardized names
        rename_map: dict[str, str] = {}
        if _animal_col in df.columns:
            rename_map[_animal_col] = "animal_id"
        if lon_col in df.columns:
            rename_map[lon_col] = "lon"
        if lat_col in df.columns:
            rename_map[lat_col] = "lat"
        if utme_col in df.columns:
            rename_map[utme_col] = "x"
        if utmn_col in df.columns:
            rename_map[utmn_col] = "y"
        if utm_zone_col in df.columns:
            rename_map[utm_zone_col] = "utm_zone"

        df = df.rename(columns=rename_map)

        # Parse timestamp
        if "timestamp" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            _fmt = "mixed" if len(_ts_col) > 1 else timestamp_format
            df["timestamp"] = pd.to_datetime(df["timestamp"], format=_fmt, errors="coerce")

        gdf = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["lon"], df["lat"]),
            crs=crs,
        )

        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")
            gdf["lon"] = gdf.geometry.x
            gdf["lat"] = gdf.geometry.y
    else:
        # Shapefile / GeoPackage / GeoJSON etc.
        gdf = gpd.read_file(filepath)
        gdf.attrs["original_crs"] = str(gdf.crs) if gdf.crs else "unknown"
        _animal_col = animal_id_col or "LoclAID"
        _ts_col = timestamp_col or "DT_MST"
        if isinstance(_ts_col, str):
            _ts_col = [_ts_col]

        # Combine multiple timestamp columns into one before renaming
        if len(_ts_col) > 1:
            present = [c for c in _ts_col if c in gdf.columns]
            if present:
                gdf["timestamp"] = gdf[present].astype(str).agg(" ".join, axis=1)
        elif len(_ts_col) == 1 and _ts_col[0] in gdf.columns:
            gdf = gdf.rename(columns={_ts_col[0]: "timestamp"})

        rename_map = {}
        for src, dst in [
            (_animal_col, "animal_id"),
            (lon_col, "lon"),
            (lat_col, "lat"),
            (utme_col, "x"),
            (utmn_col, "y"),
            (utm_zone_col, "utm_zone"),
        ]:
            if src in gdf.columns:
                rename_map[src] = dst
        gdf = gdf.rename(columns=rename_map)

        if "timestamp" in gdf.columns:
            _fmt = "mixed" if len(_ts_col) > 1 else timestamp_format
            gdf["timestamp"] = pd.to_datetime(gdf["timestamp"], format=_fmt, errors="coerce")

        # Ensure lon/lat columns exist from geometry if missing
        if "lon" not in gdf.columns:
            gdf["lon"] = gdf.geometry.x
        if "lat" not in gdf.columns:
            gdf["lat"] = gdf.geometry.y

        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")
            gdf["lon"] = gdf.geometry.x
            gdf["lat"] = gdf.geometry.y

    # Compute UTM x/y if not already present
    if "x" not in gdf.columns or gdf["x"].isna().all():
        gdf = _project_to_utm(gdf)
    else:
        gdf["x"] = pd.to_numeric(gdf["x"], errors="coerce")
        gdf["y"] = pd.to_numeric(gdf["y"], errors="coerce")

    gdf = gdf.sort_values(["animal_id", "timestamp"]).reset_index(drop=True)
    return gdf


def _utm_zone_from_lon(lon: float) -> int:
    """Return UTM zone number for a given longitude."""
    return int((lon + 180) / 6) + 1


def _project_to_utm(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Auto-detect UTM zone from median lon and project to UTM.
    Adds 'x' (easting) and 'y' (northing) columns.
    """
    med_lon = float(np.nanmedian(gdf["lon"]))
    med_lat = float(np.nanmedian(gdf["lat"]))
    zone = _utm_zone_from_lon(med_lon)
    hemisphere = "north" if med_lat >= 0 else "south"
    utm_crs = f"+proj=utm +zone={zone} +{hemisphere} +datum=WGS84 +units=m +no_defs"

    transformer = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    lons = gdf["lon"].to_numpy(dtype=float)
    lats = gdf["lat"].to_numpy(dtype=float)
    xs, ys = transformer.transform(lons, lats)
    gdf = gdf.copy()
    gdf["x"] = xs
    gdf["y"] = ys
    gdf["utm_zone"] = zone
    return gdf


# ---------------------------------------------------------------------------
# 2. calc_burst
# ---------------------------------------------------------------------------

def calc_burst(
    df: pd.DataFrame,
    id_col: str = "animal_id",
    date_col: str = "timestamp",
    tmax_seconds: float = 176400,
) -> pd.Series:
    """
    Assign integer burst IDs.

    A new burst begins when:
        - The animal ID changes, or
        - The time gap between successive fixes exceeds tmax_seconds.

    Parameters
    ----------
    df : pd.DataFrame
        Must be sorted by id_col, date_col.
    id_col : str
        Column identifying individual animals.
    date_col : str
        Timestamp column.
    tmax_seconds : float
        Maximum allowed gap (seconds) within a burst. Default = 176400 (49 h).

    Returns
    -------
    pd.Series (int)
        Burst ID for each row, indexed like df.
    """
    ids = df[id_col].to_numpy()
    times = df[date_col].to_numpy(dtype="datetime64[ns]")

    # Boolean array: True where a new burst starts
    new_animal = np.empty(len(df), dtype=bool)
    new_animal[0] = True
    new_animal[1:] = ids[1:] != ids[:-1]

    dt_ns = np.empty(len(df), dtype=float)
    dt_ns[0] = 0.0
    dt_ns[1:] = (times[1:].astype(np.float64) - times[:-1].astype(np.float64))
    dt_seconds = dt_ns / 1e9

    new_burst = new_animal | (dt_seconds > tmax_seconds)
    burst_ids = new_burst.cumsum()
    return pd.Series(burst_ids, index=df.index, name="burst_id", dtype=int)


# ---------------------------------------------------------------------------
# 3. calc_movement_params
# ---------------------------------------------------------------------------

def calc_movement_params(
    df: pd.DataFrame,
    id_col: str = "animal_id",
    date_col: str = "timestamp",
) -> pd.DataFrame:
    """
    Compute per-step movement parameters.

    Requires columns: x (UTM easting), y (UTM northing), burst_id.
    NAs are set at burst boundaries (first fix of each burst).

    New columns added:
        dist        — step distance (meters)
        dt          — elapsed time (seconds)
        speed       — speed (m/s)
        abs_angle   — absolute bearing (degrees, N=0, clockwise)
        rel_angle   — relative/turning angle (degrees, −180 to 180)
        fix_rate_hours — fix interval in hours

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'x', 'y', 'burst_id', id_col, date_col.

    Returns
    -------
    pd.DataFrame
        Original df with movement columns appended.
    """
    df = df.copy()

    x = df["x"].to_numpy(dtype=float)
    y = df["y"].to_numpy(dtype=float)
    times = df[date_col].to_numpy(dtype="datetime64[ns]").astype(np.float64)
    bursts = df["burst_id"].to_numpy()
    ids = df[id_col].to_numpy()

    n = len(df)

    dist = np.full(n, np.nan)
    dt = np.full(n, np.nan)
    speed = np.full(n, np.nan)
    abs_angle = np.full(n, np.nan)
    rel_angle = np.full(n, np.nan)

    # Same-burst mask (shifted comparison)
    same_burst = np.empty(n, dtype=bool)
    same_burst[0] = False
    same_burst[1:] = bursts[1:] == bursts[:-1]

    # Compute dx, dy, dt for all steps
    dx = np.empty(n, dtype=float)
    dy = np.empty(n, dtype=float)
    dt_ns = np.empty(n, dtype=float)
    dx[0] = np.nan
    dy[0] = np.nan
    dt_ns[0] = np.nan
    dx[1:] = x[1:] - x[:-1]
    dy[1:] = y[1:] - y[:-1]
    dt_ns[1:] = times[1:] - times[:-1]

    dt_sec = dt_ns / 1e9

    # Apply same-burst mask
    dist = np.where(same_burst, np.sqrt(dx**2 + dy**2), np.nan)
    dt_out = np.where(same_burst, dt_sec, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        speed_arr = np.where(dt_out > 0, dist / dt_out, np.nan)

    # Absolute bearing: atan2(dx, dy) gives bearing from N clockwise
    with np.errstate(invalid="ignore"):
        bearing = np.degrees(np.arctan2(dx, dy)) % 360
    abs_angle_arr = np.where(same_burst, bearing, np.nan)

    # Relative/turning angle: difference between successive bearings
    rel_angle_arr = np.full(n, np.nan)
    # Need two consecutive valid bearings in same burst
    same_burst_shifted = np.empty(n, dtype=bool)
    same_burst_shifted[0] = False
    same_burst_shifted[1:] = same_burst[1:] & same_burst[:-1]

    angle_diff = np.empty(n, dtype=float)
    angle_diff[1:] = abs_angle_arr[1:] - abs_angle_arr[:-1]
    angle_diff[0] = np.nan
    # Wrap to −180..180
    angle_diff = (angle_diff + 180) % 360 - 180
    rel_angle_arr = np.where(same_burst_shifted, angle_diff, np.nan)

    fix_rate_hours = np.where(dt_out > 0, dt_out / 3600.0, np.nan)

    df["dist"] = dist
    df["dt"] = dt_out
    df["speed"] = speed_arr
    df["abs_angle"] = abs_angle_arr
    df["rel_angle"] = rel_angle_arr
    df["fix_rate_hours"] = fix_rate_hours

    return df


# ---------------------------------------------------------------------------
# 4. calc_nsd
# ---------------------------------------------------------------------------

def calc_nsd(
    df: pd.DataFrame,
    id_col: str,
    date_col: str,
    group_col: str,
    n_ref_points: int = 20,
) -> pd.DataFrame:
    """
    Compute Net Squared Displacement (NSD) and displacement.

    Reference location = mean of the first n_ref_points per group_col.

    New columns added:
        ref_x_{group_col}, ref_y_{group_col} — reference coordinates
        nsd_{group_col}       — NSD in km²
        displacement_{group_col} — straight-line displacement in km

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'x', 'y', group_col columns.
    id_col : str
        Animal ID column.
    date_col : str
        Timestamp column (used for ordering).
    group_col : str
        Grouping column (e.g. 'id_yr', 'id_bio_year', 'animal_id').
    n_ref_points : int
        Number of first fixes to average for reference location.

    Returns
    -------
    pd.DataFrame
        df with NSD columns appended.
    """
    df = df.copy()

    ref_x_col = f"ref_x_{group_col}"
    ref_y_col = f"ref_y_{group_col}"
    nsd_col = f"nsd_{group_col}"
    disp_col = f"displacement_{group_col}"

    # Compute reference location per group
    ref_locs = (
        df.sort_values([group_col, date_col])
        .groupby(group_col, sort=False)
        .apply(lambda g: g[["x", "y"]].head(n_ref_points).mean())
    )
    ref_locs.columns = [ref_x_col, ref_y_col]
    ref_locs = ref_locs.reset_index()

    df = df.merge(ref_locs, on=group_col, how="left")

    dx = (df["x"] - df[ref_x_col]).to_numpy(dtype=float)
    dy = (df["y"] - df[ref_y_col]).to_numpy(dtype=float)

    nsd_m2 = dx**2 + dy**2
    df[nsd_col] = nsd_m2 / 1e6          # m² → km²
    df[disp_col] = np.sqrt(nsd_m2) / 1000.0  # m → km

    return df


# ---------------------------------------------------------------------------
# 5. calc_bio_year
# ---------------------------------------------------------------------------

def calc_bio_year(
    df: pd.DataFrame,
    bio_year_start_month: int = 2,
    bio_year_start_day: int = 1,
) -> pd.DataFrame:
    """
    Assign biological year and composite id_bio_year column.

    The biological year starts on bio_year_start_month/bio_year_start_day.
    Fixes before that date in a calendar year belong to the *previous*
    biological year.

    New columns added:
        bio_year    — integer biological year
        id_bio_year — '<animal_id>_<bio_year>'

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'timestamp' and 'animal_id'.

    Returns
    -------
    pd.DataFrame
    """
    df = df.copy()

    ts = df["timestamp"]
    year = ts.dt.year.to_numpy(dtype=int)
    month = ts.dt.month.to_numpy(dtype=int)
    day = ts.dt.day.to_numpy(dtype=int)

    # Is the fix before the biological year start within its calendar year?
    before_start = (month < bio_year_start_month) | (
        (month == bio_year_start_month) & (day < bio_year_start_day)
    )
    bio_year = np.where(before_start, year - 1, year)

    df["bio_year"] = bio_year
    df["id_bio_year"] = df["animal_id"].astype(str) + "_" + bio_year.astype(str)
    return df


# ---------------------------------------------------------------------------
# 6. flag_problem_points
# ---------------------------------------------------------------------------

def flag_problem_points(
    df: pd.DataFrame,
    max_speed_kmh: float | None = 10.8,
    dop_cutoff: float | None = 10,
    sat_cutoff: float | None = 6,
) -> pd.DataFrame:
    """
    Flag implausible / low-quality fixes. Sets 'problem' = 1 where ANY of:
      - speed exceeds ``max_speed_kmh`` (biologically implausible movement),
      - DOP exceeds ``dop_cutoff`` (poor fix geometry),
      - NumSats is below ``sat_cutoff`` (too few satellites).

    DOP and satellite fixes used to be dropped in :func:`quality_filter`;
    they are now kept and flagged here so they stay visible on Tab 2. Flagged
    points are still excluded from sequence extraction / modeling downstream.

    Each threshold is **independently disable-able**: pass ``None`` (e.g. the
    user cleared that Tab 1 box) to skip that check entirely. A threshold of 0
    is honoured literally, not treated as disabled. Speed requires the 'speed'
    column (m/s) from calc_movement_params; the DOP and NumSats checks need
    their columns present. NA values in any metric never flag.

    Parameters
    ----------
    df : pd.DataFrame
    max_speed_kmh : float or None
        Speed threshold in km/h (default 10.8 ≈ 3 m/s). None disables.
    dop_cutoff : float or None
        Max acceptable DOP; fixes with DOP > this are flagged. None disables.
    sat_cutoff : float or None
        Min acceptable satellite count; fixes with NumSats < this are flagged.
        None disables.

    Returns
    -------
    pd.DataFrame
    """
    df = df.copy()
    problem = np.zeros(len(df), dtype=int)

    # Speed — biologically implausible movement.
    if max_speed_kmh is not None and "speed" in df.columns:
        max_speed_ms = max_speed_kmh / 3.6
        speed_arr = df["speed"].to_numpy(dtype=float)
        problem |= np.where(
            np.isfinite(speed_arr) & (speed_arr > max_speed_ms), 1, 0
        )

    # DOP — poor fix geometry (kept & flagged, not dropped).
    if dop_cutoff is not None and "DOP" in df.columns:
        dop_arr = pd.to_numeric(df["DOP"], errors="coerce").to_numpy(dtype=float)
        problem |= np.where(
            np.isfinite(dop_arr) & (dop_arr > dop_cutoff), 1, 0
        )

    # Satellites — too few satellites for a reliable fix.
    if sat_cutoff is not None and "NumSats" in df.columns:
        sat_arr = pd.to_numeric(df["NumSats"], errors="coerce").to_numpy(dtype=float)
        problem |= np.where(
            np.isfinite(sat_arr) & (sat_arr < sat_cutoff), 1, 0
        )

    df["problem"] = problem
    return df


# ---------------------------------------------------------------------------
# 7. check_mortality
# ---------------------------------------------------------------------------

def check_mortality(
    df: pd.DataFrame,
    mort_distance_m: float | None = 50,
    mort_time_hours: float | None = 48,
) -> pd.DataFrame:
    """
    Flag potential mortality events.

    An animal is flagged as a mortality candidate starting at the fix where
    all subsequent fixes within mort_time_hours are within mort_distance_m
    of that fix (i.e., the animal effectively stopped moving).

    New column added:
        mortality_flag — 1 if fix is within a mortality window, else 0.

    The check is disabled (all fixes left unflagged) if EITHER threshold is
    ``None`` — i.e. the user cleared the distance or time box on Tab 1.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain 'animal_id', 'timestamp', 'x', 'y'.
    mort_distance_m : float or None
        Distance threshold in meters. None disables mortality detection.
    mort_time_hours : float or None
        Time window in hours. None disables mortality detection.

    Returns
    -------
    pd.DataFrame
    """
    df = df.copy()
    df["mortality_flag"] = 0

    if mort_distance_m is None or mort_time_hours is None:
        return df

    mort_time_ns = int(mort_time_hours * 3600 * 1_000_000_000)  # nanoseconds
    mort_d2 = float(mort_distance_m) ** 2

    for animal_id, grp in df.groupby("animal_id", sort=False):
        grp = grp.sort_values("timestamp")
        idx = grp.index.to_numpy()
        x = grp["x"].to_numpy(dtype=float)
        y = grp["y"].to_numpy(dtype=float)
        # int64 nanoseconds — keep integer math for searchsorted precision.
        times = grp["timestamp"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        n = len(grp)
        if n == 0:
            continue
        mort_flags = np.zeros(n, dtype=int)

        # Vectorised window lookup: for each fix i, find the exclusive end
        # index of fixes whose timestamp is within `mort_time_ns` of times[i].
        # This collapses the inner O(n) scan to O(log n) via searchsorted.
        window_ends = np.searchsorted(times, times + mort_time_ns, side="right")

        for i in range(n):
            j_end = int(window_ends[i])
            if j_end <= i + 1:
                continue
            dx = x[i + 1:j_end] - x[i]
            dy = y[i + 1:j_end] - y[i]
            # Squared distances: avoids the per-point sqrt entirely.
            sq = dx * dx + dy * dy
            if sq.max() <= mort_d2:
                mort_flags[i] = 1

        df.loc[idx, "mortality_flag"] = mort_flags

    return df


# ---------------------------------------------------------------------------
# 8. process_data  (full pipeline)
# ---------------------------------------------------------------------------

def process_data(
    filepath: str | Path,
    config: Optional[dict] = None,
) -> tuple[gpd.GeoDataFrame, dict, list[str]]:
    """
    Full data processing pipeline.

    Returns (gdf, config, log) where log is a list of human-readable messages
    replicating the R script's print output.
    """
    cfg = {**DEFAULT_CONFIG}
    if config:
        cfg.update(config)

    log: list[str] = []

    # ---- 0. Load raw CSV and detect format ----
    filepath = Path(filepath)
    ext = filepath.suffix.lower()
    if ext == ".csv":
        raw_df = pd.read_csv(filepath, low_memory=False)
    else:
        raw_df = gpd.read_file(filepath)
        if hasattr(raw_df, "drop"):
            raw_df = pd.DataFrame(raw_df.drop(columns=["geometry"], errors="ignore"))

    log.append(f"Columns in the data:")
    log.append(f"  {', '.join(raw_df.columns.tolist())}")
    log.append(f"Total records: {len(raw_df):,}")

    input_crs = cfg.get("input_crs", "EPSG:4326")
    if ext != ".csv":
        log.append(f"Input CRS: detected from shapefile .prj")
    elif input_crs != "EPSG:4326":
        log.append(f"Input CRS: {input_crs} (will reproject to WGS84 / EPSG:4326)")
    else:
        log.append(f"Input CRS: WGS84 (EPSG:4326)")

    # ---- 0a. Auto-detect app-download columns and remap ----
    raw_df = detect_and_remap_columns(raw_df, log)

    # Resolve column names (use whatever names exist after remapping).
    animal_col = cfg.get("animal_id_col", "LoclAID")
    ts_col = cfg.get("timestamp_col", "DT_MST")
    if isinstance(ts_col, str):
        ts_col = [ts_col]
    lon_col = cfg.get("lon_col", "Long")
    lat_col = cfg.get("lat_col", "Lat")

    # The UI auto-fills these from the *raw* column names (e.g. "longitude"),
    # but detect_and_remap_columns above may have just renamed that column to
    # its MAPP name ("Long"). Reconcile: if a configured name is no longer
    # present but it's a known app-download source column, follow the rename to
    # the standardized name so the rest of the pipeline (quality_filter,
    # load_data) can find it. Without this, an app-download CSV whose columns
    # don't already use MAPP names dies later with KeyError: 'lon'.
    def _reconcile(name: str) -> str:
        if name in raw_df.columns:
            return name
        mapped = APP_DOWNLOAD_COLUMN_MAP.get(name)
        if mapped and mapped in raw_df.columns:
            log.append(f"  Using remapped column '{mapped}' for configured '{name}'")
            return mapped
        return name

    animal_col = _reconcile(animal_col)
    ts_col = [_reconcile(c) for c in ts_col]
    lon_col = _reconcile(lon_col)
    lat_col = _reconcile(lat_col)

    if animal_col in raw_df.columns:
        log.append(f"Unique animals: {raw_df[animal_col].nunique()}")

    # ---- 0b. Quality filtering (bad coords) + DOP/NumSats logging ----
    # cfg values may be None (user cleared the box) → quality_filter logs the
    # check as disabled and flag_problem_points skips it.
    _is_projected = input_crs != "EPSG:4326"
    raw_df = quality_filter(
        raw_df,
        dop_cutoff=cfg.get("dop_cutoff"),
        sat_cutoff=cfg.get("sat_cutoff"),
        lon_col=lon_col,
        lat_col=lat_col,
        log=log,
        is_projected=_is_projected,
    )

    # ---- 0c. Sort ----
    sort_cols = [c for c in [animal_col] + ts_col if c in raw_df.columns]
    if sort_cols:
        raw_df = raw_df.sort_values(sort_cols).reset_index(drop=True)

    log.append(f"Final record count: {len(raw_df):,}")
    if animal_col in raw_df.columns:
        log.append(f"Unique animals: {raw_df[animal_col].nunique()}")

    # ---- 0d. Validation ----
    validate_for_migration_mapper(
        raw_df,
        animal_id_col=animal_col,
        timestamp_col=ts_col,
        lon_col=lon_col,
        lat_col=lat_col,
        log=log,
        is_projected=_is_projected,
    )

    # ---- 1. Load into GeoDataFrame ----
    # Reuse the already-loaded raw_df (which has been remapped, quality-
    # filtered, and sorted) instead of re-parsing the file from disk. For
    # multi-million-row CSVs / shapefiles this cuts the I/O cost roughly
    # in half.
    log.append("")
    log.append("Processing movement parameters...")
    gdf = load_data(
        filepath,
        animal_id_col=animal_col,
        timestamp_col=ts_col,
        timestamp_format=cfg.get("timestamp_format", "%Y-%m-%d %H:%M:%S"),
        lon_col=lon_col,
        lat_col=lat_col,
        utme_col=cfg.get("utme_col", "UTME"),
        utmn_col=cfg.get("utmn_col", "UTMN"),
        utm_zone_col=cfg.get("utm_zone_col", "UTM_Zn"),
        crs=cfg.get("input_crs", "EPSG:4326"),
        df=raw_df,
    )

    original_crs = gdf.attrs.get("original_crs")
    if original_crs:
        cfg["input_crs"] = original_crs

    # The quality filter was already run on raw_df above, so we don't
    # re-filter on DOP / NumSats here. Keep the lon/lat sanity check though
    # so a corrupt row that somehow slipped past the filter doesn't poison
    # downstream geometry math.
    if "lon" in gdf.columns:
        gdf = gdf[(gdf["lon"] < 0) & gdf["lon"].notna() & gdf["lat"].notna()]
    gdf = gdf.reset_index(drop=True)

    # ---- 2. Deduplicate ----
    before = len(gdf)
    gdf = gdf.drop_duplicates(subset=["animal_id", "timestamp"]).reset_index(drop=True)
    n_dupes = before - len(gdf)
    if n_dupes:
        log.append(f"Removed {n_dupes:,} duplicate fixes")

    # ---- 3. Burst assignment ----
    gdf["burst_id"] = calc_burst(
        gdf, id_col="animal_id", date_col="timestamp",
        tmax_seconds=cfg["tmax_seconds"],
    )
    n_bursts = gdf["burst_id"].nunique()
    log.append(f"Burst assignment: {n_bursts:,} bursts (gap threshold: {cfg['tmax_seconds']/3600:.0f}h)")

    # ---- 4. Movement parameters ----
    gdf = calc_movement_params(gdf, id_col="animal_id", date_col="timestamp")
    median_fr = gdf["fix_rate_hours"].median()
    log.append(f"Movement parameters computed (median fix rate: {median_fr:.1f}h)")

    # ---- 5. Calendar-year grouping ----
    gdf["year"] = gdf["timestamp"].dt.year
    gdf["id_yr"] = gdf["animal_id"].astype(str) + "_" + gdf["year"].astype(str)

    # ---- 6. Biological year ----
    gdf = calc_bio_year(
        gdf,
        bio_year_start_month=cfg["bio_year_start_month"],
        bio_year_start_day=cfg["bio_year_start_day"],
    )
    n_bio = gdf["id_bio_year"].nunique()
    log.append(f"Biological year: {n_bio} animal-years (start: {cfg['bio_year_start_month']}/{cfg['bio_year_start_day']})")

    # ---- 7-9. NSD ----
    gdf = calc_nsd(gdf, id_col="animal_id", date_col="timestamp",
                   group_col="id_yr", n_ref_points=cfg["n_ref_points"])
    gdf = calc_nsd(gdf, id_col="animal_id", date_col="timestamp",
                   group_col="animal_id", n_ref_points=cfg["n_ref_points"])
    gdf = calc_nsd(gdf, id_col="animal_id", date_col="timestamp",
                   group_col="id_bio_year", n_ref_points=cfg["n_ref_points"])
    log.append(f"NSD computed (ref points: {cfg['n_ref_points']})")

    # ---- 10. Flag problem points (speed, DOP, satellites) ----
    # Any of these may be None (user cleared the box) → that check is skipped.
    _spd = cfg.get("max_speed_kmh")
    _dop = cfg.get("dop_cutoff")
    _sat = cfg.get("sat_cutoff")
    gdf = flag_problem_points(
        gdf,
        max_speed_kmh=_spd,
        dop_cutoff=_dop,
        sat_cutoff=_sat,
    )
    n_prob = int(gdf["problem"].sum())
    _crit = ", ".join(
        c for c in (
            f"speed > {_spd} km/h" if _spd is not None else "",
            f"DOP > {_dop}" if _dop is not None else "",
            f"sats < {_sat}" if _sat is not None else "",
        ) if c
    ) or "no criteria (all disabled)"
    log.append(f"Problem points flagged: {n_prob:,} ({_crit})")

    # ---- 11. Mortality check ----
    # Disabled if EITHER threshold is None (user cleared a box).
    _md = cfg.get("mort_distance_m")
    _mt = cfg.get("mort_time_hours")
    gdf = check_mortality(gdf, mort_distance_m=_md, mort_time_hours=_mt)
    n_mort = int(gdf["mortality_flag"].sum())
    if _md is None or _mt is None:
        log.append("Mortality flags: disabled (distance and/or time blank)")
    else:
        log.append(f"Mortality flags: {n_mort:,} (dist < {_md}m for {_mt}h)")

    # ---- 12. Derive a herd_id from the data (used as the filename prefix for
    # population-level outputs). Prefer the DAU code (CPW herd unit, e.g.
    # "A37"); fall back to Project / project_name.
    herd_id: Optional[str] = None
    for candidate_col in ("DAU", "dau", "CptrDAU", "Project", "project_name"):
        if candidate_col in gdf.columns:
            non_null = gdf[candidate_col].dropna()
            # Drop blanks after stripping so empties / "  " don't survive uniqueness.
            cleaned = [str(v).strip() for v in non_null if str(v).strip()]
            if cleaned:
                # Multi-DAU datasets join every distinct value as
                # <DAU1>_<DAU2>_…  Sorted so the same dataset always produces
                # the same herd_id regardless of row order.
                unique_values = sorted(set(cleaned))
                herd_id = "_".join(unique_values)
                cfg["herd_id"] = herd_id
                cfg["herd_id_source_col"] = candidate_col
                if len(unique_values) > 1:
                    log.append(
                        f"Herd ID: {herd_id} "
                        f"(joined {len(unique_values)} unique values from column '{candidate_col}')"
                    )
                else:
                    log.append(f"Herd ID: {herd_id} (from column '{candidate_col}')")
                break
    if not herd_id:
        cfg["herd_id"] = "Herd"
        log.append("Herd ID: defaulting to 'Herd' (no DAU/Project column found)")

    # Project name — used as the second token in filenames like
    # <Herd>_<ProjectName>_FlagsRemoved_<date>.shp. Pulled from Project /
    # project_name. Spaces are stripped (CamelCase: "Pronghorn Movement
    # Study" -> "PronghornMovementStudy") to match the reference convention.
    import re
    project_name: Optional[str] = None
    for candidate_col in ("Project", "project_name", "ProjectName"):
        if candidate_col in gdf.columns:
            non_null = gdf[candidate_col].dropna()
            if not non_null.empty:
                raw = str(non_null.iloc[0]).strip()
                if raw:
                    sanitised = re.sub(r"\s+", "", raw)
                    sanitised = re.sub(r"[^\w\-]", "", sanitised)
                    if sanitised:
                        project_name = sanitised
                        cfg["project_name"] = project_name
                        cfg["project_name_source_col"] = candidate_col
                        log.append(f"Project name: {project_name} (from column '{candidate_col}')")
                        break
    if not project_name:
        cfg["project_name"] = "Project"
        log.append("Project name: defaulting to 'Project' (no Project column found)")

    # Final guard: duplicate column names (from overlapping source/MAPP names or
    # a rename collision in load_data) corrupt the DataFrame's block layout and
    # later surface as a baffling "IndexError: tuple index out of range" on an
    # unrelated column. Drop later duplicates, keeping the first occurrence.
    if gdf.columns.duplicated().any():
        dups = sorted(set(gdf.columns[gdf.columns.duplicated()]))
        log.append(f"WARNING: removed duplicate columns before returning (kept first of): {', '.join(map(str, dups))}")
        gdf = gdf.loc[:, ~gdf.columns.duplicated()]

    log.append("")
    log.append(f"Processing complete: {len(gdf):,} records, {gdf['animal_id'].nunique()} animals")

    return gdf, cfg, log
