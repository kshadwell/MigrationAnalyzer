"""
population_outputs.py
---------------------
Merges individual utilization distributions (UDs) and movement footprints into
population-level products, replicating Migration Mapper App 5 behaviour.
Also handles export with explanatory documentation.
"""

from __future__ import annotations

import os
import csv
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
# (scipy.ndimage.gaussian_filter was used to blur the surface before
# contouring; replaced by ksmooth outline smoothing in _smooth_ksmooth.)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rasterize_polygon(polygon, transform, shape_out):
    """Rasterize a single shapely polygon onto a grid defined by transform/shape."""
    from rasterio.features import rasterize as rio_rasterize
    burned = rio_rasterize(
        [(mapping(polygon), 1)],
        out_shape=shape_out,
        transform=transform,
        fill=0,
        dtype="uint8",
    )
    return burned.astype(np.float32)


def _polygonize_mask(mask: np.ndarray, transform) -> list:
    """Convert a boolean 2-D mask to a list of shapely geometries."""
    from rasterio.features import shapes as rio_shapes
    polys = []
    for geom, val in rio_shapes(mask.astype(np.uint8), transform=transform):
        if val == 1:
            polys.append(shape(geom))
    return polys


def _contours_from_grid(
    grid: np.ndarray,
    transform,
    levels: list[float],
    min_area_drop: float,
    min_area_fill: float,
    simplify: bool,
    smoothness: float,
) -> list[dict]:
    """
    Given a 2-D proportion grid (values 0–100) and contour levels,
    return a list of dicts {contour, geometry} where geometry is the
    union of polygons covering cells >= level.

    Pipeline mirrors Migration Mapper's CalcPopUse / CalcPopFootprint:
    contour the raw grid (NO pre-blur of the surface), drop polygons smaller
    than ``min_area_drop`` m², fill holes smaller than ``min_area_fill`` m²,
    then — when ``simplify`` is on — smooth the polygon outlines with the
    ``smoothr::smooth(method="ksmooth")`` port (see :func:`_smooth_ksmooth`),
    where ``smoothness`` matches R's ``ksmooth_smoothness``. Smoothing the
    outlines (rather than blurring the source grid) keeps contour areas and
    positions directly comparable to the R outputs.
    """
    rows = []
    for level in sorted(levels, reverse=True):
        mask = (grid >= level).astype(np.uint8)
        polys = _polygonize_mask(mask, transform)
        if not polys:
            rows.append({"contour": level, "geometry": None})
            continue

        merged = unary_union(polys)

        # Drop small polygons
        if merged.geom_type == "MultiPolygon":
            kept = [p for p in merged.geoms if p.area >= min_area_drop]
            merged = unary_union(kept) if kept else merged
        elif merged.area < min_area_drop:
            rows.append({"contour": level, "geometry": None})
            continue

        # Fill small holes
        merged = _fill_holes(merged, min_area_fill)

        # Smooth the outlines (ksmooth) — only when simplify is on.
        if simplify and smoothness and smoothness > 0:
            merged = _smooth_ksmooth(merged, smoothness)

        rows.append({"contour": level, "geometry": merged})

    return rows


def _fill_holes(geom, min_fill_area: float):
    """Remove interior rings (holes) smaller than min_fill_area from a geometry."""
    from shapely.geometry import Polygon, MultiPolygon

    def _fix_polygon(poly: Polygon) -> Polygon:
        exterior = poly.exterior
        kept_interiors = [
            ring for ring in poly.interiors
            if Polygon(ring).area >= min_fill_area
        ]
        return Polygon(exterior, kept_interiors)

    if geom.geom_type == "Polygon":
        return _fix_polygon(geom)
    elif geom.geom_type == "MultiPolygon":
        return MultiPolygon([_fix_polygon(p) for p in geom.geoms])
    return geom


