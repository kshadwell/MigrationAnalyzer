"""
sequencing.py
-------------
Automated migration sequence detection using Net Squared Displacement (NSD).

Replicates Migration Mapper App 2 (sequence definition/review) and App 3
(sequence extraction and distance calculation) logic in Python.

Background
----------
NSD plots for migratory ungulates show characteristic "humps":
  - Rising phase  → spring / outbound migration
  - Plateau       → summer (or winter) range
  - Declining phase → fall / return migration

This module auto-detects those phases, structures the results for human
review via the migtime table, and extracts GPS points per sequence.
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.signal import medfilt, find_peaks
from scipy.ndimage import uniform_filter1d
from shapely.geometry import Point


# ---------------------------------------------------------------------------
# 1. detect_migrations_nsd
# ---------------------------------------------------------------------------

def detect_migrations_nsd(
    df: pd.DataFrame,
    id_col: str = "animal_id",
    bio_year_col: str = "id_bio_year",
    nsd_col: str = "nsd_bio",
    date_col: str = "timestamp",
    displacement_col: str = "displacement_bio",
    max_sequences: int = 4,
    ensure_range_points: bool = True,
) -> pd.DataFrame:
    """
    Auto-detect migration sequences per id_bio_year using NSD changepoint analysis.

    The function:
      1. Smooths the NSD curve with a rolling median (window ≈ 7 days based on
         estimated fix rate).
      2. Computes the first derivative of the smoothed NSD.
      3. Identifies sustained positive (outbound) and negative (return) derivative
         periods as candidate migration windows.
      4. Scores each candidate by NSD amplitude and derivative consistency.

    Parameters
    ----------
    df : pd.DataFrame
        Full GPS/NSD dataset.  Must contain *id_col*, *bio_year_col*, *nsd_col*,
        *date_col*, and optionally *displacement_col*.
    id_col : str
        Column identifying individual animals.
    bio_year_col : str
        Column identifying biological year group (e.g. "A001_2023").
    nsd_col : str
        Column containing Net Squared Displacement values (m²).
    date_col : str
        Column containing fix timestamps (datetime-like).
    displacement_col : str
        Column containing straight-line displacement from capture site (m).

    Returns
    -------
    pd.DataFrame
        One row per detected migration window with columns:
        ``id_bio_year``, ``animal_id``, ``sequence_name``, ``start_date``,
        ``end_date``, ``migration_type``, ``confidence``.
    """
    required = {id_col, bio_year_col, nsd_col, date_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"detect_migrations_nsd: missing columns {missing}")

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values([bio_year_col, date_col])

    records: list[dict] = []

    for bio_year, grp in df.groupby(bio_year_col, sort=False):
        grp = grp.dropna(subset=[nsd_col]).copy()
        if len(grp) < 10:
            continue

        animal_id = grp[id_col].iloc[0]
        dates = grp[date_col].values
        nsd = grp[nsd_col].values.astype(float)

        # --- estimate fix rate in fixes/day ---------------------------------
        n_days = max(
            1,
            (grp[date_col].max() - grp[date_col].min()).days,
        )
        fixes_per_day = max(1, len(grp) / n_days)

        # window ≈ 7 calendar days worth of fixes, must be odd
        window = max(3, int(round(7 * fixes_per_day)))
        if window % 2 == 0:
            window += 1

        # --- smooth NSD with rolling median ---------------------------------
        smoothed = _rolling_median(nsd, window)

        # --- first derivative (fixes/unit) ----------------------------------
        deriv = np.gradient(smoothed)

        # --- find sustained rise/fall segments ------------------------------
        segs = _find_sustained_segments(deriv, smoothed, dates, fixes_per_day)

        # --- rank by most dramatic NSD change, keep top max_sequences ------
        nsd_range = np.ptp(smoothed) if np.ptp(smoothed) > 0 else 1.0
        for seg in segs:
            seg["_amplitude"] = seg["nsd_delta"] / nsd_range
            expected_sign = 1 if seg["migration_type"] == "outbound" else -1
            seg["_consistency"] = float(
                np.mean(np.sign(deriv[seg["slice"]]) == expected_sign)
            )
            seg["_score"] = 0.6 * seg["_amplitude"] + 0.4 * seg["_consistency"]

        segs.sort(key=lambda s: s["_score"], reverse=True)
        segs = segs[:max_sequences]
        segs.sort(key=lambda s: s["start_date"])

        # --- ensure start/end range points are captured --------------------
        if ensure_range_points:
            x_vals = grp["x"].values if "x" in grp.columns else None
            y_vals = grp["y"].values if "y" in grp.columns else None
            for seg in segs:
                sl = seg["slice"]
                seg_start_idx = sl.start
                seg_end_idx = sl.stop - 1

                if x_vals is not None and len(x_vals) > 0:
                    start_x, start_y = x_vals[seg_start_idx], y_vals[seg_start_idx]
                    end_x, end_y = x_vals[seg_end_idx], y_vals[seg_end_idx]

                    start_ref_x = np.mean(x_vals[max(0, seg_start_idx - 5):seg_start_idx + 1])
                    start_ref_y = np.mean(y_vals[max(0, seg_start_idx - 5):seg_start_idx + 1])
                    end_ref_x = np.mean(x_vals[seg_end_idx:min(len(x_vals), seg_end_idx + 6)])
                    end_ref_y = np.mean(y_vals[seg_end_idx:min(len(y_vals), seg_end_idx + 6)])

                    start_dist = np.sqrt((start_x - start_ref_x)**2 + (start_y - start_ref_y)**2)
                    end_dist = np.sqrt((end_x - end_ref_x)**2 + (end_y - end_ref_y)**2)

                    if start_dist > 5000 and seg_start_idx > 0:
                        new_start = max(0, seg_start_idx - int(2 * fixes_per_day))
                        seg["slice"] = slice(new_start, sl.stop)
                        seg["start_date"] = dates[new_start]

                    if end_dist > 5000 and seg_end_idx < len(dates) - 1:
                        new_end = min(len(dates) - 1, seg_end_idx + int(2 * fixes_per_day))
                        seg["slice"] = slice(seg["slice"].start, new_end + 1)
                        seg["end_date"] = dates[new_end]

        # --- label: mig1, mig2, ... (user renames in UI) -------------------
        for idx, seg in enumerate(segs):
            seq_name = f"mig{idx + 1}"
            confidence = round(seg["_score"], 3)

            records.append(
                {
                    "id_bio_year": bio_year,
                    "animal_id": animal_id,
                    "sequence_name": seq_name,
                    "start_date": pd.Timestamp(seg["start_date"]),
                    "end_date": pd.Timestamp(seg["end_date"]),
                    "migration_type": seg["migration_type"],
                    "confidence": confidence,
                }
            )

    if not records:
        return pd.DataFrame(
            columns=[
                "id_bio_year",
                "animal_id",
                "sequence_name",
                "start_date",
                "end_date",
                "migration_type",
                "confidence",
            ]
        )

    result = pd.DataFrame(records)
    result = result.sort_values(["id_bio_year", "start_date"]).reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# 2. build_migtime_table
# ---------------------------------------------------------------------------

def build_migtime_table(
    df: pd.DataFrame,
    bio_year_col: str = "id_bio_year",
    animal_id_col: str = "animal_id",
    bio_year_full_col: str = "bio_year_full",
    num_sequences: int = 4,
    sequence_names: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Build the migtime table — one row per id_bio_year.

    Columns produced:
      ``id_bio_year``, ``animal_id``, ``bio_year``, ``bio_year_full``,
      ``mig1_start`` … ``mig{N}_start``, ``mig1_end`` … ``mig{N}_end``,
      ``notes``, ``auto_detected``, ``reviewed``.

    Up to 8 migration slots are supported; *num_sequences* controls how many
    are pre-populated (columns for all 8 are always present for schema
    consistency).

    Parameters
    ----------
    df : pd.DataFrame
        Dataset containing at minimum *bio_year_col* and *animal_id_col*.
        If *bio_year_full_col* is absent it is derived from *bio_year_col*.
    bio_year_col : str
        Column identifying the biological year group.
    animal_id_col : str
        Column identifying individual animals.
    bio_year_full_col : str
        Column with the human-readable biological year string.
    num_sequences : int
        Number of migration sequences expected (1–8).  Defaults to 2
        (spring + fall).
    sequence_names : list[str] or None
        Optional labels for each sequence slot.  Length must equal
        *num_sequences* if provided.

    Returns
    -------
    pd.DataFrame
        Empty migtime table ready to be filled by :func:`apply_auto_detections`.
    """
    if num_sequences < 1 or num_sequences > 8:
        raise ValueError("num_sequences must be between 1 and 8.")
    if sequence_names is not None and len(sequence_names) != num_sequences:
        raise ValueError(
            f"sequence_names length ({len(sequence_names)}) must match "
            f"num_sequences ({num_sequences})."
        )

    # unique id_bio_year rows
    key_cols = [bio_year_col, animal_id_col]
    if bio_year_full_col in df.columns:
        key_cols.append(bio_year_full_col)

    base = (
        df[key_cols]
        .drop_duplicates(subset=[bio_year_col])
        .sort_values(bio_year_col)
        .reset_index(drop=True)
        .copy()
    )

    # derive bio_year from id_bio_year if not present
    if bio_year_full_col not in df.columns:
        # assume format "ANIMAL_BIOYEAR" — take the last token after "_"
        base["bio_year"] = base[bio_year_col].astype(str).apply(
            lambda v: v.rsplit("_", 1)[-1] if "_" in str(v) else v
        )
        base[bio_year_full_col] = base["bio_year"]
    else:
        base["bio_year"] = base[bio_year_full_col]

    # rename to standard schema
    base = base.rename(
        columns={bio_year_col: "id_bio_year", animal_id_col: "animal_id"}
    )
    if bio_year_full_col != "bio_year_full":
        base = base.rename(columns={bio_year_full_col: "bio_year_full"})

    # ensure column order
    base = base[["id_bio_year", "animal_id", "bio_year", "bio_year_full"]]

    # add mig date columns (always 8 slots for schema consistency)
    for i in range(1, 9):
        base[f"mig{i}_start"] = pd.NaT
        base[f"mig{i}_end"] = pd.NaT

    base["notes"] = ""
    base["auto_detected"] = False
    base["reviewed"] = False

    # store metadata as attributes (informational only)
    base.attrs["num_sequences"] = num_sequences
    default_names = ["mig1", "mig2", "mig3", "mig4", "mig5", "mig6", "mig7", "mig8"]
    base.attrs["sequence_names"] = sequence_names or default_names[:num_sequences]

    return base


