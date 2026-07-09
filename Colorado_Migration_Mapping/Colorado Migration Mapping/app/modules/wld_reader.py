"""
wld_reader.py

Read MigrationAnalyzer .wld files and extract selected variables
as a DataFrame, ready to merge with GPS data.
"""

from __future__ import annotations

import json
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# Column index → (name, human label, group)
WLD_COLUMNS: dict[int, tuple[str, str, str]] = {
    0:  ("epoch_seconds",       "Epoch (seconds)",          "Position & Time"),
    1:  ("wld_latitude",        "Latitude",                 "Position & Time"),
    2:  ("wld_longitude",       "Longitude",                "Position & Time"),
    3:  ("speed_kmh",           "Speed (km/h)",             "Position & Time"),
    4:  ("elevation_m",         "Elevation (m)",            "Position & Time"),
    5:  ("bearing",             "Bearing (°)",              "Position & Time"),
    6:  ("temp_c",              "Temperature (°C)",         "Position & Time"),
    7:  ("dt_hours",            "Time Delta (hrs)",         "Position & Time"),
    8:  ("impedance",           "Impedance",                "Movement Kernel"),
    9:  ("heat_suppression",    "Heat Suppression",         "Movement Kernel"),
    10: ("effective_speed",     "Effective Speed (km/h)",   "Movement Kernel"),
    11: ("speed_fast",          "Speed Fast (km/h)",        "Movement Kernel"),
    12: ("speed_slow",          "Speed Slow (km/h)",        "Movement Kernel"),
    13: ("density",             "Density (animals/km²)",    "Movement Kernel"),
    14: ("heading_consistency", "Heading Consistency",      "Movement Kernel"),
    15: ("gate_state",          "Gate State",               "Movement Kernel"),
    16: ("thermal_load",        "Thermal Load",             "Movement Kernel"),
    17: ("target_elevation",    "Target Elevation (m)",     "Movement Kernel"),
    18: ("displacement_km",     "Displacement (km)",        "Movement Kernel"),
    19: ("migration_charge",    "Migration Charge",         "Movement Kernel"),
    20: ("spring_energy",       "Spring Energy",            "Movement Kernel"),
    21: ("migrating",           "Migrating (0/1)",          "Movement Kernel"),
    22: ("migration_direction", "Migration Direction",      "Movement Kernel"),
    23: ("mortality_signal",    "Mortality Signal",         "Movement Kernel"),
    24: ("stationarity",        "Stationarity",             "Movement Kernel"),
    25: ("directedness",        "Directedness",             "Movement Kernel"),
    26: ("spatial_spread",      "Spatial Spread (km²)",     "Movement Kernel"),
    27: ("artifact",            "Artifact Flag",            "Movement Kernel"),
    28: ("snow_depth",          "Snow Depth (m)",           "Environment"),
    29: ("snow_density",        "Snow Density (kg/m³)",     "Environment"),
    30: ("evt_code",            "EVT Code",                 "Environment"),
    31: ("canopy_cover",        "Canopy Cover (%)",         "Environment"),
    32: ("canopy_height",       "Canopy Height (dm)",       "Environment"),
    33: ("bps_code",            "BpS Code",                 "Environment"),
    34: ("aspect_range",        "Aspect Range (°)",         "Environment"),
    35: ("habitat_quality",     "Habitat Quality",          "Environment"),
}

# Useful defaults — the variables most biologists care about
DEFAULT_SELECTED = [4, 6, 28, 29, 30, 31, 32, 33, 34, 35]


def get_variable_options() -> list[dict]:
    """Return list of {label, value, group} for UI checklist."""
    opts = []
    for col_idx, (name, label, group) in sorted(WLD_COLUMNS.items()):
        opts.append({
            "label": f"{label}  ({name})",
            "value": col_idx,
            "group": group,
        })
    return opts