def _smooth_ksmooth(geom, smoothness: float):
    """Smooth polygon *outlines* with Gaussian kernel regression — a port of
    R ``smoothr::smooth(method="ksmooth")`` (Migration Mapper's CalcPopUse /
    CalcPopFootprint smoothing step).

    Each ring is parameterised by cumulative arc length (circularly, since the
    rings are closed) and every densified vertex is replaced by the
    Gaussian-weighted average of its neighbours along the boundary. Bandwidth =
    ``smoothness * mean(original segment length)``; the kernel sd is scaled like
    R's ``stats::ksmooth`` normal kernel (sd = 0.3706506 * bandwidth). This
    de-pixelates the staircase contour edges while preserving each contour's
    area and position — unlike blurring the source grid, which moves the
    contours and changes their areas.
    """
    from shapely.geometry import Polygon, MultiPolygon

    def _smooth_ring(coords):
        pts = np.asarray(coords, dtype=float)
        if len(pts) >= 2 and np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        m = len(pts)
        if m < 4:
            return None
        seg = np.hypot(*(np.roll(pts, -1, axis=0) - pts).T)
        mean_seg = float(seg.mean())
        if mean_seg <= 0:
            return None
        sd = 0.3706506 * float(smoothness) * mean_seg
        if sd <= 0:
            return None
        # Densify each original segment into ~nd pieces so the kernel has
        # resolution to work with; keep the total bounded for speed/memory.
        nd = max(1, min(8, int(np.ceil(2500 / max(m, 1)))))
        a = np.arange(nd) / nd
        nxt = np.roll(pts, -1, axis=0)
        dens = (pts[:, None, :] + a[None, :, None] * (nxt - pts)[:, None, :]).reshape(-1, 2)
        M = len(dens)
        dd = np.hypot(*(np.roll(dens, -1, axis=0) - dens).T)
        total = float(dd.sum())
        if total <= 0:
            return None
        t = np.concatenate([[0.0], np.cumsum(dd)[:-1]])
        # Windowed circular Gaussian regression: only neighbours within a few sd
        # along the boundary carry weight, so we sweep a bounded index window
        # rather than forming an MxM matrix.
        dd_pos = dd[dd > 0]
        min_dt = float(dd_pos.min()) if dd_pos.size else (total / M)
        W = int(np.ceil(4.0 * sd / max(min_dt, 1e-9)))
        W = max(2, min(W, M // 2, 400))
        idx = np.arange(M)
        acc_x = np.zeros(M)
        acc_y = np.zeros(M)
        acc_w = np.zeros(M)
        for off in range(-W, W + 1):
            j = (idx + off) % M
            dt = np.abs(t[j] - t)
            dt = np.minimum(dt, total - dt)
            w = np.exp(-0.5 * (dt / sd) ** 2)
            acc_x += w * dens[j, 0]
            acc_y += w * dens[j, 1]
            acc_w += w
        sx = acc_x / acc_w
        sy = acc_y / acc_w
        out = np.column_stack([sx, sy])
        return np.vstack([out, out[0]])  # re-close the ring

    def _smooth_polygon(poly):
        ext = _smooth_ring(np.asarray(poly.exterior.coords))
        if ext is None:
            return poly
        holes = []
        for ring in poly.interiors:
            h = _smooth_ring(np.asarray(ring.coords))
            if h is not None:
                holes.append(h)
        try:
            sp = Polygon(ext, holes)
            if not sp.is_valid:
                sp = sp.buffer(0)
            return sp if (sp and not sp.is_empty and sp.is_valid) else poly
        except Exception:
            return poly

    try:
        if geom.geom_type == "Polygon":
            return _smooth_polygon(geom)
        if geom.geom_type == "MultiPolygon":
            parts = [_smooth_polygon(p) for p in geom.geoms]
            parts = [p for p in parts if p is not None and not p.is_empty]
            return MultiPolygon(parts) if parts else geom
    except Exception:
        return geom
    return geom


def _grid_meta_from_arrays(arrays: list[np.ndarray], src_crs) -> dict:
    """
    Placeholder: in production the caller should pass grid_meta with
    transform and crs.  This helper just returns a minimal stub so that
    functions work even without explicit grid_meta.
    """
    raise ValueError(
        "grid_meta must be provided explicitly (keys: 'transform', 'crs', 'shape')."
    )


def _build_geodataframe(rows: list[dict], src_crs, out_crs) -> gpd.GeoDataFrame:
    """Build a GeoDataFrame from contour rows, reproject if needed, add area_km2."""
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=src_crs)
    gdf = gdf[gdf.geometry.notna()].reset_index(drop=True)

    if out_crs is not None:
        target = CRS.from_user_input(out_crs)
        if gdf.crs != target:
            gdf = gdf.to_crs(target)

    # area in km²
    # Use equal-area projection for area calc if CRS is geographic
    if gdf.crs and gdf.crs.is_geographic:
        area_gdf = gdf.to_crs("ESRI:54009")
    else:
        area_gdf = gdf
    gdf["area_km2"] = area_gdf.geometry.area / 1e6

    return gdf[["contour", "geometry", "area_km2"]]


# ---------------------------------------------------------------------------
# 1. Population use (UD-based)
# ---------------------------------------------------------------------------

def calc_population_use(
    ud_dict: dict[str, np.ndarray],
    grid_meta: dict,
    merge_order: list[str] = ("id", "year"),
    contour_type: str = "Area",
    contour_levels: list[float] = (5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90),
    min_area_drop: float = 20_000,
    min_area_fill: float = 20_000,
    simplify: bool = True,
    smooth_bandwidth: float = 2,
    out_crs=None,
) -> gpd.GeoDataFrame:
    """
    Merge individual UD rasters into a population-level use surface and
    contour at the requested levels.

    Parameters
    ----------
    ud_dict : dict
        Mapping of migration name → 2-D numpy array (UD values, not yet
        normalised to sum-to-1; function normalises internally).
        Keys can encode individual and year, e.g. ``"elk01_2022"``.
    grid_meta : dict
        Must contain ``'transform'`` (affine), ``'crs'``, and ``'shape'``
        (rows, cols).
    merge_order : sequence of str
        Two-element list/tuple with ``'id'`` and ``'year'`` in desired order.
        - ``['id', 'year']``: average each individual across years first,
          then average across individuals.
        - ``['year', 'id']``: average each year across individuals first,
          then average across years.
    contour_type : str
        ``'Area'``  – contour level = % of individuals whose UD > 0 at cell.
        ``'Volume'`` – contour level = % of total UD volume.
    contour_levels : list of float
        Contour percentage levels (e.g. 50 → 50 % isopleths).
    min_area_drop : float
        Minimum polygon area in CRS units (metres² if projected).
        Polygons smaller than this are removed.
    min_area_fill : float
        Holes smaller than this area are filled.
    simplify : bool
        Apply Gaussian smoothing before contouring.
    smooth_bandwidth : float
        Standard deviation (cells) for Gaussian kernel.
    out_crs : optional
        Output CRS for the GeoDataFrame (any format accepted by
        ``CRS.from_user_input``).  Defaults to ``grid_meta['crs']``.

    Returns
    -------
    GeoDataFrame
        Columns: ``contour``, ``geometry``, ``area_km2``.
    """
    transform = grid_meta["transform"]
    src_crs = CRS.from_user_input(grid_meta["crs"])
    shape_rc = grid_meta["shape"]  # (rows, cols)

    # ------------------------------------------------------------------
    # Parse keys into (individual_id, year) pairs
    # Keys are expected as "<id>_<year>" or just "<id>" if no year info.
    # ------------------------------------------------------------------
    parsed: dict[tuple[str, str], np.ndarray] = {}
    for key, arr in ud_dict.items():
        parts = key.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            ind_id, year = parts[0], parts[1]
        else:
            ind_id, year = key, "all"
        parsed[(ind_id, year)] = arr.astype(np.float32)

    # ------------------------------------------------------------------
    # Merge according to merge_order
    # ------------------------------------------------------------------
    ids = sorted({k[0] for k in parsed})
    years = sorted({k[1] for k in parsed})

    if list(merge_order)[0] == "id":
        # Step 1: average each individual across years
        per_id: dict[str, np.ndarray] = {}
        for ind_id in ids:
            stacked = np.stack(
                [parsed[(ind_id, yr)] for yr in years if (ind_id, yr) in parsed],
                axis=0,
            )
            per_id[ind_id] = stacked.mean(axis=0)
        # Step 2: stack across individuals
        stack = np.stack(list(per_id.values()), axis=0)
    else:
        # Step 1: average each year across individuals
        per_year: dict[str, np.ndarray] = {}
        for yr in years:
            stacked = np.stack(
                [parsed[(ind_id, yr)] for ind_id in ids if (ind_id, yr) in parsed],
                axis=0,
            )
            per_year[yr] = stacked.mean(axis=0)
        # Step 2: stack across years
        stack = np.stack(list(per_year.values()), axis=0)

    n_layers = stack.shape[0]

    # ------------------------------------------------------------------
    # Build proportion grid
    # ------------------------------------------------------------------
    if contour_type == "Area":
        # Proportion of layers with UD > 0 at each cell × 100
        presence = (stack > 0).sum(axis=0) / n_layers * 100.0
        prop_grid = presence
    elif contour_type == "Volume":
        # Normalise each layer to sum-to-1 in-place, then accumulate into a
        # 2-D sum to avoid allocating a second full 3-D array.
        stack = stack.astype(np.float32, copy=False)
        summed = np.zeros(stack.shape[1:], dtype=np.float64)
        for i in range(n_layers):
            total = stack[i].sum()
            if total > 0:
                stack[i] /= total
            summed += stack[i]
        # cumulative volume from highest to lowest
        flat = summed.ravel()
        order = np.argsort(flat)[::-1]
        cumsum = np.cumsum(flat[order])
        rank = np.empty_like(cumsum)
        rank[order] = cumsum
        prop_grid = (1.0 - rank.reshape(summed.shape)) * 100.0
        prop_grid = np.clip(prop_grid, 0, 100)
    else:
        raise ValueError(f"contour_type must be 'Area' or 'Volume', got {contour_type!r}")

    rows = _contours_from_grid(
        prop_grid, transform, list(contour_levels),
        min_area_drop, min_area_fill, simplify, smooth_bandwidth,
    )
    return _build_geodataframe(rows, src_crs, out_crs)


# ---------------------------------------------------------------------------
# 2. Population footprint
# ---------------------------------------------------------------------------

def calc_population_footprint(
    footprint_dict: dict[str, Any],  # shapely Polygon values
    grid_meta: dict,
    contour_levels: list[float] = (5, 10, 15, 20, 30),
    min_area_drop: float = 20_000,
    min_area_fill: float = 20_000,
    simplify: bool = True,
    smooth_bandwidth: float = 2,
    out_crs=None,
) -> gpd.GeoDataFrame:
    """
    Merge individual movement footprints into a population-level overlap
    surface and contour at the requested levels.

    Parameters
    ----------
    footprint_dict : dict
        Mapping of migration name → shapely Polygon/MultiPolygon.
    grid_meta : dict
        Must contain ``'transform'`` (affine), ``'crs'``, and ``'shape'``.
    contour_levels : list of float
        Percentage of individuals that must overlap a cell for it to appear
        in a given contour (e.g. 5 → at least 5 % of individuals used area).
    min_area_drop, min_area_fill, simplify, smooth_bandwidth, out_crs :
        Same as :func:`calc_population_use`.

    Returns
    -------
    GeoDataFrame
        Columns: ``contour``, ``geometry``, ``area_km2``.
    """
    transform = grid_meta["transform"]
    src_crs = CRS.from_user_input(grid_meta["crs"])
    shape_rc = grid_meta["shape"]

    n = len(footprint_dict)
    if n == 0:
        raise ValueError("footprint_dict is empty.")

    # Rasterize each footprint and accumulate
    accum = np.zeros(shape_rc, dtype=np.float64)
    for poly in footprint_dict.values():
        accum += _rasterize_polygon(poly, transform, shape_rc).astype(np.float64)

    prop_grid = accum / n * 100.0  # % of individuals overlapping each cell

    rows = _contours_from_grid(
        prop_grid, transform, list(contour_levels),
        min_area_drop, min_area_fill, simplify, smooth_bandwidth,
    )
    return _build_geodataframe(rows, src_crs, out_crs)


# ---------------------------------------------------------------------------
# 3. Metadata summary
# ---------------------------------------------------------------------------

def generate_metadata_summary(
    migtime_df,
    model_results: dict,
    config: dict,
) -> dict:
    """
    Create summary statistics matching the A37_metadata format.

    Parameters
    ----------
    migtime_df : DataFrame
        Migration timing data with at least columns:
        ``animal_id``, ``season``, ``start_date``, ``end_date``,
        ``distance_km``, ``duration_days``.
    model_results : dict
        Output from model fitting (e.g. kernel parameters, bandwidth).
    config : dict
        Analysis configuration with keys such as ``herd_name``, ``species``,
        ``analyst``, ``analysis_date``, ``kernel_type``, ``bandwidth``, etc.

    Returns
    -------
    dict
        Nested dict with sections: ``herd_info``, ``data_summary``,
        ``migration_timing``, ``migration_distance``, ``model_parameters``.
    """
    import pandas as pd

    summary: dict[str, Any] = {}

    # -- Herd / study info -------------------------------------------------
    summary["herd_info"] = {
        "herd_name":    config.get("herd_name", "Unknown"),
        "species":      config.get("species", "Unknown"),
        "analyst":      config.get("analyst", "Unknown"),
        "analysis_date": config.get("analysis_date", "Unknown"),
    }

    # -- Data summary ------------------------------------------------------
    seasons = migtime_df["season"].unique().tolist() if "season" in migtime_df.columns else []
    data_summary: dict[str, Any] = {
        "seasons": seasons,
        "total_animals": int(migtime_df["animal_id"].nunique()) if "animal_id" in migtime_df.columns else "N/A",
        "total_sequences": int(len(migtime_df)),
    }
    if "season" in migtime_df.columns and "animal_id" in migtime_df.columns:
        per_season = migtime_df.groupby("season").agg(
            n_animals=("animal_id", "nunique"),
            n_sequences=("animal_id", "count"),
        ).to_dict(orient="index")
        data_summary["per_season"] = per_season
    summary["data_summary"] = data_summary

    # -- Migration timing --------------------------------------------------
    timing: dict[str, Any] = {}
    for col in ("start_date", "end_date"):
        if col in migtime_df.columns:
            timing[f"median_{col}"] = (
                migtime_df.groupby("season")[col]
                .median()
                .dt.strftime("%Y-%m-%d")
                .to_dict()
                if hasattr(migtime_df[col], "dt")
                else migtime_df.groupby("season")[col].median().to_dict()
            )
    summary["migration_timing"] = timing

    # -- Migration distance / duration ------------------------------------
    dist_stats: dict[str, Any] = {}
    for col in ("distance_km", "duration_days"):
        if col in migtime_df.columns:
            dist_stats[col] = (
                migtime_df.groupby("season")[col]
                .agg(["mean", "median", "std", "min", "max"])
                .to_dict(orient="index")
            )
    summary["migration_distance"] = dist_stats

    # -- Model parameters --------------------------------------------------
    summary["model_parameters"] = {
        "kernel_type":  config.get("kernel_type", model_results.get("kernel_type", "Unknown")),
        "bandwidth":    config.get("bandwidth",   model_results.get("bandwidth",    "Unknown")),
        "merge_order":  config.get("merge_order",  model_results.get("merge_order",  "Unknown")),
        "contour_type": config.get("contour_type", model_results.get("contour_type", "Unknown")),
        "contour_levels": config.get("contour_levels", model_results.get("contour_levels", "Unknown")),
        "min_area_drop": config.get("min_area_drop", model_results.get("min_area_drop", "Unknown")),
        "min_area_fill": config.get("min_area_fill", model_results.get("min_area_fill", "Unknown")),
        "smooth_bandwidth": config.get("smooth_bandwidth", model_results.get("smooth_bandwidth", "Unknown")),
        **{k: v for k, v in model_results.items()
           if k not in ("kernel_type", "bandwidth", "merge_order",
                        "contour_type", "contour_levels", "min_area_drop",
                        "min_area_fill", "smooth_bandwidth")},
    }

    return summary


# ---------------------------------------------------------------------------
# 4. Export shapefile
# ---------------------------------------------------------------------------

def export_shapefiles(
    gdf: gpd.GeoDataFrame,
    out_path: str | Path,
    layer_name: str,
) -> Path:
    """
    Export a GeoDataFrame to a shapefile.

    Parameters
    ----------
    gdf : GeoDataFrame
    out_path : str or Path
        Directory in which to write the shapefile.
    layer_name : str
        Base name for output files (without extension).

    Returns
    -------
    Path
        Path to the ``.shp`` file written.
    """
    out_dir = Path(out_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    shp_path = out_dir / f"{layer_name}.shp"
    gdf.to_file(str(shp_path))
    return shp_path


# ---------------------------------------------------------------------------
# 5. Export GeoTIFF
# ---------------------------------------------------------------------------

def export_geotiff(
    raster_array: np.ndarray,
    grid_meta: dict,
    out_path: str | Path,
) -> Path:
    """
    Export a 2-D numpy array to a single-band GeoTIFF.

    Parameters
    ----------
    raster_array : ndarray
        2-D array to write.
    grid_meta : dict
        Must contain ``'transform'`` (affine), ``'crs'``, and ``'shape'``.
    out_path : str or Path
        Full output file path (including ``.tif`` extension).

    Returns
    -------
    Path
        Path to the written GeoTIFF.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    profile = {
        "driver":    "GTiff",
        "dtype":     rasterio.float32,
        "width":     raster_array.shape[1],
        "height":    raster_array.shape[0],
        "count":     1,
        "crs":       CRS.from_user_input(grid_meta["crs"]),
        "transform": grid_meta["transform"],
        "compress":  "lzw",
        "nodata":    -9999.0,
    }

    with rasterio.open(str(out_path), "w", **profile) as dst:
        out = raster_array.astype(np.float32)
        out = np.where(np.isnan(out), -9999.0, out)
        dst.write(out, 1)

    return out_path


# ---------------------------------------------------------------------------
# 6. Export report
# ---------------------------------------------------------------------------

_REPORT_TEMPLATE = textwrap.dedent("""\
    ============================================================
    MIGRATION MAPPER POPULATION-LEVEL ANALYSIS REPORT
    ============================================================

    HERD / STUDY INFORMATION
    -------------------------
    Herd name   : {herd_name}
    Species     : {species}
    Analyst     : {analyst}
    Analysis date: {analysis_date}

    DATA SUMMARY
    ------------
    Total animals   : {total_animals}
    Total sequences : {total_sequences}
    Seasons analysed: {seasons}

    MIGRATION TIMING (median per season)
    -------------------------------------
    {timing_block}

    MIGRATION DISTANCE / DURATION (mean ± SD, per season)
    -------------------------------------------------------
    {distance_block}

    MODEL PARAMETERS
    ----------------
    {param_block}

    METHODOLOGY NOTES
    -----------------
    Population Use Surface
      Each individual's utilisation distribution (UD) is normalised to
      sum to 1 and then merged across individuals according to the
      merge_order parameter.  For 'Area' contours the surface represents
      the proportion of individuals with UD > 0 at each cell.  For
      'Volume' contours the surface represents the cumulative UD volume.
      Polygons smaller than min_area_drop m² are removed; holes smaller
      than min_area_fill m² are filled; then (when simplify is on) the
      contour outlines are smoothed with the ksmooth port — matching
      Migration Mapper's CalcPopUse rather than blurring the source grid.

    Population Footprint Surface
      Individual movement footprints are rasterised onto the common grid
      and the proportion of individuals overlapping each cell is computed.
      Contouring, smoothing, and cleanup follow the same procedure as the
      UD surface.

    OUTPUT FILES
    ------------
    popUseMerged/Pop_use_contours.*      Population use contour polygons
    footPrintsMerged/Footprint_contours.*  Population footprint contour polygons
    Metadata/metadata_summary.csv        This summary in tabular form
    Metadata/<season>_migration_distance_info.csv  Per-season distance info
    UDs/<season>/*.tif                   Individual UD GeoTIFFs
    Footprints/<season>/*.shp            Individual footprint shapefiles
    ============================================================
""")


def export_report(
    metadata_summary: dict,
    out_path: str | Path,
) -> Path:
    """
    Write a formatted text report with metadata and methodology explanations.

    Parameters
    ----------
    metadata_summary : dict
        Output of :func:`generate_metadata_summary`.
    out_path : str or Path
        Full output file path (e.g. ``Metadata/report.txt``).

    Returns
    -------
    Path
        Path to the written report.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    hi   = metadata_summary.get("herd_info", {})
    ds   = metadata_summary.get("data_summary", {})
    mt   = metadata_summary.get("migration_timing", {})
    md_  = metadata_summary.get("migration_distance", {})
    mp   = metadata_summary.get("model_parameters", {})

    # Build timing block
    timing_lines = []
    for col, season_vals in mt.items():
        for season, val in season_vals.items():
            timing_lines.append(f"  {season} {col}: {val}")
    timing_block = "\n".join(timing_lines) or "  N/A"

    # Build distance block
    dist_lines = []
    for metric, season_data in md_.items():
        for season, stats in season_data.items():
            mean_ = stats.get("mean", "N/A")
            std_  = stats.get("std",  "N/A")
            dist_lines.append(f"  {season} {metric}: {mean_:.2f} ± {std_:.2f}"
                              if isinstance(mean_, float) else
                              f"  {season} {metric}: {mean_} ± {std_}")
    distance_block = "\n".join(dist_lines) or "  N/A"

    # Build param block
    param_lines = [f"  {k}: {v}" for k, v in mp.items()]
    param_block = "\n".join(param_lines) or "  N/A"

    report_text = _REPORT_TEMPLATE.format(
        herd_name     = hi.get("herd_name", "Unknown"),
        species       = hi.get("species",   "Unknown"),
        analyst       = hi.get("analyst",   "Unknown"),
        analysis_date = hi.get("analysis_date", "Unknown"),
        total_animals   = ds.get("total_animals", "N/A"),
        total_sequences = ds.get("total_sequences", "N/A"),
        seasons         = ", ".join(str(s) for s in ds.get("seasons", [])),
        timing_block    = timing_block,
        distance_block  = distance_block,
        param_block     = param_block,
    )

    out_path.write_text(report_text, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# 7. Export all
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Per-season banded population outputs
# ---------------------------------------------------------------------------

def _sanitize_token(value: str) -> str:
    """Make a filename-safe token: strip whitespace, replace runs of non-word
    chars with underscores, trim leading/trailing underscores."""
    import re
    s = re.sub(r"[^\w]+", "_", str(value).strip())
    return s.strip("_") or "Unknown"


def _season_abbrev(label: str) -> str:
    """Map a sequence label to the 3-letter WMI convention (Spr / Fal / Sum /
    Win). Falls back to a sanitised version of the original label."""
    if not label:
        return "All"
    low = str(label).strip().lower()
    if low.startswith("spr"):
        return "Spr"
    if low.startswith("fal") or low.startswith("aut"):
        return "Fal"
    if low.startswith("sum"):
        return "Sum"
    if low.startswith("win"):
        return "Win"
    return _sanitize_token(label)[:5]


def calc_season_banded_outputs(
    ud_dict: dict[str, np.ndarray],
    grid_meta: dict,
    out_dir: str | Path,
    herd_id: str = "Herd",
    season_label: str = "All",
    date_stamp: str | None = None,
    min_individuals: tuple[int, ...] = (2, 3),
    top_pct: tuple[float, ...] = (10, 20),
    stopover_pct: float = 10.0,
    all_isopleths: tuple[float, ...] = (5, 10, 15, 20, 30, 50, 75, 95),
    min_area_drop: float = 20_000,
    min_area_fill: float = 20_000,
    simplify: bool = True,
    smooth_bandwidth: float = 2.0,
) -> dict[str, Path]:
    """Per-season banded population outputs matching the WMI canonical layout.

    For a *single* season's ``ud_dict`` (mig_key -> 2-D UD array, each on the
    same population grid), writes the canonical product set:

        <herd>_BBMM_<Season>_<date>.tif                       mean UD (float32)
        <herd>_BBMM_<Season>_<date>_all.shp                   isopleth polygons
        <herd>_BBMM_<Season>_<date>_minimumN.tif               ≥N individuals (uint8)
        <herd>_BBMM_<Season>_<date>_minimumN.shp               polygon version
        <herd>_BBMM_<Season>_<date>_topP.tif                  top P% UD volume (uint8)
        <herd>_BBMM_<Season>_<date>_topP.shp                  polygon version
        <herd>_BBMM_<Season>_<date>_stopover.tif              top stopover_pct% of mean-UD volume (uint8)
        <herd>_BBMM_<Season>_<date>_stopover.shp              polygon version

    Parameters
    ----------
    ud_dict:
        Mapping ``mig_key -> UD raster`` for sequences in this season.
    grid_meta:
        Population grid metadata (transform, shape, crs).
    out_dir:
        Folder to write into. Created if absent.
    herd_id:
        Filename prefix (e.g. ``"A37"``).
    season_label:
        Either an already-abbreviated label (``"Spr"``, ``"Fal"``, ``"All"``)
        or a free-form one — passed through :func:`_season_abbrev` either way.
    date_stamp:
        ``"MMYYYY"`` token. Defaults to today.
    min_individuals:
        Thresholds for the ``minN`` files (e.g. ``(1, 2, 3)``).
    top_pct:
        Top-volume percent thresholds for the ``topP`` files.
    stopover_pct:
        Percent of the population **mean-UD volume** that defines a stopover
        (default 10, matching Migration Mapper's ``stopover_percent``). The
        densest cells whose cumulative UD probability mass reaches this
        fraction are kept. Set to 0/None to skip the stopover output.
    all_isopleths:
        Levels (% individuals) used for the ``_all.shp`` contour set.

    Returns
    -------
    ``dict`` mapping a human-readable key (``"ud"``, ``"all"``, ``"minimum1"``,
    ``"top10"`` etc.) to the written :class:`Path`. Missing entries are
    skipped (e.g. if a band produced no polygons).
    """
    # Compute the products in memory, then write every one to ``out_dir``.
    # The compute/write split lets callers (e.g. the Dash app's Tab 5) hold the
    # products in memory and flush only a user-selected subset to disk later —
    # see :func:`compute_season_banded_products` and :func:`write_product`.
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    products = compute_season_banded_products(
        ud_dict, grid_meta,
        herd_id=herd_id, season_label=season_label, date_stamp=date_stamp,
        min_individuals=min_individuals, top_pct=top_pct, stopover_pct=stopover_pct,
        all_isopleths=all_isopleths, min_area_drop=min_area_drop,
        min_area_fill=min_area_fill, simplify=simplify, smooth_bandwidth=smooth_bandwidth,
    )
    written: dict[str, Path] = {}
    for prod in products:
        written[prod["key"]] = write_product(prod, out_dir, grid_meta)
    return written


def _mask_to_gdf(
    mask: np.ndarray,
    transform,
    src_crs,
    name: str,
    min_area_drop: float,
    min_area_fill: float,
    value: int | None = None,
) -> gpd.GeoDataFrame | None:
    """Polygonize a boolean band mask into a one-row GeoDataFrame (``value`` /
    ``band`` columns), applying the same small-speck drop + hole-fill cleanup as
    the contour pipeline. Returns ``None`` when nothing survives. Pure compute —
    no disk I/O (the caller writes the returned GeoDataFrame)."""
    polys = _polygonize_mask(mask, transform)
    if not polys:
        return None
    merged = unary_union(polys)
    if hasattr(merged, "geom_type") and merged.geom_type == "MultiPolygon":
        kept = [p for p in merged.geoms if p.area >= min_area_drop]
        if kept:
            merged = unary_union(kept)
    elif hasattr(merged, "area") and merged.area < min_area_drop:
        return None
    merged = _fill_holes(merged, min_area_fill)
    if value is None:
        value = (int(name[7:]) if name.startswith("minimum") and name[7:].isdigit()
                 else (int(name[3:]) if name.startswith("top") and name[3:].isdigit() else 0))
    return gpd.GeoDataFrame(
        [{"value": value, "band": name}], geometry=[merged], crs=src_crs,
    )


def compute_season_banded_products(
    ud_dict: dict[str, np.ndarray],
    grid_meta: dict,
    herd_id: str = "Herd",
    season_label: str = "All",
    date_stamp: str | None = None,
    min_individuals: tuple[int, ...] = (2, 3),
    top_pct: tuple[float, ...] = (10, 20),
    stopover_pct: float = 10.0,
    all_isopleths: tuple[float, ...] = (5, 10, 15, 20, 30, 50, 75, 95),
    min_area_drop: float = 20_000,
    min_area_fill: float = 20_000,
    simplify: bool = True,
    smooth_bandwidth: float = 2.0,
) -> list[dict]:
    """Compute the per-season banded population products **in memory** without
    touching disk. Returns an ordered list of product descriptors; pass each to
    :func:`write_product` to flush it to a directory.

    Each descriptor is a dict::

        {
          "key":      "count" | "meanUD" | "minimum1" | "top10" | "stopover" | "all" ...,
          "kind":     "count" | "float32" | "uint8" | "vector",
          "filename": "<prefix>_<band>.tif" | ".shp"   (basename, no directory),
          "label":    human-readable description for a UI checkbox,
          "array":    np.ndarray   (raster kinds only),
          "gdf":      GeoDataFrame  (vector kind only),
        }

    The band logic is identical to the historical write-as-you-go version of
    :func:`calc_season_banded_outputs`; only the disk writes have been factored
    out into :func:`write_product`.
    """
    import datetime as _dt
    from rasterio.crs import CRS

    if not ud_dict:
        raise ValueError("ud_dict is empty.")

    if date_stamp is None:
        date_stamp = _dt.datetime.now().strftime("%m%Y")
    season = _season_abbrev(season_label)
    herd = _sanitize_token(herd_id)
    prefix = f"{herd}_BBMM_{season}_{date_stamp}"

    transform = grid_meta["transform"]
    src_crs = CRS.from_user_input(grid_meta["crs"])

    # Stack into (n_layers, H, W).
    arrays = [arr.astype(np.float32) for arr in ud_dict.values()]
    stack = np.stack(arrays, axis=0)
    n_layers = stack.shape[0]

    # Count grid: how many individuals had UD > 0 at each cell.
    count_grid = (stack > 0).sum(axis=0).astype(np.uint16)

    # Mean UD (probability surface) — each individual normalised to sum=1
    # before averaging so big-range animals don't drown out small-range ones.
    # Normalise in-place and accumulate into a 2-D sum to avoid a second 3-D array.
    mean_ud = np.zeros(stack.shape[1:], dtype=np.float64)
    for i in range(n_layers):
        total = stack[i].sum()
        if total > 0:
            stack[i] /= total
        mean_ud += stack[i]
    mean_ud /= n_layers
    s = mean_ud.sum()
    if s > 0:
        mean_ud /= s
    mean_ud = mean_ud.astype(np.float32)

    products: list[dict] = []

    def _add_mask_pair(mask: np.ndarray, band: str, label: str, value: int | None = None):
        """Append the uint8 raster + polygonized vector for a band mask."""
        products.append({
            "key": f"{band}_tif", "kind": "uint8",
            "filename": f"{prefix}_{band}.tif", "label": f"{label} (raster)",
            "array": mask.astype(np.uint8),
        })
        gdf = _mask_to_gdf(mask, transform, src_crs, band,
                           min_area_drop, min_area_fill, value=value)
        if gdf is not None:
            products.append({
                "key": f"{band}_shp", "kind": "vector",
                "filename": f"{prefix}_{band}.shp", "label": f"{label} (polygons)",
                "gdf": gdf,
            })

    # ---- 1. Main raster = overlap-count surface (matches Migration Mapper) ----
    # MM's main per-season tif is the integer count of overlapping individuals
    # (1..N), not a probability density. It's the primary file; the normalised
    # mean-UD density is kept as a separate "_meanUD" output.
    products.append({
        "key": "count", "kind": "count",
        "filename": f"{prefix}.tif", "label": f"{season} mean overlap-count raster",
        "array": count_grid,
    })
    products.append({
        "key": "meanUD", "kind": "float32",
        "filename": f"{prefix}_meanUD.tif", "label": f"{season} mean-UD density raster",
        "array": mean_ud,
    })

    # ---- 2. minN: cells used by ≥N individuals ----
    # minimum1 is redundant with the "all" isopleth output, so skip it.
    # minimum2+ are rasters carrying the actual count values (not binary masks)
    # clipped to cells where count >= N, so the user sees overlap intensity.
    for n in min_individuals:
        if n < 2:
            continue
        mask = (count_grid >= n)
        if mask.sum() == 0:
            continue
        clipped = np.where(mask, count_grid, 0).astype(np.float32)
        products.append({
            "key": f"minimum{n}_tif", "kind": "float32",
            "filename": f"{prefix}_minimum{n}.tif",
            "label": f"{season} ≥{n} individuals count raster",
            "array": clipped,
        })

    # ---- 3. topP%: top X% by volume of the broad USE (count) surface, not the
    # concentrated mean-UD density (which gave tiny specks). Rank cells by
    # overlap count descending, accumulate until X% of the total mass. ----
    use_flat = count_grid.ravel().astype(np.float64)
    order = np.argsort(use_flat)[::-1]
    cumsum = np.cumsum(use_flat[order])
    total = cumsum[-1] if len(cumsum) else 0.0
    if total > 0:
        for p in top_pct:
            threshold_idx = int(np.searchsorted(cumsum, total * p / 100.0)) + 1
            keep_idx = order[:threshold_idx]
            mask = np.zeros(count_grid.size, dtype=np.uint8)
            mask[keep_idx] = 1
            mask = mask.reshape(count_grid.shape)
            if mask.sum() == 0:
                continue
            _add_mask_pair(mask, f"top{int(p)}", f"{season} top {int(p)}% use corridor")

    # ---- 3b. Stopover — top stopover_pct% of the mean-UD VOLUME ----
    # Migration Mapper's stopover (create.corridors.stopovers.R / CalcPopUse.R):
    # take the population mean UD, convert to a volume contour, and keep the
    # densest cells comprising the top `stopover_percent`% of the UD volume.
    # This is intentionally on the mean-UD *density* (where use is concentrated),
    # NOT the overlap-count surface the topP bands above use.
    if stopover_pct and stopover_pct > 0:
        ud_flat = mean_ud.ravel().astype(np.float64)
        order = np.argsort(ud_flat)[::-1]
        cumsum = np.cumsum(ud_flat[order])
        total_ud = cumsum[-1] if len(cumsum) else 0.0
        if total_ud > 0:
            threshold_idx = int(np.searchsorted(cumsum, total_ud * stopover_pct / 100.0)) + 1
            keep_idx = order[:threshold_idx]
            mask = np.zeros(mean_ud.size, dtype=np.uint8)
            mask[keep_idx] = 1
            mask = mask.reshape(mean_ud.shape)
            if mask.sum() > 0:
                _add_mask_pair(
                    mask, "stopover",
                    f"{season} stopovers (top {stopover_pct:g}% of mean-UD)",
                    value=int(round(stopover_pct)),
                )

    # ---- 4. "all" isopleths shapefile (% of individuals overlapping) ----
    presence_pct = count_grid.astype(np.float64) / n_layers * 100.0
    rows = _contours_from_grid(
        presence_pct, transform, list(all_isopleths),
        min_area_drop, min_area_fill, simplify, smooth_bandwidth,
    )
    all_gdf = _build_geodataframe(rows, src_crs, src_crs)
    if len(all_gdf) > 0:
        products.append({
            "key": "all", "kind": "vector",
            "filename": f"{prefix}_all.shp", "label": f"{season} isopleth contours",
            "gdf": all_gdf,
        })

    return products


def write_product(product: dict, out_dir: str | Path, grid_meta: dict) -> Path:
    """Write a single product descriptor (from
    :func:`compute_season_banded_products`) to ``out_dir`` and return its Path.

    Dispatches on ``product["kind"]``:
      - ``"count"``   integer overlap surface → float32 GeoTIFF, 0 → NaN nodata
      - ``"float32"`` density surface → plain float32 GeoTIFF
      - ``"uint8"``   band mask → uint8 GeoTIFF
      - ``"vector"``  GeoDataFrame → shapefile
    """
    import rasterio
    from rasterio.crs import CRS

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / product["filename"]
    kind = product["kind"]

    if kind == "vector":
        product["gdf"].to_file(path)
        return path

    transform = grid_meta["transform"]
    src_crs = CRS.from_user_input(grid_meta["crs"])
    shape_rc = grid_meta["shape"]
    arr = product["array"]

    if kind == "count":
        out = arr.astype(np.float32)
        out[arr <= 0] = np.nan
        with rasterio.open(
            path, "w", driver="GTiff",
            height=shape_rc[0], width=shape_rc[1], count=1,
            dtype=np.float32, crs=src_crs, transform=transform,
            compress="lzw", nodata=float("nan"),
        ) as dst:
            dst.write(out, 1)
    elif kind == "float32":
        with rasterio.open(
            path, "w", driver="GTiff",
            height=shape_rc[0], width=shape_rc[1], count=1,
            dtype=np.float32, crs=src_crs, transform=transform, compress="lzw",
        ) as dst:
            dst.write(arr.astype(np.float32), 1)
    elif kind == "uint8":
        with rasterio.open(
            path, "w", driver="GTiff",
            height=shape_rc[0], width=shape_rc[1], count=1,
            dtype=np.uint8, crs=src_crs, transform=transform, compress="lzw",
        ) as dst:
            dst.write(arr.astype(np.uint8), 1)
    else:
        raise ValueError(f"write_product: unknown kind {kind!r}")

    return path


# ---------------------------------------------------------------------------
# Herd-level metadata CSV / XLSX (matches WMI canonical schema)
# ---------------------------------------------------------------------------

_KM_TO_MILES = 0.621371


def _season_abbrev_lower(label: str) -> str:
    """Lowercase 3-letter season abbreviation for column suffixes
    (spr / fal / sum / win / all). Mirrors _season_abbrev but emits
    the case the WMI metadata file uses (Animals_spr, Seqs_fal, ...)."""
    if not label:
        return "all"
    low = str(label).strip().lower()
    if low.startswith("spr"):
        return "spr"
    if low.startswith("fal") or low.startswith("aut"):
        return "fal"
    if low.startswith("sum"):
        return "sum"
    if low.startswith("win"):
        return "win"
    return _sanitize_token(low)[:5].lower()


def _stat_or_na(values, fn, fmt=None):
    """Apply a stat (np.mean / min / max / median) to a list, returning 'NA'
    when the list is empty. Optionally format the result."""
    arr = [v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not arr:
        return "NA"
    out = fn(np.array(arr, dtype=float))
    if fmt is None:
        return out
    return fmt(out)


def write_herd_metadata(
    processed_df,
    sequences_dict: dict,
    out_dir: str | Path,
    herd_id: str = "Herd",
    species: str | None = None,
    analyst: str = "Unknown",
    date_stamp: str | None = None,
    season_labels_order: list[str] | None = None,
) -> dict[str, Path]:
    """Write the herd-level metadata summary CSV + XLSX in the WMI 2-column
    key/value schema. Filename: ``<herd>_metadata_<MMYYYY>.{csv,xlsx}``.

    The R reference's file is two columns: an empty-named first column for
    the statistic label, ``V1`` for the value. We match that layout exactly
    (down to the empty header on column 1) so analysts can open ours in the
    same tooling they use for the canonical files.

    All distances are reported in MILES (the WMI convention for CO wildlife
    biology), converted from the per-sequence Euclidean / cumulative
    distances computed in metres on the projected coordinates.

    Parameters
    ----------
    processed_df:
        Full processed GPS dataframe — used for top-level counts (Individuals,
        Males/Females, Project_start/end_year, fix-rate stats).
    sequences_dict:
        Mapping ``mig_key -> sequence GeoDataFrame``. Used to compute the
        per-season blocks. Each value must have ``date`` and projected (metre)
        geometry.
    out_dir:
        Directory to write into. Created if absent.
    herd_id:
        Goes into the ``Herd_Name`` row.
    species:
        Optional. Otherwise read from a ``Species`` column on
        ``processed_df`` (first non-null) or defaulted to ``"Unknown"``.
    analyst:
        Whatever name to record. Default ``"Unknown"``.
    date_stamp:
        Filename token ``MMYYYY``. Defaults to today.
    season_labels_order:
        Order in which to lay out the per-season blocks. Defaults to
        sorted alphabetical, but pass e.g. ``["Spring", "Fall"]`` for the
        traditional ordering.
    """
    import datetime as _dt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if date_stamp is None:
        date_stamp = _dt.datetime.now().strftime("%m%Y")
    herd_token = _sanitize_token(herd_id)

    # ----- Per-sequence stats -------------------------------------------------
    # For each sequence: derive (season_label, animal_id, start, end, days,
    # eucl_km, cumu_km). Cheaper than re-running calc_seq_distances; we already
    # have the same geometry locally.
    per_seq: list[dict] = []
    for mig_key, sub in sequences_dict.items():
        if sub is None or len(sub) == 0:
            continue
        parts = str(mig_key).rsplit("_", 2)
        if len(parts) == 3:
            animal_id, _bio_year_str, season_label = parts
        else:
            animal_id, season_label = str(mig_key), ""
        sub = sub.copy()
        if "date" in sub.columns:
            sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
        xs = sub.geometry.x.to_numpy(dtype=float)
        ys = sub.geometry.y.to_numpy(dtype=float)
        if len(xs) < 2:
            continue
        sub = sub.sort_values("date") if "date" in sub.columns else sub
        t_start = sub["date"].min() if "date" in sub.columns else pd.NaT
        t_end = sub["date"].max() if "date" in sub.columns else pd.NaT
        days = float((t_end - t_start).total_seconds() / 86400.0) if pd.notna(t_start) and pd.notna(t_end) else float("nan")
        eucl_km = float(np.hypot(xs[-1] - xs[0], ys[-1] - ys[0]) / 1000.0)
        cumu_km = float(np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2).sum() / 1000.0)
        per_seq.append({
            "season": season_label,
            "animal_id": animal_id,
            "start": t_start,
            "end": t_end,
            "days": days,
            "eucl_miles": eucl_km * _KM_TO_MILES,
            "cumu_miles": cumu_km * _KM_TO_MILES,
            "eucl_km": eucl_km,
            "cumu_km": cumu_km,
        })

    # Group seqs by season, then build the canonical key/value list.
    by_season: dict[str, list[dict]] = {}
    for r in per_seq:
        by_season.setdefault(r["season"], []).append(r)

    if season_labels_order is None:
        season_labels_order = sorted(by_season.keys())
    else:
        # Make sure any unanticipated labels are still included on the tail.
        season_labels_order = list(season_labels_order) + [
            s for s in by_season.keys() if s not in season_labels_order
        ]

    # ----- Top-level rows ----------------------------------------------------
    rows: list[tuple[str, object]] = []

    # Resolve Species
    if species is None and "Species" in processed_df.columns:
        non_null = processed_df["Species"].dropna()
        species = str(non_null.iloc[0]) if not non_null.empty else "Unknown"
    elif species is None:
        species = "Unknown"

    rows.append(("Herd_Name", herd_token))
    rows.append(("Species", species))
    rows.append(("Analyses_Date", _dt.datetime.now().strftime("%m/%d/%Y")))
    rows.append(("Analyst", analyst))

    # Individuals / Males / Females
    n_individuals = int(processed_df["animal_id"].nunique()) if "animal_id" in processed_df.columns else 0
    rows.append(("Individuals", n_individuals))
    if "Sex" in processed_df.columns:
        sex_groups = processed_df.dropna(subset=["Sex"]).groupby("animal_id")["Sex"].first()
        n_males = int((sex_groups.astype(str).str.upper().isin({"M", "MALE"})).sum())
        n_females = int((sex_groups.astype(str).str.upper().isin({"F", "FEMALE"})).sum())
    else:
        n_males = 0
        n_females = 0
    rows.append(("Males", n_males))
    rows.append(("Females", n_females))

    # Project year range
    if "timestamp" in processed_df.columns:
        ts = pd.to_datetime(processed_df["timestamp"], errors="coerce")
        if ts.notna().any():
            rows.append(("Project_start_year", int(ts.min().year)))
            rows.append(("Project_end_year", int(ts.max().year)))
        else:
            rows.append(("Project_start_year", "NA"))
            rows.append(("Project_end_year", "NA"))
    else:
        rows.append(("Project_start_year", "NA"))
        rows.append(("Project_end_year", "NA"))

    # Fix-rate stats — drawn from the fix_rate_hours column computed in
    # data_ingestion.calc_movement_params.
    if "fix_rate_hours" in processed_df.columns:
        fr = pd.to_numeric(processed_df["fix_rate_hours"], errors="coerce").dropna()
        if not fr.empty:
            rows.append(("max_FixRate_hours", float(fr.max())))
            rows.append(("min_FixRate_hours", float(fr.min())))
            rows.append(("med_FIXRate_hours", float(fr.median())))
        else:
            rows.append(("max_FixRate_hours", "NA"))
            rows.append(("min_FixRate_hours", "NA"))
            rows.append(("med_FIXRate_hours", "NA"))
    else:
        rows.append(("max_FixRate_hours", "NA"))
        rows.append(("min_FixRate_hours", "NA"))
        rows.append(("med_FIXRate_hours", "NA"))

    # ----- Per-season Animals / Seqs blocks -----------------------------------
    season_abbrevs: list[tuple[str, str]] = [
        (label, _season_abbrev_lower(label)) for label in season_labels_order
    ]
    for label, abbrev in season_abbrevs:
        seqs = by_season.get(label, [])
        animals = {r["animal_id"] for r in seqs}
        rows.append((f"Animals_{abbrev}", len(animals)))
    # "all" is unique animals across every season
    all_animals = {r["animal_id"] for r in per_seq}
    rows.append(("Animals_all", len(all_animals)))

    for label, abbrev in season_abbrevs:
        seqs = by_season.get(label, [])
        rows.append((f"Seqs_{abbrev}", len(seqs)))
    rows.append(("Seqs_all", len(per_seq)))

    # ----- Per-season median start / end dates --------------------------------
    def _median_mmdd(dts):
        dts = [t for t in dts if pd.notna(t)]
        if not dts:
            return "NA"
        # Median by day-of-year, then format MM/DD.
        ord_days = sorted(int(t.timetuple().tm_yday) for t in dts)
        mid = ord_days[len(ord_days) // 2]
        # Convert day-of-year back to a synthetic date (any non-leap year is fine).
        d = _dt.date(2025, 1, 1) + _dt.timedelta(days=mid - 1)
        return d.strftime("%m/%d")

    for label, abbrev in season_abbrevs:
        seqs = by_season.get(label, [])
        rows.append((f"med_start_{abbrev}", _median_mmdd([r["start"] for r in seqs])))
        rows.append((f"med_end_{abbrev}", _median_mmdd([r["end"] for r in seqs])))

    # ----- Per-season migration-day stats -------------------------------------
    for label, abbrev in season_abbrevs:
        seqs = by_season.get(label, [])
        days = [r["days"] for r in seqs if r.get("days") is not None]
        rows.append((f"avg_mig_days_{abbrev}", _stat_or_na(days, np.mean)))
        rows.append((f"min_mig_days_{abbrev}", _stat_or_na(days, np.min)))
        rows.append((f"max_mig_days_{abbrev}", _stat_or_na(days, np.max)))

    # ----- Per-season cumulative-distance stats (miles AND km) ----------------
    # Cumulative = total path length (sum of step distances). Both units are
    # reported (miles = WMI/Jaffe convention; km = Chloe convention).
    for label, abbrev in season_abbrevs:
        seqs = by_season.get(label, [])
        cumu = [r["cumu_miles"] for r in seqs if r.get("cumu_miles") is not None]
        cumu_km = [r["cumu_km"] for r in seqs if r.get("cumu_km") is not None]
        rows.append((f"avg_mig_miles_cumu_{abbrev}", _stat_or_na(cumu, np.mean)))
        rows.append((f"min_mig_miles_cumu_{abbrev}", _stat_or_na(cumu, np.min)))
        rows.append((f"max_mig_miles_cumu_{abbrev}", _stat_or_na(cumu, np.max)))
        rows.append((f"avg_mig_km_cumu_{abbrev}", _stat_or_na(cumu_km, np.mean)))
        rows.append((f"min_mig_km_cumu_{abbrev}", _stat_or_na(cumu_km, np.min)))
        rows.append((f"max_mig_km_cumu_{abbrev}", _stat_or_na(cumu_km, np.max)))
    all_cumu = [r["cumu_miles"] for r in per_seq]
    all_cumu_km = [r["cumu_km"] for r in per_seq]
    rows.append(("avg_mig_miles_cumu_all", _stat_or_na(all_cumu, np.mean)))
    rows.append(("avg_mig_km_cumu_all", _stat_or_na(all_cumu_km, np.mean)))

    # ----- Per-season Euclidean (straight-line) distance stats (miles AND km) -
    for label, abbrev in season_abbrevs:
        seqs = by_season.get(label, [])
        eucl = [r["eucl_miles"] for r in seqs if r.get("eucl_miles") is not None]
        eucl_km = [r["eucl_km"] for r in seqs if r.get("eucl_km") is not None]
        rows.append((f"avg_mig_miles_eucl_{abbrev}", _stat_or_na(eucl, np.mean)))
        rows.append((f"min_mig_miles_eucl_{abbrev}", _stat_or_na(eucl, np.min)))
        rows.append((f"max_mig_miles_eucl_{abbrev}", _stat_or_na(eucl, np.max)))
        rows.append((f"avg_mig_km_eucl_{abbrev}", _stat_or_na(eucl_km, np.mean)))
        rows.append((f"min_mig_km_eucl_{abbrev}", _stat_or_na(eucl_km, np.min)))
        rows.append((f"max_mig_km_eucl_{abbrev}", _stat_or_na(eucl_km, np.max)))
    all_eucl = [r["eucl_miles"] for r in per_seq]
    all_eucl_km = [r["eucl_km"] for r in per_seq]
    rows.append(("avg_mig_miles_eucl_all", _stat_or_na(all_eucl, np.mean)))
    rows.append(("avg_mig_km_eucl_all", _stat_or_na(all_eucl_km, np.mean)))

    # ----- Annual active collars (Chloe-style) --------------------------------
    # Number of unique animals with data in each biological year. Added both as
    # per-year rows here and written to a dedicated <herd>_annualCollars CSV.
    annual_pairs: list[tuple[str, int]] = []
    if "bio_year" in processed_df.columns and "animal_id" in processed_df.columns:
        bdf = processed_df.dropna(subset=["bio_year"])
        counts = bdf.groupby("bio_year")["animal_id"].nunique()
        def _year_key(v):
            try:
                return int(float(v))
            except (ValueError, TypeError):
                return str(v)
        for yr in sorted(counts.index, key=_year_key):
            try:
                yr_label = str(int(float(yr)))
            except (ValueError, TypeError):
                yr_label = str(yr)
            annual_pairs.append((yr_label, int(counts[yr])))
    for yr_label, cnt in annual_pairs:
        rows.append((f"ActiveCollars_{yr_label}", cnt))

    # Two-column dataframe with the WMI quirky header layout:
    # first column unnamed, second column "V1".
    df_meta = pd.DataFrame(rows, columns=["", "V1"])

    written: dict[str, Path] = {}
    csv_path = out_dir / f"{herd_token}_metadata_{date_stamp}.csv"
    df_meta.to_csv(csv_path, index=False, encoding="utf-8")
    written["csv"] = csv_path

    # Dedicated annual-active-collars CSV (Year, ActiveCollars) — mirrors
    # Chloe's metadata_annualCollars.csv.
    if annual_pairs:
        annual_df = pd.DataFrame(annual_pairs, columns=["Year", "ActiveCollars"])
        annual_path = out_dir / f"{herd_token}_annualCollars_{date_stamp}.csv"
        annual_df.to_csv(annual_path, index=False, encoding="utf-8")
        written["annual_collars"] = annual_path

    # XLSX mirror — requires openpyxl. Sheet name matches filename stem.
    try:
        xlsx_path = out_dir / f"{herd_token}_metadata_{date_stamp}.xlsx"
        sheet_name = f"{herd_token}_metadata_{date_stamp}"[:31]  # Excel sheet name cap
        df_meta.to_excel(xlsx_path, sheet_name=sheet_name, index=False)
        written["xlsx"] = xlsx_path
    except Exception:
        pass  # If openpyxl isn't available, the CSV is still useful on its own.

    return written


def _line_distances_km(xs, ys) -> tuple[float, float, float]:
    """Per-sequence distance metrics (km) from ordered projected (metre) coords.

    Returns ``(eucl, cumu, maxpair)``:
      - ``eucl``     straight line, first fix -> last fix
      - ``cumu``     total path length (sum of sequential segment lengths)
      - ``maxpair``  greatest straight-line distance between ANY two fixes
                     (the migration's max spread), via the full pairwise matrix

    Returns zeros for sequences with fewer than 2 points.
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if len(xs) < 2:
        return 0.0, 0.0, 0.0
    eucl = float(np.hypot(xs[-1] - xs[0], ys[-1] - ys[0]) / 1000.0)
    cumu = float(np.sqrt(np.diff(xs) ** 2 + np.diff(ys) ** 2).sum() / 1000.0)
    dx = xs[:, None] - xs[None, :]
    dy = ys[:, None] - ys[None, :]
    maxpair = float(np.sqrt((dx * dx + dy * dy).max()) / 1000.0)
    return eucl, cumu, maxpair


def write_per_season_distance_csvs(
    sequences_dict: dict,
    out_dir: str | Path,
    id_col: str = "mig",
    write_xlsx: bool = True,
) -> dict[str, Path]:
    """Per-season ``<season>_migration_distance_info.csv`` SUMMARY files.

    One CSV per season. Each file has three rows (one per distance metric) and
    the columns ``metric, mean_km, sd_km, min_km, max_km, n_sequences``:

        metric              meaning
        eucl_firstlast_km   straight line first fix -> last fix
        cumu_path_km        total path length
        maxpair_spread_km   greatest straight-line distance between any two fixes

    Reworked 2026-06-26: previously one row per sequence with the season-wide
    stats repeated on every row (a port of CalcSeqDistances.R). The per-sequence
    distances now live as columns on ``MigLines.shp`` (Eucl_Dist_ / Cumu_Dist_ /
    MaxPair_km), so these CSVs are pure season summaries — easier to read and no
    longer parity-bound to the R layout.

    Writes to ``out_dir / Metadata / <season>_migration_distance_info.csv``.
    """
    out_dir = Path(out_dir)
    meta_dir = out_dir / "Metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    # Group sequences by season label (last token of mig_key).
    by_season: dict[str, list] = {}
    for mig_key, sub in sequences_dict.items():
        if sub is None or len(sub) == 0:
            continue
        parts = str(mig_key).rsplit("_", 1)
        label = parts[1] if len(parts) == 2 else "all"
        by_season.setdefault(label, []).append(sub)

    def _stats(vals: list[float]) -> tuple[float, float, float, float]:
        a = np.asarray(vals, dtype=float)
        sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
        return float(a.mean()), sd, float(a.min()), float(a.max())

    written: dict[str, Path] = {}
    for label, subs in by_season.items():
        try:
            eucls: list[float] = []
            cumus: list[float] = []
            maxprs: list[float] = []
            for sub in subs:
                s = sub.copy().sort_values("date")
                xs = s.geometry.x.to_numpy(dtype=float)
                ys = s.geometry.y.to_numpy(dtype=float)
                if len(xs) < 2:
                    continue
                e, c, m = _line_distances_km(xs, ys)
                eucls.append(e)
                cumus.append(c)
                maxprs.append(m)
            if not eucls:
                continue

            rows = []
            for name, vals in (
                ("eucl_firstlast_km", eucls),
                ("cumu_path_km", cumus),
                ("maxpair_spread_km", maxprs),
            ):
                mean_km, sd_km, min_km, max_km = _stats(vals)
                rows.append({
                    "metric": name,
                    "mean_km": round(mean_km, 4),
                    "sd_km": round(sd_km, 4),
                    "min_km": round(min_km, 4),
                    "max_km": round(max_km, 4),
                    "n_sequences": len(vals),
                })
            df = pd.DataFrame(
                rows,
                columns=["metric", "mean_km", "sd_km", "min_km", "max_km", "n_sequences"],
            )
            csv_path = meta_dir / f"{label}_migration_distance_info.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8")
            written[label + "_csv"] = csv_path
            if write_xlsx:
                try:
                    xlsx_path = meta_dir / f"{label}_migration_distance_info.xlsx"
                    df.to_excel(xlsx_path, index=False)
                    written[label + "_xlsx"] = xlsx_path
                except Exception:
                    pass
        except Exception:
            pass
    return written


# ---------------------------------------------------------------------------
# Flag-removed processed-data shapefile
# ---------------------------------------------------------------------------

def write_flags_removed_shapefile(
    processed_df,
    out_dir: str | Path,
    herd_id: str = "Herd",
    project_name: str = "Project",
    date_stamp: str | None = None,
    lon_col: str = "lon",
    lat_col: str = "lat",
    crs: str = "EPSG:4326",
) -> Path | None:
    """Filtered GPS file (no problem / mortality fixes) written as a
    **GeoPackage** named like the reference:
    ``<Herd>_<ProjectName>_FlagsRemoved_<DDMMMYYYY>.gpkg``.

    GeoPackage was chosen over ESRI Shapefile so long column names survive
    intact — shapefile's .dbf attribute table caps field names at 10 ASCII
    characters and silently laundered ours (`mortality_flag` → `mortality_`,
    `displacement_animal_id` / `displacement_id_bio_year` collided on the
    prefix and became `displace_1` / `displace_2`, etc.). GeoPackage is a
    modern OGC SQLite-backed format with no field-name limit and opens
    cleanly in QGIS / ArcGIS Pro / R `sf` / `geopandas`. The MigPoints /
    MigLines / popUseMerged shapefiles that the original WMI Migration
    Mapper *consumes* stay as `.shp` for compatibility — this file is an
    app-internal visual cross-check, not a Migration Mapper input.

    Drops rows where ``problem == 1`` or ``mortality_flag == 1`` (auto- or
    user-flagged), preserving everything else verbatim. Writes to
    ``out_dir / EXPORTS / <name>.gpkg``.

    Returns the ``.gpkg`` Path, or ``None`` if no rows remain after filtering.
    """
    import datetime as _dt

    out_dir = Path(out_dir)
    exports_dir = out_dir / "EXPORTS"
    exports_dir.mkdir(parents=True, exist_ok=True)

    if date_stamp is None:
        date_stamp = _dt.datetime.now().strftime("%d%b%Y")  # e.g. "18May2026"

    df = processed_df.copy()
    if "problem" in df.columns:
        df = df[df["problem"].fillna(0).astype(int) == 0]
    if "mortality_flag" in df.columns:
        df = df[df["mortality_flag"].fillna(0).astype(int) == 0]
    if df.empty:
        return None

    if lon_col not in df.columns or lat_col not in df.columns:
        return None

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
        crs=crs,
    )

    # Datetimes don't survive shapefile DBF — coerce to ISO strings.
    for col in gdf.columns:
        if col == "geometry":
            continue
        if pd.api.types.is_datetime64_any_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)

    name = f"{_sanitize_token(herd_id)}_{_sanitize_token(project_name)}_FlagsRemoved_{date_stamp}.gpkg"
    out_path = exports_dir / name
    # GeoPackage has no 10-char field-name limit, so we write directly with
    # no warning-suppression dance. The layer name inside the .gpkg matches
    # the file stem so GIS tools open it with a sensible default label.
    layer_name = out_path.stem
    try:
        gdf.to_file(out_path, layer=layer_name, driver="GPKG")
    except Exception:
        # Some columns (lists, dicts) can crash the writer; drop them and retry.
        safe_gdf = gdf.copy()
        for col in safe_gdf.columns:
            if col == "geometry":
                continue
            if safe_gdf[col].dtype == object:
                safe_gdf[col] = safe_gdf[col].astype(str)
        safe_gdf.to_file(out_path, layer=layer_name, driver="GPKG")
    return out_path


# ---------------------------------------------------------------------------
# MigLines / MigPoints / MigLines_Dist shapefile writers
# (matches the WMI canonical attribute schema)
# ---------------------------------------------------------------------------

def write_mig_outputs(
    processed_df,
    migtime_df,
    sequences_dict: dict,
    out_dir: str | Path,
    herd_id: str = "Herd",
    date_stamp: str | None = None,
    seq_labels: list[str] | None = None,
    bio_year_start_month: int = 2,
    bio_year_start_day: int = 1,
    target_crs=None,
) -> dict[str, Path]:
    """Write the MigLines / MigPoints shapefile set.

    Outputs:
        <herd>_MigLines_<date>.shp        one LineString per sequence, carrying
                                          all per-sequence distance columns:
                                          Eucl_Dist_ km (first->last straight
                                          line), Cumu_Dist_ km (path length),
                                          MaxPair_km (max straight-line spread
                                          between any two fixes)
        <herd>_MigPoints_<date>.shp       all GPS fixes that fall inside any
                                          sequence window

    Note: MigLines_Dist was merged into MigLines on 2026-06-26 (it was just
    MigLines + the distance columns). Per-season summaries of these distances
    are written separately by :func:`write_per_season_distance_csvs`.

    Parameters
    ----------
    processed_df:
        Full processed dataframe of GPS fixes (must contain ``animal_id``,
        ``timestamp``, ``lon``, ``lat``, and any original CPW columns
        to carry into MigPoints).
    migtime_df:
        Reviewed/filled migtime table (one row per id_bio_year, with
        ``mig1_start`` … ``mig8_end`` date columns).
    sequences_dict:
        Mapping ``mig_key -> GeoDataFrame`` produced by
        :func:`sequencing.extract_sequences`. Geometry must be Point in a
        projected (metre) CRS so distances come out in metres.
    out_dir:
        Folder to write into. Created if absent.
    herd_id:
        Filename prefix (e.g. ``"A37"``).
    date_stamp:
        ``"MMYYYY"`` token. Defaults to today.
    seq_labels:
        User-supplied per-slot labels in slot order
        (``["Spring", "Fall", ...]``). Used to map each sequence back to
        its ``"mig1".."mig8"`` slot for the ``Mig`` column.
    bio_year_start_month, bio_year_start_day:
        Bio-year anchor for the ``tempStartM`` / ``tempStartD`` columns.
    target_crs:
        Optional CRS to reproject all outputs into. Defaults to whatever
        the sequence geometries are already in.
    """
    import datetime as _dt
    from shapely.geometry import LineString, Point

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if date_stamp is None:
        date_stamp = _dt.datetime.now().strftime("%m%Y")
    herd_token = _sanitize_token(herd_id)

    # Build "label -> slot index" lookup so we can write "mig1".."mig8".
    label_to_slot: dict[str, int] = {}
    if seq_labels:
        for i, lab in enumerate(seq_labels):
            if lab:
                label_to_slot[str(lab)] = i + 1

    # The CRS to carry through. If sequences are missing CRS, fall back to
    # target_crs (typically the pop_grid's projected CRS).
    sample_crs = None
    for sub in sequences_dict.values():
        if hasattr(sub, "crs") and sub.crs is not None:
            sample_crs = sub.crs
            break
    if target_crs is None:
        target_crs = sample_crs

    line_rows: list[dict] = []
    line_geoms: list = []
    fix_indices: list[int] = []  # rows of processed_df included in MigPoints

    for mig_key, sub in sequences_dict.items():
        if sub is None or len(sub) == 0:
            continue
        sub = sub.copy().sort_values("date")
        # Reproject to target_crs if needed for consistent metric distances.
        if target_crs is not None and getattr(sub, "crs", None) is not None and sub.crs != target_crs:
            sub = sub.to_crs(target_crs)

        # Parse the mig_key: "<animal>_<bio_year>_<season_label>"
        parts = str(mig_key).rsplit("_", 2)
        if len(parts) == 3:
            animal_id, bio_year_str, season_label = parts
        else:
            animal_id, bio_year_str, season_label = str(mig_key), "", ""

        try:
            bio_year_full = int(bio_year_str)
        except (ValueError, TypeError):
            bio_year_full = 0
        bio_year_2digit = bio_year_full % 100 if bio_year_full else 0

        # Build the LineString from sorted points.
        xs = sub.geometry.x.to_numpy(dtype=float)
        ys = sub.geometry.y.to_numpy(dtype=float)
        if len(xs) < 2:
            # Single-point "line" — skip the linestring, but still include the
            # fixes in MigPoints. (Reference behaviour mirrors this.)
            continue
        line = LineString(list(zip(xs, ys)))

        # Mig_Start / Mig_End as Unix epoch (seconds) STRING — matches ref.
        dates = pd.to_datetime(sub["date"], errors="coerce")
        t_start = dates.min()
        t_end = dates.max()
        duration_days = (t_end - t_start).total_seconds() / 86400.0
        # Unix epoch in seconds (ref uses 10-digit values like "1617148800").
        mig_start_str = str(int(t_start.timestamp())) if pd.notna(t_start) else ""
        mig_end_str = str(int(t_end.timestamp())) if pd.notna(t_end) else ""

        # Distances (km). MaxPair_km = greatest straight-line distance between
        # any two fixes (migration spread); shapefile .dbf caps field names at
        # 10 chars, hence the short names here (long names are in the summary CSV).
        eucl_dist_km, cumu_dist_km, maxpair_km = _line_distances_km(xs, ys)

        line_rows.append({
            "id_bioYear": f"{animal_id}_{bio_year_2digit:02d}" if bio_year_full else str(mig_key),
            "Mig": f"mig{label_to_slot.get(season_label, 1)}",
            "newUid": animal_id,
            "bioYear": int(bio_year_2digit),
            "bioYearFul": int(bio_year_full),
            "tempStartD": int(bio_year_start_day),
            "tempStartM": int(bio_year_start_month),
            "Mig_Start": mig_start_str,
            "Mig_End": mig_end_str,
            "Duration": round(float(duration_days), 4),
            "Season": str(season_label),
            "FXR.n": int(len(sub)),
            "Eucl_Dist_": round(eucl_dist_km, 6),
            "Cumu_Dist_": round(cumu_dist_km, 6),
            "MaxPair_km": round(maxpair_km, 6),
        })
        line_geoms.append(line)
        # Stash the original-row index (we'll round-trip via timestamp+animal).
        # The sub["id"] is animal_id; date column is parsed timestamps.

    written: dict[str, Path] = {}

    # --- MigLines (single file, carries all per-sequence distances) ---
    # Merged 2026-06-26: the old separate MigLines_Dist was just MigLines + the
    # distance columns, so it's consolidated here. One LineString per sequence
    # with Eucl_Dist_ (first->last), Cumu_Dist_ (path length), MaxPair_km (max
    # spread). Per-season summaries of these go to <season>_migration_distance_info.csv.
    if line_rows:
        mig_lines = gpd.GeoDataFrame(line_rows, geometry=line_geoms, crs=target_crs)
        # Put the distance columns at the end, after the descriptive attributes.
        dist_cols = ["Eucl_Dist_", "Cumu_Dist_", "MaxPair_km"]
        cols = [c for c in mig_lines.columns if c not in dist_cols + ["geometry"]]
        cols += dist_cols + ["geometry"]
        mig_lines = mig_lines[cols]
        path = out_dir / f"{herd_token}_MigLines_{date_stamp}.shp"
        mig_lines.to_file(path)
        written["MigLines"] = path

    # --- MigPoints ---
    # Build the union of all GPS fixes that fall inside any sequence window.
    # We trust extract_sequences to have done the time-window slicing, so we
    # just union the GeoDataFrames it produced.
    if sequences_dict:
        frames = []
        for mig_key, sub in sequences_dict.items():
            if sub is None or len(sub) == 0:
                continue
            sub = sub.copy()
            if target_crs is not None and getattr(sub, "crs", None) is not None and sub.crs != target_crs:
                sub = sub.to_crs(target_crs)
            sub["mig_key"] = mig_key
            frames.append(sub)
        if frames:
            mig_points = pd.concat(frames, ignore_index=True)
            # Optionally enrich with the original CPW columns if we still have
            # them on `processed_df`. We match on animal_id + timestamp.
            try:
                cpw_cols = [c for c in processed_df.columns
                            if c not in ("animal_id", "timestamp", "lon", "lat", "x", "y", "geometry")]
                if cpw_cols:
                    proc = processed_df[["animal_id", "timestamp", *cpw_cols]].copy()
                    proc["timestamp"] = pd.to_datetime(proc["timestamp"], errors="coerce")
                    mig_points["date"] = pd.to_datetime(mig_points["date"], errors="coerce")
                    mig_points = mig_points.merge(
                        proc,
                        how="left",
                        left_on=["id", "date"],
                        right_on=["animal_id", "timestamp"],
                    )
                    mig_points = mig_points.drop(
                        columns=[c for c in ("animal_id", "timestamp") if c in mig_points.columns]
                    )
            except Exception:
                pass

            # Datetime cols don't survive shapefile DBF — coerce to ISO strings.
            for col in mig_points.columns:
                if pd.api.types.is_datetime64_any_dtype(mig_points[col]):
                    mig_points[col] = mig_points[col].astype(str)
            mig_points_gdf = gpd.GeoDataFrame(
                mig_points,
                geometry=mig_points.get("geometry"),
                crs=target_crs,
            )
            path = out_dir / f"{herd_token}_MigPoints_{date_stamp}.shp"
            mig_points_gdf.to_file(path)
            written["MigPoints"] = path

    return written


def export_all(
    pop_use_gdf: gpd.GeoDataFrame,
    pop_foot_gdf: gpd.GeoDataFrame,
    ud_dict: dict[str, np.ndarray],
    footprint_dict: dict[str, Any],
    grid_meta: dict,
    metadata: dict,
    out_dir: str | Path,
) -> dict[str, list[Path]]:
    """
    Export all population-level products to a directory structure matching
    Migration Mapper conventions.

    Directory layout::

        out_dir/
          popUseMerged/Pop_use_contours.*
          footPrintsMerged/Footprint_contours.*
          Metadata/metadata_summary.csv
          Metadata/{season}_migration_distance_info.csv
          UDs/{season}/*.tif
          Footprints/{season}/*.shp

    Parameters
    ----------
    pop_use_gdf : GeoDataFrame
        Output of :func:`calc_population_use`.
    pop_foot_gdf : GeoDataFrame
        Output of :func:`calc_population_footprint`.
    ud_dict : dict
        {mig_name: 2-D ndarray} – individual UD rasters (same keys as used
        to produce ``pop_use_gdf``).
    footprint_dict : dict
        {mig_name: shapely polygon} – individual footprints.
    grid_meta : dict
        Raster grid metadata (``transform``, ``crs``, ``shape``).
    metadata : dict
        Output of :func:`generate_metadata_summary`.
    out_dir : str or Path
        Root output directory (created if absent).

    Returns
    -------
    dict
        Mapping of category label → list of Path objects written.
    """
    out_dir = Path(out_dir)
    written: dict[str, list[Path]] = {
        "pop_use":   [],
        "pop_foot":  [],
        "metadata":  [],
        "uds":       [],
        "footprints": [],
    }

    # ------------------------------------------------------------------
    # Population use contours
    # ------------------------------------------------------------------
    pu_dir = out_dir / "popUseMerged"
    shp = export_shapefiles(pop_use_gdf, pu_dir, "Pop_use_contours")
    written["pop_use"].append(shp)

    # ------------------------------------------------------------------
    # Footprint contours
    # ------------------------------------------------------------------
    fp_dir = out_dir / "footPrintsMerged"
    shp = export_shapefiles(pop_foot_gdf, fp_dir, "Footprint_contours")
    written["pop_foot"].append(shp)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    meta_dir = out_dir / "Metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    # metadata_summary.csv (flat)
    summary_csv = meta_dir / "metadata_summary.csv"
    _write_flat_csv(metadata, summary_csv)
    written["metadata"].append(summary_csv)

    # Per-season distance info
    dist_data = metadata.get("migration_distance", {})
    seasons_seen: set[str] = set()
    for metric, season_dict in dist_data.items():
        for season in season_dict:
            seasons_seen.add(str(season))

    for season in seasons_seen:
        season_csv = meta_dir / f"{season}_migration_distance_info.csv"
        rows_out = []
        for metric, season_dict in dist_data.items():
            if season in season_dict:
                row = {"metric": metric, "season": season}
                row.update(season_dict[season])
                rows_out.append(row)
        if rows_out:
            _write_rows_csv(rows_out, season_csv)
            written["metadata"].append(season_csv)

    # Text report
    report_path = meta_dir / "report.txt"
    export_report(metadata, report_path)
    written["metadata"].append(report_path)

    # ------------------------------------------------------------------
    # Individual UDs per season
    # ------------------------------------------------------------------
    for mig_name, arr in ud_dict.items():
        # Infer season from key: "<id>_<year>_<season>" or "<id>_<season>"
        parts = mig_name.split("_")
        season = parts[-1] if len(parts) > 1 else "unknown"
        tif_dir = out_dir / "UDs" / season
        tif_path = export_geotiff(arr, grid_meta, tif_dir / f"{mig_name}.tif")
        written["uds"].append(tif_path)

    # ------------------------------------------------------------------
    # Individual footprints per season
    # ------------------------------------------------------------------
    for mig_name, poly in footprint_dict.items():
        parts = mig_name.split("_")
        season = parts[-1] if len(parts) > 1 else "unknown"
        fp_season_dir = out_dir / "Footprints" / season
        gdf_single = gpd.GeoDataFrame(
            [{"mig_name": mig_name, "geometry": poly}],
            geometry="geometry",
            crs=CRS.from_user_input(grid_meta["crs"]),
        )
        shp = export_shapefiles(gdf_single, fp_season_dir, mig_name)
        written["footprints"].append(shp)

    return written


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _write_flat_csv(data: dict, out_path: Path) -> None:
    """Write a nested dict as a flat key=value CSV."""
    rows = []
    for section, content in data.items():
        if isinstance(content, dict):
            for key, val in content.items():
                rows.append({"section": section, "key": key, "value": str(val)})
        else:
            rows.append({"section": section, "key": section, "value": str(content)})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["section", "key", "value"])
        writer.writeheader()
        writer.writerows(rows)


def _write_rows_csv(rows: list[dict], out_path: Path) -> None:
    """Write a list of dicts to CSV."""
    if not rows:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