# ---------------------------------------------------------------------------
# 3. apply_auto_detections
# ---------------------------------------------------------------------------

def apply_auto_detections(
    migtime_df: pd.DataFrame,
    detections_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Fill the migtime table with auto-detected migration start/end dates.

    Detected sequences are ordered by start_date per id_bio_year and mapped to
    mig1, mig2, … slots (up to 8).  The ``auto_detected`` flag is set to True
    for any row that receives at least one date.

    Parameters
    ----------
    migtime_df : pd.DataFrame
        Output of :func:`build_migtime_table`.
    detections_df : pd.DataFrame
        Output of :func:`detect_migrations_nsd`.

    Returns
    -------
    pd.DataFrame
        Updated migtime table (copy — original is not modified).
    """
    migtime = migtime_df.copy()
    det = detections_df.sort_values(["id_bio_year", "start_date"]).copy()

    for bio_year, grp in det.groupby("id_bio_year", sort=False):
        mask = migtime["id_bio_year"] == bio_year
        if not mask.any():
            warnings.warn(
                f"apply_auto_detections: id_bio_year '{bio_year}' not found in "
                "migtime_df; skipping."
            )
            continue

        idx = migtime.index[mask][0]
        for slot, (_, row) in enumerate(grp.iterrows(), start=1):
            if slot > 8:
                break
            migtime.at[idx, f"mig{slot}_start"] = row["start_date"]
            migtime.at[idx, f"mig{slot}_end"] = row["end_date"]

        migtime.at[idx, "auto_detected"] = True

    return migtime


# ---------------------------------------------------------------------------
# 4. extract_sequences
# ---------------------------------------------------------------------------

def extract_sequences(
    df: pd.DataFrame,
    migtime_df: pd.DataFrame,
    sequence_names: List[str],
    date_col: str = "timestamp",
    id_col: str = "animal_id",
) -> Dict[str, gpd.GeoDataFrame]:
    """
    Extract GPS points for each defined migration sequence.

    Points are filtered to the date windows defined in *migtime_df*.
    Problem / mortality-flagged points are dropped if a ``flag`` column is
    present (values of ``'problem'`` or ``'mortality'`` are excluded).

    The ``mig`` key follows the convention ``{animal_id}_{bio_year}_{season}``.

    Parameters
    ----------
    df : pd.DataFrame
        Full GPS dataset.  Must contain *date_col*, *id_col*, ``lon``, ``lat``,
        ``x``, ``y``, and ``id_bio_year`` columns.
    migtime_df : pd.DataFrame
        Reviewed (or auto-filled) migtime table from :func:`build_migtime_table`.
    sequence_names : list[str]
        Ordered list of sequence labels matching mig1, mig2, … slots.
        E.g. ``['Spring', 'Fall']``.
    date_col : str
        Timestamp column in *df*.
    id_col : str
        Animal ID column in *df*.

    Returns
    -------
    dict[str, GeoDataFrame]
        Keys are sequence names; values are GeoDataFrames with columns:
        ``id``, ``date``, ``mig``, ``lon``, ``lat``, ``x``, ``y``,
        ``geometry`` (Point from lon/lat).
    """
    required_df = {date_col, id_col, "id_bio_year"}
    missing = required_df - set(df.columns)
    if missing:
        raise ValueError(f"extract_sequences: df missing columns {missing}")

    for coord in ("lon", "lat"):
        if coord not in df.columns:
            raise ValueError(
                f"extract_sequences: df missing coordinate column '{coord}'."
            )

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])

    # Drop flagged points so each sequence reads A→C with point B excised
    # when B is a problem/mortality fix. (Legacy "flag" string column still
    # supported in case any caller pre-stages flags that way.)
    if "problem" in df.columns:
        df = df[df["problem"].fillna(0).astype(int) == 0]
    if "mortality_flag" in df.columns:
        df = df[df["mortality_flag"].fillna(0).astype(int) == 0]
    if "flag" in df.columns:
        df = df[~df["flag"].astype(str).str.lower().isin({"problem", "mortality"})]

    # ensure x/y exist (project from lon/lat if absent)
    if "x" not in df.columns:
        df["x"] = df["lon"]
    if "y" not in df.columns:
        df["y"] = df["lat"]

    results: Dict[str, gpd.GeoDataFrame] = {}

    for seq_idx, seq_name in enumerate(sequence_names, start=1):
        start_col = f"mig{seq_idx}_start"
        end_col = f"mig{seq_idx}_end"

        if start_col not in migtime_df.columns or end_col not in migtime_df.columns:
            warnings.warn(
                f"extract_sequences: columns '{start_col}'/'{end_col}' not found "
                "in migtime_df; skipping sequence."
            )
            continue

        frames: list[pd.DataFrame] = []

        for _, mrow in migtime_df.iterrows():
            bio_year = mrow["id_bio_year"]
            start = mrow[start_col]
            end = mrow[end_col]

            if pd.isnull(start) or pd.isnull(end):
                continue

            start = pd.Timestamp(start)
            end = pd.Timestamp(end)

            subset = df[
                (df["id_bio_year"] == bio_year)
                & (df[date_col] >= start)
                & (df[date_col] <= end)
            ].copy()

            if subset.empty:
                continue

            # derive bio_year label from id_bio_year
            bio_yr_label = (
                str(mrow.get("bio_year", bio_year))
            )
            animal = str(mrow["animal_id"])
            mig_key = f"{animal}_{bio_yr_label}_{seq_name}"

            subset = subset.rename(columns={id_col: "id", date_col: "date"})
            subset["mig"] = mig_key
            frames.append(subset[["id", "date", "mig", "lon", "lat", "x", "y"]])

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            gdf = gpd.GeoDataFrame(
                combined,
                geometry=gpd.points_from_xy(combined["lon"], combined["lat"]),
                crs="EPSG:4326",
            )
        else:
            gdf = gpd.GeoDataFrame(
                columns=["id", "date", "mig", "lon", "lat", "x", "y", "geometry"],
                geometry="geometry",
                crs="EPSG:4326",
            )

        results[seq_name] = gdf

    return results


# ---------------------------------------------------------------------------
# 5. calc_sequence_distances
# ---------------------------------------------------------------------------

def calc_sequence_distances(
    seq_gdf: gpd.GeoDataFrame,
    id_col: str = "mig",
) -> pd.DataFrame:
    """
    Compute total cumulative path distance per migration sequence.

    Distances are calculated from projected coordinates (columns ``x``, ``y``
    in metres) if available; otherwise the function falls back to haversine
    distances from ``lon``/``lat``.

    Parameters
    ----------
    seq_gdf : GeoDataFrame
        Output from :func:`extract_sequences` for a single sequence (or a
        concatenation of multiple).
    id_col : str
        Column used to group fixes into individual migration tracks.

    Returns
    -------
    pd.DataFrame
        Columns: ``mig``, ``total_distance_km``, ``start_date``, ``end_date``,
        ``duration_days``.
    """
    if seq_gdf.empty:
        return pd.DataFrame(
            columns=["mig", "total_distance_km", "start_date", "end_date", "duration_days"]
        )

    use_projected = "x" in seq_gdf.columns and "y" in seq_gdf.columns

    records: list[dict] = []

    for mig_id, grp in seq_gdf.groupby(id_col, sort=False):
        grp = grp.sort_values("date").reset_index(drop=True)
        if len(grp) < 2:
            dist_km = 0.0
        elif use_projected:
            dx = np.diff(grp["x"].values.astype(float))
            dy = np.diff(grp["y"].values.astype(float))
            dist_km = float(np.sum(np.sqrt(dx**2 + dy**2))) / 1000.0
        else:
            dist_km = _haversine_path_km(
                grp["lat"].values.astype(float),
                grp["lon"].values.astype(float),
            )

        start_dt = grp["date"].min()
        end_dt = grp["date"].max()
        duration = max(0, (end_dt - start_dt).days)

        records.append(
            {
                "mig": mig_id,
                "total_distance_km": round(dist_km, 3),
                "start_date": start_dt,
                "end_date": end_dt,
                "duration_days": duration,
            }
        )

    return pd.DataFrame(records).sort_values("mig").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 6. get_nsd_plot_data
# ---------------------------------------------------------------------------

def get_nsd_plot_data(
    df: pd.DataFrame,
    id_bio_year: str,
    date_col: str = "timestamp",
    nsd_col: str = "nsd_bio",
    displacement_col: str = "displacement_bio",
    speed_col: str = "speed",
    migtime_df: Optional[pd.DataFrame] = None,
) -> dict:
    """
    Extract plot data for a single id_bio_year for the review UI.

    Optionally includes shading regions derived from *migtime_df*.

    Parameters
    ----------
    df : pd.DataFrame
        Full GPS/NSD dataset.
    id_bio_year : str
        The biological year group key to extract.
    date_col : str
        Timestamp column.
    nsd_col : str
        NSD column.
    displacement_col : str
        Displacement column.
    speed_col : str
        Speed column (m/s or km/h — units are passed through as-is).
    migtime_df : pd.DataFrame or None
        Optional migtime table.  If provided, sequence shading regions are
        derived from the row matching *id_bio_year*.

    Returns
    -------
    dict
        Keys:
          ``dates``          – list of pd.Timestamp
          ``nsd``            – np.ndarray (float)
          ``nsd_smoothed``   – np.ndarray (float), 7-day rolling median
          ``displacement``   – np.ndarray (float) or None
          ``speed``          – np.ndarray (float) or None
          ``shading_regions``– list of dicts with keys
                               ``label``, ``start``, ``end``, ``color``
          ``id_bio_year``    – str (echoed back)
          ``n_fixes``        – int
    """
    grp = df[df["id_bio_year"] == id_bio_year].copy()
    if grp.empty:
        raise ValueError(f"get_nsd_plot_data: id_bio_year '{id_bio_year}' not found.")

    grp[date_col] = pd.to_datetime(grp[date_col])
    grp = grp.sort_values(date_col).reset_index(drop=True)
    grp = grp.dropna(subset=[nsd_col])

    dates: list[pd.Timestamp] = grp[date_col].tolist()
    nsd = grp[nsd_col].values.astype(float)

    # smooth
    n = len(nsd)
    n_days = max(1, (grp[date_col].max() - grp[date_col].min()).days)
    fixes_per_day = max(1, n / n_days)
    window = max(3, int(round(7 * fixes_per_day)))
    if window % 2 == 0:
        window += 1
    nsd_smoothed = _rolling_median(nsd, window)

    displacement = (
        grp[displacement_col].values.astype(float)
        if displacement_col in grp.columns
        else None
    )
    speed = (
        grp[speed_col].values.astype(float)
        if speed_col in grp.columns
        else None
    )

    # shading regions
    shading_regions: list[dict] = []
    _COLORS = [
        "#4CAF50",  # green – spring
        "#FF9800",  # orange – fall
        "#2196F3",  # blue – extra
        "#9C27B0",  # purple
        "#F44336",  # red
        "#00BCD4",  # cyan
        "#8BC34A",  # light green
        "#FF5722",  # deep orange
    ]
    if migtime_df is not None and not migtime_df.empty:
        mrow = migtime_df[migtime_df["id_bio_year"] == id_bio_year]
        if not mrow.empty:
            mrow = mrow.iloc[0]
            for i in range(1, 9):
                sc = f"mig{i}_start"
                ec = f"mig{i}_end"
                if sc not in mrow.index or pd.isnull(mrow[sc]):
                    continue
                shading_regions.append(
                    {
                        "label": f"mig{i}",
                        "start": pd.Timestamp(mrow[sc]),
                        "end": pd.Timestamp(mrow[ec]),
                        "color": _COLORS[(i - 1) % len(_COLORS)],
                    }
                )

    return {
        "id_bio_year": id_bio_year,
        "n_fixes": len(dates),
        "dates": dates,
        "nsd": nsd,
        "nsd_smoothed": nsd_smoothed,
        "displacement": displacement,
        "speed": speed,
        "shading_regions": shading_regions,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _rolling_median(arr: np.ndarray, window: int) -> np.ndarray:
    """Apply a rolling median to *arr* with edge padding."""
    # scipy medfilt handles odd kernel sizes and pads with zeros at edges.
    # We override edge behaviour by reflecting the array.
    pad = window // 2
    padded = np.pad(arr, pad, mode="reflect")
    smoothed = medfilt(padded, kernel_size=window)
    return smoothed[pad : pad + len(arr)]


def _find_sustained_segments(
    deriv: np.ndarray,
    smoothed: np.ndarray,
    dates: np.ndarray,
    fixes_per_day: float,
    min_duration_days: float = 5.0,
    min_nsd_delta_frac: float = 0.05,
) -> list[dict]:
    """
    Identify sustained positive and negative derivative segments.

    A segment is retained when:
      - Its duration exceeds *min_duration_days* of fixes.
      - The NSD change across the segment is at least *min_nsd_delta_frac*
        of the total NSD range.

    Returns a list of dicts with keys:
      ``migration_type``, ``start_date``, ``end_date``, ``nsd_delta``, ``slice``.
    """
    min_fixes = max(3, int(round(min_duration_days * fixes_per_day)))
    nsd_range = np.ptp(smoothed)
    min_delta = min_nsd_delta_frac * nsd_range

    segments: list[dict] = []

    for sign, mig_type in [(1, "outbound"), (-1, "return")]:
        binary = (np.sign(deriv) == sign).astype(int)
        runs = _rle(binary)

        pos = 0
        for length, val in runs:
            if val == 1 and length >= min_fixes:
                sl = slice(pos, pos + length)
                seg_nsd = smoothed[sl]
                delta = abs(seg_nsd[-1] - seg_nsd[0])
                if delta >= min_delta:
                    segments.append(
                        {
                            "migration_type": mig_type,
                            "start_date": dates[pos],
                            "end_date": dates[pos + length - 1],
                            "nsd_delta": delta,
                            "slice": sl,
                        }
                    )
            pos += length

    # sort by start date
    segments.sort(key=lambda s: s["start_date"])

    # merge overlapping / adjacent same-type segments
    merged = _merge_segments(segments, smoothed, dates)
    return merged


def _rle(arr: np.ndarray) -> list[Tuple[int, int]]:
    """Run-length encode a binary array. Returns list of (length, value)."""
    if len(arr) == 0:
        return []
    runs: list[Tuple[int, int]] = []
    current = arr[0]
    count = 1
    for v in arr[1:]:
        if v == current:
            count += 1
        else:
            runs.append((count, int(current)))
            current = v
            count = 1
    runs.append((count, int(current)))
    return runs


def _merge_segments(
    segments: list[dict],
    smoothed: np.ndarray,
    dates: np.ndarray,
) -> list[dict]:
    """
    Merge consecutive same-type segments that are separated by a gap of less
    than 20% of the shorter segment's length.
    """
    if not segments:
        return []

    merged = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        if seg["migration_type"] != prev["migration_type"]:
            merged.append(seg)
            continue

        gap = seg["slice"].start - prev["slice"].stop
        tolerance = 0.2 * min(
            prev["slice"].stop - prev["slice"].start,
            seg["slice"].stop - seg["slice"].start,
        )
        if gap <= tolerance:
            new_sl = slice(prev["slice"].start, seg["slice"].stop)
            new_delta = abs(
                smoothed[new_sl.stop - 1] - smoothed[new_sl.start]
            )
            merged[-1] = {
                "migration_type": prev["migration_type"],
                "start_date": prev["start_date"],
                "end_date": seg["end_date"],
                "nsd_delta": new_delta,
                "slice": new_sl,
            }
        else:
            merged.append(seg)

    return merged


def _haversine_path_km(lats: np.ndarray, lons: np.ndarray) -> float:
    """
    Compute cumulative great-circle path distance in km.

    Parameters
    ----------
    lats, lons : np.ndarray
        Latitude and longitude arrays in decimal degrees (WGS-84), ordered
        chronologically.
    """
    R = 6371.0  # Earth radius in km
    lat1 = np.radians(lats[:-1])
    lat2 = np.radians(lats[1:])
    dlat = lat2 - lat1
    dlon = np.radians(lons[1:] - lons[:-1])

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return float(np.sum(R * c))