def read_wld_metadata(wld_path: str | Path) -> dict:
    """Read population metadata from a .wld file without parsing fixes."""
    with zipfile.ZipFile(str(wld_path), "r") as zf:
        pop = json.loads(zf.read("population.json"))
        collar_meta = {}
        if "fixes_meta.json" in zf.namelist():
            collar_meta = json.loads(zf.read("fixes_meta.json"))
        buf = zf.read("fixes.bin")

    nc = struct.unpack("<H", buf[4:6])[0]
    cols = struct.unpack("<H", buf[6:8])[0]
    total = struct.unpack("<I", buf[8:12])[0]

    return {
        "population": pop.get("population", "Unknown"),
        "species": pop.get("species", ""),
        "n_collars": nc,
        "n_fixes": total,
        "cols_per_row": cols,
        "date_range": pop.get("date_range", []),
        "collar_meta": collar_meta,
    }


def read_wld(
    wld_path: str | Path,
    selected_columns: list[int] | None = None,
) -> pd.DataFrame:
    """
    Parse a .wld file and return a DataFrame with one row per GPS fix.

    Always includes: animal_id (serial), timestamp, lat, lon.
    Additional columns determined by selected_columns (indices into the 36-col spec).
    """
    if selected_columns is None:
        selected_columns = DEFAULT_SELECTED

    with zipfile.ZipFile(str(wld_path), "r") as zf:
        buf = zf.read("fixes.bin")
        collar_meta = {}
        if "fixes_meta.json" in zf.namelist():
            collar_meta = json.loads(zf.read("fixes_meta.json"))

    magic = buf[0:4]
    if magic != b"ELK1":
        raise ValueError(f"Invalid WLD file — expected ELK1 magic, got {magic!r}")

    nc = struct.unpack("<H", buf[4:6])[0]
    cols = struct.unpack("<H", buf[6:8])[0]
    total = struct.unpack("<I", buf[8:12])[0]

    index_start = 32
    data_start = index_start + nc * 32

    rows = []
    for i in range(nc):
        base = index_start + i * 32
        aid = struct.unpack("<I", buf[base : base + 4])[0]
        nf = struct.unpack("<I", buf[base + 4 : base + 8])[0]
        boff = struct.unpack("<Q", buf[base + 8 : base + 16])[0]

        if nf == 0:
            continue

        start = data_start + boff
        end = start + nf * cols * 8
        data = np.frombuffer(buf[start:end], dtype="<f8").reshape((nf, cols))

        serial = str(aid)
        local_id = ""
        if serial in collar_meta:
            local_id = collar_meta[serial].get("local_id", "")

        for j in range(nf):
            row = {
                "wld_serial": serial,
                "wld_local_id": local_id,
                "wld_timestamp": datetime.fromtimestamp(data[j, 0], tz=timezone.utc),
                "wld_lat": data[j, 1],
                "wld_lon": data[j, 2],
            }
            for ci in selected_columns:
                if 0 <= ci < cols:
                    col_name = WLD_COLUMNS[ci][0]
                    row[col_name] = data[j, ci]
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["wld_timestamp"] = pd.to_datetime(df["wld_timestamp"], utc=True)
    return df


def read_wld_fast(
    wld_path: str | Path,
    selected_columns: list[int] | None = None,
) -> pd.DataFrame:
    """
    Vectorized version — much faster for large WLD files.
    """
    if selected_columns is None:
        selected_columns = DEFAULT_SELECTED

    with zipfile.ZipFile(str(wld_path), "r") as zf:
        buf = zf.read("fixes.bin")
        collar_meta = {}
        if "fixes_meta.json" in zf.namelist():
            collar_meta = json.loads(zf.read("fixes_meta.json"))

    magic = buf[0:4]
    if magic != b"ELK1":
        raise ValueError(f"Invalid WLD file — expected ELK1 magic, got {magic!r}")

    nc = struct.unpack("<H", buf[4:6])[0]
    cols = struct.unpack("<H", buf[6:8])[0]
    total = struct.unpack("<I", buf[8:12])[0]

    index_start = 32
    data_start = index_start + nc * 32

    all_data = np.frombuffer(buf[data_start:], dtype="<f8").reshape((total, cols))

    serial_arr = np.empty(total, dtype=object)
    local_id_arr = np.empty(total, dtype=object)
    offset = 0
    for i in range(nc):
        base = index_start + i * 32
        aid = struct.unpack("<I", buf[base : base + 4])[0]
        nf = struct.unpack("<I", buf[base + 4 : base + 8])[0]
        serial = str(aid)
        lid = collar_meta.get(serial, {}).get("local_id", "")
        serial_arr[offset : offset + nf] = serial
        local_id_arr[offset : offset + nf] = lid
        offset += nf

    result = {
        "wld_serial": serial_arr,
        "wld_local_id": local_id_arr,
        "wld_timestamp": pd.to_datetime(all_data[:, 0], unit="s", utc=True),
        "wld_lat": all_data[:, 1],
        "wld_lon": all_data[:, 2],
    }
    for ci in selected_columns:
        if 0 <= ci < cols:
            result[WLD_COLUMNS[ci][0]] = all_data[:, ci]

    return pd.DataFrame(result)


def merge_wld_to_gps(
    gps_df: pd.DataFrame,
    wld_df: pd.DataFrame,
    gps_id_col: str = "animal_id",
    gps_ts_col: str = "timestamp",
    max_time_diff_seconds: int = 1800,
) -> pd.DataFrame:
    """
    Merge WLD variables onto GPS data by nearest timestamp match per animal.

    Matching strategy:
    1. Try matching GPS animal_id to wld_serial (tracker ID)
    2. For each matched animal, find nearest WLD fix within max_time_diff_seconds
    3. Attach selected WLD columns to the GPS row
    """
    if wld_df.empty:
        return gps_df

    var_cols = [c for c in wld_df.columns if c not in
                ("wld_serial", "wld_local_id", "wld_timestamp", "wld_lat", "wld_lon")]

    if not var_cols:
        return gps_df

    gps = gps_df.copy()
    gps[gps_ts_col] = pd.to_datetime(gps[gps_ts_col], utc=True, errors="coerce")

    for col in var_cols:
        gps[col] = np.nan

    gps_ids = gps[gps_id_col].unique()
    wld_serials = wld_df["wld_serial"].unique()

    id_map = {}
    for gid in gps_ids:
        gid_str = str(gid)
        for ws in wld_serials:
            if gid_str == ws or gid_str in ws or ws in gid_str:
                id_map[gid] = ws
                break

    for gps_id, wld_serial in id_map.items():
        gps_mask = gps[gps_id_col] == gps_id
        wld_sub = wld_df[wld_df["wld_serial"] == wld_serial].sort_values("wld_timestamp")

        if wld_sub.empty:
            continue

        gps_times = gps.loc[gps_mask, gps_ts_col].values.astype("datetime64[s]").astype(np.int64)
        wld_times = wld_sub["wld_timestamp"].values.astype("datetime64[s]").astype(np.int64)

        indices = np.searchsorted(wld_times, gps_times)
        indices = np.clip(indices, 0, len(wld_times) - 1)

        # Check neighbor to the left too
        left = np.clip(indices - 1, 0, len(wld_times) - 1)
        diff_right = np.abs(wld_times[indices] - gps_times)
        diff_left = np.abs(wld_times[left] - gps_times)
        best = np.where(diff_left < diff_right, left, indices)
        best_diff = np.minimum(diff_left, diff_right)

        within_threshold = best_diff <= max_time_diff_seconds
        matched_idx = best[within_threshold]
        gps_rows = gps.index[gps_mask][within_threshold]

        for col in var_cols:
            gps.loc[gps_rows, col] = wld_sub[col].values[matched_idx]

    return gps
