"""
modeling.py
-----------
Corridor modeling for migration sequences. Python port of the MAPP3.x R
workflow (Wyoming Migration Initiative / Western Corridor Mapping Team),
specifically the helper scripts under ``MAPP3.x_code_workflow/functions/``:

- CalcPopGrid.R       -> :func:`create_population_grid`
- CalcSeqDistances.R  -> :func:`calc_seq_distances`
- CalcKernel.R        -> :func:`calc_kernel_ud` (Silverman href bandwidth,
                         bivariate-normal kernel, 99.99% tail cutoff)
- CalcLineBuff.R      -> :func:`calc_line_buffer`
- CalcBBMM.R          -> :func:`calc_bbmm` (FMV when ``bm_var`` is supplied;
                         estimated motion variance (EB) via Horne 2007
                         likelihood when ``bm_var=None``)
- CalcDBBMM.R         -> :func:`calc_dbbmm` — calls R's ``move`` package via
                         Rscript subprocess; falls back to BBMM if R or
                         required packages are not installed.
- CalcCTMM.R          -> :func:`calc_ctmm` — calls R's ``ctmm`` package via
                         Rscript subprocess; falls back to kernel UD if R
                         or required packages are not installed.

Kernel UD and Line Buffer numbers should be very close to R's, modulo the
fact that we evaluate the KDE directly (no SpatialPixels boundary effects).
BBMM produces output that tracks ``BBMM::brownian.bridge()`` closely but
won't be bit-for-bit identical — the bridge integration and the maximum-
likelihood variance estimator are reimplemented in pure NumPy/SciPy.

Public surface that ``main.py`` imports:

- :func:`create_population_grid`
- :func:`calc_kernel_ud`, :func:`calc_line_buffer`, :func:`calc_bbmm`
- :func:`calc_bbmm_stub`, :func:`calc_ctmm`, :func:`calc_dbbmm`
- :func:`calc_seq_distances`
- :func:`get_model_config`, :func:`run_model`, :func:`run_all_sequences`

Dependencies: numpy, scipy, pandas, rasterio, geopandas, shapely.
"""

from __future__ import annotations

import logging
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize as rio_rasterize
from rasterio.features import shapes as rio_shapes
from rasterio.transform import from_bounds
from shapely.geometry import LineString, MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
PopGrid = dict[str, Any]  # keys: transform, shape, crs


# ---------------------------------------------------------------------------
# 1. create_population_grid
# ---------------------------------------------------------------------------

def create_population_grid(
    points_gdf: gpd.GeoDataFrame,
    cell_size: float = 250,
    buffer_mult: float = 0.3,
    out_path: str | None = None,
) -> PopGrid:
    """Create an empty raster grid covering all points plus a proportional buffer.

    Equivalent to ``CalcPopGrid()`` in the Wyoming Migration Initiative MAPP3.x
    workflow: extends the bounding box of *points_gdf* by ``buffer_mult`` of
    *each dimension* (matching R's ``terra::extend(ext, c(width*m, height*m))``)
    and builds a raster at the given cell size. Writes ``PopGrid_empty.tif`` if
    ``out_path`` is given (single-band uint8 zeros — matches R's ``INT1U``).

    Parameters
    ----------
    points_gdf:
        GeoDataFrame of animal locations. Must be in a projected CRS (metres).
    cell_size:
        Raster cell size in the same units as the CRS (default 500 m). R name:
        ``cell.size``.
    buffer_mult:
        Fraction of *each dimension* added as a buffer on both sides. So a
        bbox of width W and height H grows by ``W*buffer_mult`` on left/right
        and ``H*buffer_mult`` on top/bottom. R name: ``mult4buff``.
    out_path:
        Optional file path. If provided, writes ``PopGrid_empty.tif`` here as
        single-band uint8 zeros (matches R's ``terra::writeRaster(...,
        datatype="INT1U")``).

    Returns
    -------
    dict with keys:
        ``transform``  – rasterio Affine transform
        ``shape``      – (nrows, ncols) tuple
        ``crs``        – pyproj CRS object
        ``cell_size``  – cell size used
        ``bounds``     – (minx, miny, maxx, maxy) of the grid
    """
    if points_gdf.empty:
        raise ValueError("points_gdf is empty; cannot create grid.")

    crs = points_gdf.crs
    if crs is None:
        raise ValueError("points_gdf has no CRS set.")

    minx, miny, maxx, maxy = points_gdf.total_bounds  # type: ignore[misc]
    width = maxx - minx
    height = maxy - miny

    # Match R: extend each dimension by mult4buff * that dimension on each side.
    bx = width * buffer_mult
    by = height * buffer_mult
    minx -= bx
    maxx += bx
    miny -= by
    maxy += by

    ncols = int(np.ceil((maxx - minx) / cell_size))
    nrows = int(np.ceil((maxy - miny) / cell_size))

    # Rasterio uses top-left origin; y increases downward in pixel space.
    transform = from_bounds(minx, miny, maxx, maxy, ncols, nrows)

    grid_meta: PopGrid = {
        "transform": transform,
        "shape": (nrows, ncols),
        "crs": crs,
        "cell_size": cell_size,
        "bounds": (minx, miny, maxx, maxy),
    }

    if out_path is not None:
        _write_raster(
            np.zeros((nrows, ncols), dtype=np.float32),
            grid_meta,
            out_path,
        )
        logger.info("Population grid written to %s (%d x %d cells)", out_path, nrows, ncols)

    return grid_meta


# ---------------------------------------------------------------------------
# 2. calc_kernel_ud
# ---------------------------------------------------------------------------

def _silverman_href_bandwidth(xs: np.ndarray, ys: np.ndarray) -> float:
    """Silverman reference bandwidth for bivariate KDE — matches the value
    ``adehabitatHR::kernelUD(kern='bivnorm', h='href')`` computes in R.

    h = sqrt( (var(x) + var(y)) / 2 ) * n^(-1/6)
    """
    n = len(xs)
    if n < 2:
        return 1.0
    var_x = float(np.var(xs, ddof=1))
    var_y = float(np.var(ys, ddof=1))
    return float(np.sqrt(0.5 * (var_x + var_y)) * n ** (-1.0 / 6.0))


def _kde_bivnorm_on_grid(
    xs: np.ndarray, ys: np.ndarray,
    grid_xx: np.ndarray, grid_yy: np.ndarray,
    h: float,
    batch_size: int = 200,
) -> np.ndarray:
    """Vectorised symmetric bivariate-normal KDE evaluated at every cell of
    (grid_xx, grid_yy). Returns the *unnormalised* density (rescaling to sum=1
    is done by the caller, matching R's two-step normalisation: rescale, drop
    < 99.99% tail, rescale again).

    Batches over data points to keep peak memory ≤ batch_size × n_grid_cells
    in float64.
    """
    n = len(xs)
    inv_2h2 = 1.0 / (2.0 * h * h)
    grid_flat_x = grid_xx.ravel()
    grid_flat_y = grid_yy.ravel()
    density_flat = np.zeros(grid_flat_x.size, dtype=np.float64)
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        dx = grid_flat_x[None, :] - xs[start:end, None]
        dy = grid_flat_y[None, :] - ys[start:end, None]
        sq = dx * dx + dy * dy
        density_flat += np.exp(-sq * inv_2h2).sum(axis=0)
    density = density_flat.reshape(grid_xx.shape)
    density /= (2.0 * np.pi * h * h * n)
    return density


def _apply_tail_cutoff(density: np.ndarray, keep_fraction: float = 0.9999) -> np.ndarray:
    """Zero out cells outside the ``keep_fraction`` highest-probability area
    and rescale the survivors to sum to 1. Matches R's:

        cutoff <- sort(values, decreasing=TRUE)
        vlscsum <- cumsum(cutoff)
        cutoff <- cutoff[vlscsum > keep_fraction][1]
        density[density < cutoff] <- 0
        density <- density / sum(density)
    """
    out = density.astype(np.float64, copy=True)
    total = out.sum()
    if total <= 0:
        return out.astype(np.float32)
    out /= total
    flat = out.ravel()
    sorted_desc = np.sort(flat)[::-1]
    cumsum = np.cumsum(sorted_desc)
    above = np.where(cumsum > keep_fraction)[0]
    if len(above) == 0:
        return out.astype(np.float32)
    cutoff = sorted_desc[above[0]]
    out[out < cutoff] = 0.0
    s = out.sum()
    if s > 0:
        out /= s
    return out.astype(np.float32)


def _footprint_from_density(
    density: np.ndarray, contour: float
) -> tuple[np.ndarray, float]:
    """Build the binary footprint raster (uint8 0/1) at the given probability
    contour, matching R's:

        cutoff <- sort(values, decreasing=TRUE)
        cutoff <- cutoff[cumsum(cutoff) > contour/100][1]
        footprint <- ifelse(density >= cutoff, 1, 0)

    Returns ``(footprint_uint8, cutoff)``.
    """
    flat = density.ravel()
    sorted_desc = np.sort(flat)[::-1]
    cumsum = np.cumsum(sorted_desc)
    threshold = contour / 100.0
    above = np.where(cumsum > threshold)[0]
    if len(above) == 0:
        return np.zeros_like(density, dtype=np.uint8), 0.0
    cutoff = float(sorted_desc[above[0]])
    fp = (density >= cutoff).astype(np.uint8)
    return fp, cutoff


def _subgrid_for_extent(
    pop_grid: PopGrid,
    xs: np.ndarray,
    ys: np.ndarray,
    mult4buff: float,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
    """Compute the cell-centre coordinate arrays for a subgrid that wraps the
    bounding box of (xs, ys) extended by ``mult4buff`` of each dimension,
    aligned to the population grid's cells.

    Returns ``(grid_xx, grid_yy, (row0, row1, col0, col1))`` where row0..row1
    and col0..col1 are inclusive index ranges within the full pop grid (so the
    caller can paste the result back).
    """
    transform = pop_grid["transform"]
    nrows, ncols = pop_grid["shape"]
    minx, miny, maxx, maxy = xs.min(), ys.min(), xs.max(), ys.max()
    bx = (maxx - minx) * mult4buff
    by = (maxy - miny) * mult4buff
    minx -= bx; maxx += bx; miny -= by; maxy += by

    # Convert spatial bounds to pixel indices within the pop grid.
    # transform.a = cell width (>0), transform.e = -cell height (<0)
    col0 = max(0, int(np.floor((minx - transform.c) / transform.a)))
    col1 = min(ncols - 1, int(np.ceil((maxx - transform.c) / transform.a)) - 1)
    # For rows: y decreases as row index increases (e is negative).
    row0 = max(0, int(np.floor((maxy - transform.f) / transform.e)))
    row1 = min(nrows - 1, int(np.ceil((miny - transform.f) / transform.e)) - 1)
    if col1 < col0 or row1 < row0:
        # Degenerate: a single cell.
        col0 = max(0, min(col0, ncols - 1))
        col1 = col0
        row0 = max(0, min(row0, nrows - 1))
        row1 = row0

    col_centres = np.arange(col0, col1 + 1) + 0.5
    row_centres = np.arange(row0, row1 + 1) + 0.5
    sub_xs = transform.c + col_centres * transform.a
    sub_ys = transform.f + row_centres * transform.e
    grid_xx, grid_yy = np.meshgrid(sub_xs, sub_ys)
    return grid_xx, grid_yy, (row0, row1, col0, col1)


def calc_kernel_ud(
    seq_gdf: gpd.GeoDataFrame,
    seq_name: str,
    pop_grid: PopGrid,
    smooth_param: float | None = None,
    contour: float = 99,
    mult4buff: float = 0.3,
    subsample: int | None = None,
    date_col: str = "date",
    ud_dir: str | None = None,
    footprint_dir: str | None = None,
) -> tuple[np.ndarray, Polygon | MultiPolygon, dict[str, Any]]:
    """Kernel utilization distribution matching ``CalcKernel()`` from MAPP3.x.

    Uses bivariate-normal KDE with Silverman ``href`` bandwidth (the default in
    ``adehabitatHR::kernelUD(kern='bivnorm', h='href')``) on a subgrid wrapping
    the sequence's bounding box plus a ``mult4buff`` buffer on each dimension.
    Applies R's two-step normalisation: rescale to sum 1, zero cells outside
    the 99.99% tail, rescale again. The footprint is then built from the
    user-supplied ``contour`` (default 99%).

    Parameters
    ----------
    seq_gdf:
        Sequence point GeoDataFrame. Must have a projected (metre) CRS and a
        geometry column of POINTS.
    seq_name:
        Sequence identifier used in metadata and output filenames.
    pop_grid:
        Grid metadata dict from :func:`create_population_grid`.
    smooth_param:
        Bandwidth in CRS units (metres). ``None`` (the default) selects the
        Silverman href bandwidth, matching R's ``h='href'``.
    contour:
        Probability contour (1–99.999) used to build the footprint polygon.
    mult4buff:
        Per-dimension extent buffer for the subgrid (matches R param of the
        same name).
    subsample:
        If int, randomly subsample this many points per Julian day (matches
        R's ``slice_sample`` per ``yr_jul`` grouping).
    date_col:
        Timestamp column on ``seq_gdf``.
    ud_dir, footprint_dir:
        If set, write ``<dir>/<seq_name>.tif`` for the UD (float32) and
        footprint (uint8). Matches R's ``UD.fldr`` / ``Footprint.fldr``.

    Returns
    -------
    (ud_raster, footprint_polygon, metadata)

    where ``ud_raster`` is the full-pop-grid UD as a float32 ndarray,
    ``footprint_polygon`` is a Shapely geom, and ``metadata`` is the row from
    R's ``result.tbl`` (keys ``seq_name``, ``kernel_smooth_param``, ...).
    """
    import datetime as _dt
    if seq_gdf.empty:
        raise ValueError(f"Sequence '{seq_name}' has no points.")

    start_time = _dt.datetime.now()
    nrows, ncols = pop_grid["shape"]

    # Pull and (optionally) subsample data.
    work = seq_gdf.copy()
    if date_col in work.columns:
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work = work.dropna(subset=[date_col]).sort_values(date_col)

    if subsample is not None and date_col in work.columns:
        work = work.assign(_yr_jul=work[date_col].dt.strftime("%Y_%j"))
        work = (
            work.groupby("_yr_jul", group_keys=False, sort=False)
                .apply(lambda g: g.sample(min(len(g), int(subsample)), replace=False))
        )
        # pandas >= 2.2 excludes the grouping column from the apply result, so
        # the old chained `.drop(columns="_yr_jul")` raised KeyError. Drop
        # defensively (errors="ignore") — works whether or not the column
        # survived the groupby.
        work = work.drop(columns="_yr_jul", errors="ignore").sort_values(date_col)

    xs = work.geometry.x.to_numpy(dtype=np.float64)
    ys = work.geometry.y.to_numpy(dtype=np.float64)
    n_locs = len(xs)

    def _short_metadata(error: str) -> dict[str, Any]:
        n_days = int(work[date_col].dt.dayofyear.nunique()) if date_col in work.columns and n_locs > 0 else 0
        return {
            "seq_name": seq_name,
            "kernel_smooth_param": np.nan,
            "grid_size": np.nan,
            "grid_cell_size": pop_grid.get("cell_size"),
            "date_created": _dt.datetime.now().isoformat(timespec="seconds"),
            "execution_time_min": round((_dt.datetime.now() - start_time).total_seconds() / 60.0, 2),
            "num_locs": n_locs,
            "start_date": str(work[date_col].min()) if date_col in work.columns and n_locs > 0 else "",
            "end_date": str(work[date_col].max()) if date_col in work.columns and n_locs > 0 else "",
            "num_days": n_days,
            "errors": error,
        }

    if n_locs < 5:
        return (
            np.zeros((nrows, ncols), dtype=np.float32),
            Polygon(),
            _short_metadata("Less than 5 points."),
        )

    # Build subgrid wrapping the seq + mult4buff buffer (matches R's terra::extend).
    grid_xx, grid_yy, (row0, row1, col0, col1) = _subgrid_for_extent(pop_grid, xs, ys, mult4buff)

    h = float(smooth_param) if smooth_param is not None else _silverman_href_bandwidth(xs, ys)
    if h <= 0 or not np.isfinite(h):
        return (
            np.zeros((nrows, ncols), dtype=np.float32),
            Polygon(),
            _short_metadata("Bandwidth is non-positive — data may be coincident."),
        )

    density = _kde_bivnorm_on_grid(xs, ys, grid_xx, grid_yy, h)
    density = _apply_tail_cutoff(density, keep_fraction=0.9999)

    # Place subgrid back into a full-pop-grid float32 array of zeros.
    ud_full = np.zeros((nrows, ncols), dtype=np.float32)
    ud_full[row0:row1 + 1, col0:col1 + 1] = density.astype(np.float32)

    # Footprint at user contour.
    fp_raster, _cutoff = _footprint_from_density(density.astype(np.float64), contour=contour)
    fp_full = np.zeros((nrows, ncols), dtype=np.uint8)
    fp_full[row0:row1 + 1, col0:col1 + 1] = fp_raster

    # Optional disk writes (UD.fldr / Footprint.fldr).
    if ud_dir is not None:
        from pathlib import Path
        Path(ud_dir).mkdir(parents=True, exist_ok=True)
        _write_raster(ud_full, pop_grid, str(Path(ud_dir) / f"{seq_name}.tif"))
    if footprint_dir is not None:
        from pathlib import Path
        Path(footprint_dir).mkdir(parents=True, exist_ok=True)
        _write_raster_uint8(fp_full, pop_grid, str(Path(footprint_dir) / f"{seq_name}.tif"))

    # Footprint polygon (for in-memory consumers — population merging etc.).
    footprint_polygon = _polygon_from_uint8_mask(fp_full, pop_grid)

    n_days = int(work[date_col].dt.dayofyear.nunique()) if date_col in work.columns else 0
    metadata = {
        "seq_name": seq_name,
        "kernel_smooth_param": round(h, 4),
        "grid_size": int(density.size),
        "grid_cell_size": pop_grid.get("cell_size"),
        "date_created": _dt.datetime.now().isoformat(timespec="seconds"),
        "execution_time_min": round((_dt.datetime.now() - start_time).total_seconds() / 60.0, 2),
        "num_locs": n_locs,
        "start_date": str(work[date_col].min()) if date_col in work.columns else "",
        "end_date": str(work[date_col].max()) if date_col in work.columns else "",
        "num_days": n_days,
        "errors": "None",
    }
    logger.info(
        "Kernel UD computed for '%s': n=%d, h=%.2f m, contour=%d%%",
        seq_name, n_locs, h, contour,
    )
    return ud_full, footprint_polygon, metadata


# ---------------------------------------------------------------------------
# 3. calc_line_buffer
# ---------------------------------------------------------------------------

def calc_line_buffer(
    seq_gdf: gpd.GeoDataFrame,
    seq_name: str,
    buff_distance: float = 300,
    pop_grid: PopGrid | None = None,
    footprint_dir: str | None = None,
) -> tuple[np.ndarray | None, Polygon | MultiPolygon, dict[str, Any]]:
    """Buffer the animal's movement path by ``buff_distance`` metres.

    Matches ``CalcLineBuff()`` from MAPP3.x: sorts points by date, connects
    consecutive points as line segments, buffers each by ``buff_distance``,
    unions, and rasterises onto the population grid (uint8, 1=inside / 0=out).

    Parameters
    ----------
    seq_gdf:
        Sequence GeoDataFrame (projected CRS, metres).
    seq_name:
        Sequence identifier — used in logs and as the output filename stem.
    buff_distance:
        Buffer radius in CRS units (default 300 m; matches the call site in
        ``code2run.R``).
    pop_grid:
        Grid metadata dict from :func:`create_population_grid`. If ``None``,
        no raster is produced (polygon only).
    footprint_dir:
        If set, writes ``<footprint_dir>/<seq_name>.tif`` (uint8). Matches R's
        ``Footprint.fldr``.

    Returns
    -------
    (footprint_raster, footprint_polygon, metadata)
    """
    import datetime as _dt
    if seq_gdf.empty:
        raise ValueError(f"Sequence '{seq_name}' has no points.")

    start_time = _dt.datetime.now()
    work = seq_gdf.copy()
    date_col = "date"
    if date_col in work.columns:
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work = work.dropna(subset=[date_col]).sort_values(date_col)
    n_locs = len(work)

    def _short_metadata(error: str) -> dict[str, Any]:
        return {
            "seq_name": seq_name,
            "buff_distance": buff_distance,
            "grid_cell_size": pop_grid.get("cell_size") if pop_grid else None,
            "date_created": _dt.datetime.now().isoformat(timespec="seconds"),
            "execution_time_min": round((_dt.datetime.now() - start_time).total_seconds() / 60.0, 2),
            "num_locs": n_locs,
            "start_date": str(work[date_col].min()) if date_col in work.columns and n_locs > 0 else "",
            "end_date": str(work[date_col].max()) if date_col in work.columns and n_locs > 0 else "",
            "num_days": int(work[date_col].dt.dayofyear.nunique()) if date_col in work.columns and n_locs > 0 else 0,
            "errors": error,
        }

    if n_locs < 2:
        # Single-point fallback — buffer the lone point (R returns an error here,
        # but a single buffered disc is still useful for downstream merging).
        if n_locs == 1:
            footprint: Polygon | MultiPolygon = work.geometry.iloc[0].buffer(buff_distance)
        else:
            footprint = Polygon()
        if pop_grid is not None:
            nrows, ncols = pop_grid["shape"]
            ud_raster = _rasterize_polygon(footprint, pop_grid, nrows, ncols).astype(np.uint8)
        else:
            ud_raster = None
        return ud_raster, footprint, _short_metadata("Only 1 point in sequence. No footprint was written out.")

    coords = list(zip(work.geometry.x, work.geometry.y))
    line = LineString(coords)
    footprint = line.buffer(buff_distance)
    if pop_grid is not None:
        nrows, ncols = pop_grid["shape"]
        ud_raster = _rasterize_polygon(footprint, pop_grid, nrows, ncols).astype(np.uint8)
    else:
        ud_raster = None

    # Optional disk write — matches CalcLineBuff's Footprint.fldr behaviour.
    if footprint_dir is not None and pop_grid is not None and ud_raster is not None:
        from pathlib import Path
        Path(footprint_dir).mkdir(parents=True, exist_ok=True)
        _write_raster_uint8(ud_raster, pop_grid, str(Path(footprint_dir) / f"{seq_name}.tif"))

    logger.info(
        "Line buffer computed for '%s': distance=%.1f m, area=%.2f km², n=%d",
        seq_name, buff_distance, footprint.area / 1e6, n_locs,
    )
    metadata = {
        "seq_name": seq_name,
        "buff_distance": buff_distance,
        "numb_cells": int(ud_raster.sum()) if ud_raster is not None else None,
        "grid_cell_size": pop_grid.get("cell_size") if pop_grid else None,
        "date_created": _dt.datetime.now().isoformat(timespec="seconds"),
        "execution_time_min": round((_dt.datetime.now() - start_time).total_seconds() / 60.0, 2),
        "num_locs": n_locs,
        "start_date": str(work[date_col].min()) if date_col in work.columns else "",
        "end_date": str(work[date_col].max()) if date_col in work.columns else "",
        "num_days": int(work[date_col].dt.dayofyear.nunique()) if date_col in work.columns else 0,
        "errors": "None",
    }
    return ud_raster, footprint, metadata


# ---------------------------------------------------------------------------
# 4. calc_bbmm_stub
# ---------------------------------------------------------------------------

def _estimate_brownian_motion_variance(
    xs: np.ndarray,
    ys: np.ndarray,
    time_lag_min: np.ndarray,
    location_error: np.ndarray,
    max_lag_min: float,
) -> float:
    """Maximum-likelihood estimate of Brownian motion variance.

    Follows Horne et al. (2007) / the ``BBMM::brownian.motion.variance``
    estimator: at each interior triplet ``(i, i+1, i+2)`` whose two segments
    both fit within ``max_lag_min``, the residual of the middle point from
    the straight-line interpolation between the outer two is bivariate normal
    with variance ``v = t_total * alpha * (1-alpha) * sigma^2 + locerr terms``.
    The likelihood is minimised over sigma^2 with :func:`scipy.optimize.minimize_scalar`.
    """
    from scipy.optimize import minimize_scalar

    n = len(xs)
    if n < 3:
        raise ValueError("Need at least 3 points to estimate BM variance")

    sq_list: list[float] = []
    loc_var_list: list[float] = []
    coef_list: list[float] = []
    for i in range(n - 2):
        lag1 = time_lag_min[i]
        lag2 = time_lag_min[i + 1]
        if lag1 <= 0 or lag2 <= 0 or lag1 > max_lag_min or lag2 > max_lag_min:
            continue
        t_total = lag1 + lag2
        alpha = lag1 / t_total
        mu_x = xs[i] + alpha * (xs[i + 2] - xs[i])
        mu_y = ys[i] + alpha * (ys[i + 2] - ys[i])
        sq = (xs[i + 1] - mu_x) ** 2 + (ys[i + 1] - mu_y) ** 2
        loc_var = (
            (1 - alpha) ** 2 * location_error[i] ** 2
            + location_error[i + 1] ** 2
            + alpha ** 2 * location_error[i + 2] ** 2
        )
        coef = t_total * alpha * (1.0 - alpha)
        sq_list.append(sq)
        loc_var_list.append(loc_var)
        coef_list.append(coef)

    if not sq_list:
        raise ValueError("No valid triplets for variance estimation")

    sq_arr = np.array(sq_list, dtype=np.float64)
    loc_var_arr = np.array(loc_var_list, dtype=np.float64)
    coef_arr = np.array(coef_list, dtype=np.float64)

    def neg_log_lik(sigma2: float) -> float:
        # 2-D bivariate-normal negative log-likelihood (matches BBMM's
        # brownian.motion.variance): each coordinate is N(0, v) with the SAME
        # variance v, so the joint −loglik per triplet is
        #   log(v) + (dx²+dy²)/(2v)   [constants dropped].
        # The data term is sq/(2v), NOT sq/v — using sq/v double-weights the
        # residual and biases the estimated motion variance high (over-diffuse
        # UDs). sq_arr already holds dx²+dy².
        v = coef_arr * sigma2 + loc_var_arr
        if np.any(v <= 0):
            return 1e30
        return float(np.sum(np.log(v) + sq_arr / (2.0 * v)))

    result = minimize_scalar(neg_log_lik, bounds=(1e-6, 1e9), method="bounded")
    return float(result.x)


def _bbmm_bridge_accumulate(
    xs: np.ndarray,
    ys: np.ndarray,
    time_lag_min: np.ndarray,
    grid_x_flat: np.ndarray,
    grid_y_flat: np.ndarray,
    bm_var: float,
    location_error: np.ndarray,
    max_lag_min: float,
    time_step_min: float,
) -> tuple[np.ndarray, float]:
    """Accumulate the bridge integrand across every segment whose lag <= max_lag.

    Returns ``(unnormalised_density_flat, T_total_minutes)``. Caller normalises.

    For each segment ``(i, i+1)``:
      mu(α) = x[i] + α (x[i+1] - x[i])
      σ²(α) = lag·α(1-α)·BMvar + (1-α)²·locerr[i]² + α²·locerr[i+1]²
      θ     = (1/(2π σ²)) · exp(-((gx-μx)²+(gy-μy)²)/(2σ²))
    integrated over α ∈ [0, 1] in steps of time_step_min/lag.
    """
    n = len(xs)
    out = np.zeros(grid_x_flat.size, dtype=np.float64)
    t_total = 0.0
    for i in range(n - 1):
        lag = float(time_lag_min[i])
        if lag <= 0.0 or lag > max_lag_min:
            continue
        t_total += lag
        n_steps = int(np.floor(lag / time_step_min)) + 1
        alphas = np.arange(n_steps) * time_step_min / lag
        alphas = np.clip(alphas, 0.0, 1.0)
        mu_xs = xs[i] + alphas * (xs[i + 1] - xs[i])
        mu_ys = ys[i] + alphas * (ys[i + 1] - ys[i])
        sigma2s = (
            lag * alphas * (1.0 - alphas) * bm_var
            + (1.0 - alphas) ** 2 * location_error[i] ** 2
            + alphas ** 2 * location_error[i + 1] ** 2
        )
        for k in range(n_steps):
            s2 = float(sigma2s[k])
            if s2 <= 0.0:
                continue
            dx = grid_x_flat - mu_xs[k]
            dy = grid_y_flat - mu_ys[k]
            out += (1.0 / (2.0 * np.pi * s2)) * np.exp(-(dx * dx + dy * dy) / (2.0 * s2))
    return out, t_total


def calc_bbmm(
    seq_gdf: gpd.GeoDataFrame,
    seq_name: str,
    pop_grid: PopGrid,
    bm_var: float | None = None,
    location_error: float = 20.0,
    max_lag_hours: float = 8.0,
    contour: float = 99.0,
    time_step_min: float = 5.0,
    mult4buff: float = 0.3,
    date_col: str = "date",
    ud_dir: str | None = None,
    footprint_dir: str | None = None,
    bm_var_fix_rate_threshold_hours: float | None = None,
) -> tuple[np.ndarray, Polygon | MultiPolygon, dict[str, Any]]:
    """Brownian Bridge Movement Model — port of ``CalcBBMM()`` from MAPP3.x.

    Supports the two R modes:
      - ``bm_var=None`` → estimated Brownian motion variance (EB) via Horne (2007) MLE.
      - ``bm_var=<float>`` → forced motion variance (FMV).

    Conditional FMV-by-fix-rate (adapted from Chloe's CB_MAPP workflow):
      - ``bm_var_fix_rate_threshold_hours=<float>`` together with a non-None
        ``bm_var`` makes the forced value *conditional* on this sequence's fix
        rate. If the **median** gap between consecutive fixes is **greater than**
        the threshold (coarse data), the supplied ``bm_var`` is used (FMV);
        otherwise the variance is estimated from the data (EB). Chloe sources the
        fix interval per-collar from a metadata CSV; here it is derived per
        sequence from the timestamps (closer to Jaffe's data-driven approach).
        Ignored when ``bm_var`` is None or the threshold is None.

    Time lags are computed in minutes between consecutive fixes after sorting by
    ``date_col``. Sequences with > 1/3 of steps exceeding ``max_lag_hours`` are
    skipped with an error in the metadata, as are sequences with < 4 fixes.

    The bridge is integrated at ``time_step_min``-minute steps along each segment.
    Output normalisation (drop < 99.99% tail then rescale) and contour
    extraction match :func:`calc_kernel_ud`.
    """
    import datetime as _dt
    if seq_gdf.empty:
        raise ValueError(f"Sequence '{seq_name}' has no points.")

    start_time = _dt.datetime.now()
    nrows, ncols = pop_grid["shape"]
    max_lag_min = max_lag_hours * 60.0

    work = seq_gdf.copy()
    if date_col in work.columns:
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work = work.dropna(subset=[date_col]).sort_values(date_col)
    xs = work.geometry.x.to_numpy(dtype=np.float64)
    ys = work.geometry.y.to_numpy(dtype=np.float64)
    n_locs = len(xs)
    locerr = np.full(n_locs, float(location_error))

    def _short_metadata(error: str) -> dict[str, Any]:
        n_days = int(work[date_col].dt.dayofyear.nunique()) if date_col in work.columns and n_locs > 0 else 0
        return {
            "seq_name": seq_name,
            "brownian_motion_variance": np.nan,
            "grid_size": np.nan,
            "grid_cell_size": pop_grid.get("cell_size"),
            "date_created": _dt.datetime.now().isoformat(timespec="seconds"),
            "execution_time_min": round((_dt.datetime.now() - start_time).total_seconds() / 60.0, 2),
            "num_locs": n_locs,
            "start_date": str(work[date_col].min()) if date_col in work.columns and n_locs > 0 else "",
            "end_date": str(work[date_col].max()) if date_col in work.columns and n_locs > 0 else "",
            "num_days": n_days,
            "errors": error,
        }

    if n_locs < 4:
        return (
            np.zeros((nrows, ncols), dtype=np.float32),
            Polygon(),
            _short_metadata("Less than 4 points."),
        )

    # Time lag in minutes between consecutive timestamps. Use total_seconds on
    # the timedelta so this is independent of the datetime64 resolution —
    # `astype("int64")` is NOT safe here: pandas 2.x may store timestamps at
    # microsecond (or other) resolution, which silently made the lags 1000x too
    # small and collapsed the BMvar term (the bridge then ignored motion
    # variance and was dominated by location error).
    t_secs = (work[date_col] - work[date_col].iloc[0]).dt.total_seconds().to_numpy(dtype=np.float64)
    time_lag_min = np.diff(t_secs) / 60.0

    # R: if > 1/3 of steps have lag > max.lag → bail with error metadata.
    if np.mean(time_lag_min > max_lag_min) > 1.0 / 3.0:
        return (
            np.zeros((nrows, ncols), dtype=np.float32),
            Polygon(),
            _short_metadata(
                f"More than 1/3 of steps have time gaps > max_lag={max_lag_hours}h. "
                "BBMM probably won't work."
            ),
        )

    # Conditional FMV-by-fix-rate (Chloe-style): when a forced bm_var AND a
    # threshold are both supplied, only force the variance for coarse sequences
    # (median fix gap > threshold). Fine-fix sequences fall back to EB.
    effective_bm_var = bm_var
    variance_mode = "FMV" if bm_var is not None else "EB"
    if bm_var is not None and bm_var_fix_rate_threshold_hours is not None:
        median_gap_hours = float(np.median(time_lag_min)) / 60.0 if time_lag_min.size else 0.0
        if median_gap_hours > float(bm_var_fix_rate_threshold_hours):
            effective_bm_var = bm_var               # coarse data → forced value
            variance_mode = "FMV (conditional)"
        else:
            effective_bm_var = None                 # fine data → estimate (EB)
            variance_mode = "EB (conditional)"

    # EB mode: estimate motion variance from data; FMV mode: use given value.
    try:
        if effective_bm_var is None:
            sigma2_hat = _estimate_brownian_motion_variance(
                xs, ys, time_lag_min, locerr, max_lag_min
            )
        else:
            sigma2_hat = float(effective_bm_var)
    except Exception as exc:
        return (
            np.zeros((nrows, ncols), dtype=np.float32),
            Polygon(),
            _short_metadata(f"BMvar estimation failed: {exc}"),
        )

    # Build the subgrid wrapping the seq + mult4buff buffer.
    grid_xx, grid_yy, (row0, row1, col0, col1) = _subgrid_for_extent(pop_grid, xs, ys, mult4buff)
    grid_x_flat = grid_xx.ravel()
    grid_y_flat = grid_yy.ravel()

    int_flat, t_total = _bbmm_bridge_accumulate(
        xs, ys, time_lag_min, grid_x_flat, grid_y_flat,
        bm_var=sigma2_hat, location_error=locerr,
        max_lag_min=max_lag_min, time_step_min=time_step_min,
    )
    if t_total <= 0:
        return (
            np.zeros((nrows, ncols), dtype=np.float32),
            Polygon(),
            _short_metadata("No segments survived the max.lag filter."),
        )

    density = (int_flat / t_total).reshape(grid_xx.shape)
    density = _apply_tail_cutoff(density, keep_fraction=0.9999)

    ud_full = np.zeros((nrows, ncols), dtype=np.float32)
    ud_full[row0:row1 + 1, col0:col1 + 1] = density.astype(np.float32)

    fp_raster, _ = _footprint_from_density(density.astype(np.float64), contour=contour)
    fp_full = np.zeros((nrows, ncols), dtype=np.uint8)
    fp_full[row0:row1 + 1, col0:col1 + 1] = fp_raster

    if ud_dir is not None:
        from pathlib import Path
        Path(ud_dir).mkdir(parents=True, exist_ok=True)
        _write_raster(ud_full, pop_grid, str(Path(ud_dir) / f"{seq_name}.tif"))
    if footprint_dir is not None:
        from pathlib import Path
        Path(footprint_dir).mkdir(parents=True, exist_ok=True)
        _write_raster_uint8(fp_full, pop_grid, str(Path(footprint_dir) / f"{seq_name}.tif"))

    footprint_polygon = _polygon_from_uint8_mask(fp_full, pop_grid)

    n_days = int(work[date_col].dt.dayofyear.nunique()) if date_col in work.columns else 0
    metadata = {
        "seq_name": seq_name,
        "brownian_motion_variance": round(sigma2_hat, 2),
        "grid_size": int(density.size),
        "grid_cell_size": pop_grid.get("cell_size"),
        "date_created": _dt.datetime.now().isoformat(timespec="seconds"),
        "execution_time_min": round((_dt.datetime.now() - start_time).total_seconds() / 60.0, 2),
        "num_locs": n_locs,
        "start_date": str(work[date_col].min()) if date_col in work.columns else "",
        "end_date": str(work[date_col].max()) if date_col in work.columns else "",
        "num_days": n_days,
        "variance_mode": variance_mode,
        "errors": "None",
    }
    logger.info(
        "BBMM computed for '%s': n=%d, BMvar=%.2f m², mode=%s, contour=%d%%",
        seq_name, n_locs, sigma2_hat, variance_mode, contour,
    )
    return ud_full, footprint_polygon, metadata


def calc_bbmm_stub(
    seq_gdf: gpd.GeoDataFrame,
    seq_name: str,
    pop_grid: PopGrid,
    config: dict[str, Any],
) -> tuple[np.ndarray, Polygon | MultiPolygon, dict[str, Any]]:
    """Backwards-compatible wrapper: unpacks the legacy ``config`` dict into
    :func:`calc_bbmm`'s keyword arguments. Kept because ``main.py`` imports
    ``calc_bbmm_stub`` by name."""
    return calc_bbmm(
        seq_gdf,
        seq_name,
        pop_grid,
        bm_var=config.get("bm_var"),
        location_error=config.get("location_error", 20.0),
        max_lag_hours=config.get("max_lag", config.get("max_lag_hours", 8.0)),
        contour=config.get("contour", 99.0),
        time_step_min=config.get("time_step", config.get("time_step_min", 5.0)),
        mult4buff=config.get("mult4buff", 0.3),
        ud_dir=config.get("ud_dir"),
        footprint_dir=config.get("footprint_dir"),
        bm_var_fix_rate_threshold_hours=config.get("bm_var_fix_rate_threshold_hours"),
    )


# ---------------------------------------------------------------------------
# 5. calc_ctmm (real CTMM via R subprocess, kernel UD fallback)
# ---------------------------------------------------------------------------

def _find_rscript() -> str | None:
    """Locate an Rscript executable that has the required CTMM packages.

    Search order:
      1. RSCRIPT_PATH env var (user override — full path to Rscript executable)
      2. R_HOME env var  (+ /bin/Rscript)
      3. System PATH
      4. Windows registry (R registers its install path there)
      5. Common filesystem locations (AppData, Program Files, ~/R)

    Among all found candidates, the first whose library contains the six
    required packages wins.  Falls back to the newest if none qualifies.
    """
    import shutil
    import os
    import subprocess as _sp

    candidates: list[str] = []

    def _add(p: str) -> None:
        if p and os.path.isfile(p) and p not in candidates:
            candidates.append(p)

    _add(os.environ.get("RSCRIPT_PATH", ""))

    r_home = os.environ.get("R_HOME", "")
    if r_home:
        _add(os.path.join(r_home, "bin", "Rscript.exe"))
        _add(os.path.join(r_home, "bin", "Rscript"))

    rs = shutil.which("Rscript")
    if rs:
        _add(rs)

    if os.name == "nt":
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\R-core\R") as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                        _add(os.path.join(install_path, "bin", "Rscript.exe"))
                except OSError:
                    pass
        except ImportError:
            pass

    search_roots = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "R"),
        r"C:\Program Files\R",
        r"C:\Program Files (x86)\R",
        os.path.expanduser("~/R"),
    ]
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root), reverse=True):
            _add(os.path.join(root, entry, "bin", "Rscript.exe"))

    if not candidates:
        return None

    required = {"ctmm", "move", "sf", "terra", "R.utils", "jsonlite"}
    for rscript in candidates:
        try:
            out = _sp.run(
                [rscript, "-e", "cat(installed.packages()[,'Package'],sep='\\n')"],
                capture_output=True, text=True, timeout=15,
            )
            if required.issubset(set(out.stdout.splitlines())):
                return rscript
        except Exception:
            continue

    return candidates[0]


def calc_ctmm(
    seq_gdf: gpd.GeoDataFrame,
    seq_name: str,
    pop_grid: PopGrid,
    config: dict[str, Any],
) -> tuple[np.ndarray, Polygon | MultiPolygon, dict[str, Any]]:
    """Continuous-Time Movement Model via R's ``ctmm`` package.

    Calls ``ctmm_bridge.R`` via Rscript subprocess, matching CalcCTMM.R from
    WMI MAPP3.x: ctmm.guess -> ctmm.select (AIC/BIC/AICc, pHREML) ->
    ctmm::occurrence on the population subgrid -> 99.99% tail cutoff ->
    contour-based footprint.

    Falls back to kernel UD if R or required R packages are not available.
    """
    import json
    import os
    import subprocess
    import tempfile

    info_criteria = config.get("info_criteria", "AIC")
    contour = config.get("contour", 99)
    mult4buff = config.get("mult4buff", 0.3)
    max_timeout = config.get("max_timeout", 600)

    user_rscript = config.get("rscript_path", "")
    if user_rscript and os.path.isfile(user_rscript):
        rscript = user_rscript
    else:
        rscript = _find_rscript()
    if rscript is None:
        warnings.warn(
            f"[{seq_name}] R/Rscript not found on this system. "
            "Falling back to kernel UD approximation. Install R and the "
            "ctmm, move, sf, terra, R.utils, jsonlite packages for real CTMM.",
            UserWarning,
            stacklevel=2,
        )
        logger.warning("CTMM: Rscript not found — falling back to kernel UD for '%s'.", seq_name)
        ud, fp, meta = calc_kernel_ud(
            seq_gdf, seq_name, pop_grid,
            smooth_param=config.get("smooth_param"),
            contour=contour, mult4buff=mult4buff,
            ud_dir=config.get("ud_dir"),
            footprint_dir=config.get("footprint_dir"),
        )
        meta["method_note"] = "CTMM fallback — R not found; produced via kernel UD."
        return ud, fp, meta

    bridge_r = os.path.join(os.path.dirname(__file__), "ctmm_bridge.R")

    with tempfile.TemporaryDirectory(prefix="ctmm_") as tmpdir:
        # Write sequence points as CSV
        csv_path = os.path.join(tmpdir, "seq_points.csv")
        coords = np.array([(g.x, g.y) for g in seq_gdf.geometry])
        ts_col = "date" if "date" in seq_gdf.columns else "timestamp"
        timestamps = seq_gdf[ts_col] if ts_col in seq_gdf.columns else seq_gdf.iloc[:, 0]
        csv_df = pd.DataFrame({
            "x_proj": coords[:, 0],
            "y_proj": coords[:, 1],
            "timestamp": pd.to_datetime(timestamps).dt.strftime("%Y-%m-%d %H:%M:%S"),
        })
        csv_df.to_csv(csv_path, index=False)

        # Write pop grid as a temp tif
        popgrid_path = os.path.join(tmpdir, "popgrid.tif")
        nrows, ncols = pop_grid["shape"]
        with rasterio.open(
            popgrid_path, "w", driver="GTiff",
            height=nrows, width=ncols, count=1, dtype="uint8",
            crs=pop_grid["crs"], transform=pop_grid["transform"],
        ) as dst:
            dst.write(np.zeros((nrows, ncols), dtype=np.uint8), 1)

        ud_path = os.path.join(tmpdir, f"{seq_name}.tif")
        fp_path = os.path.join(tmpdir, f"{seq_name}_fp.tif")
        meta_path = os.path.join(tmpdir, "meta.json")

        cmd = [
            rscript, "--vanilla", bridge_r,
            csv_path, popgrid_path, ud_path, fp_path,
            str(info_criteria), str(contour), str(mult4buff),
            str(max_timeout), meta_path,
        ]

        logger.info("CTMM: running Rscript for '%s' (IC=%s, contour=%s)...", seq_name, info_criteria, contour)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=max_timeout + 60,
            )
        except subprocess.TimeoutExpired:
            warnings.warn(
                f"[{seq_name}] CTMM Rscript timed out after {max_timeout + 60}s. "
                "Falling back to kernel UD.",
                UserWarning, stacklevel=2,
            )
            ud, fp, meta = calc_kernel_ud(
                seq_gdf, seq_name, pop_grid,
                smooth_param=config.get("smooth_param"),
                contour=contour, mult4buff=mult4buff,
                ud_dir=config.get("ud_dir"),
                footprint_dir=config.get("footprint_dir"),
            )
            meta["method_note"] = "CTMM fallback — Rscript timed out; produced via kernel UD."
            return ud, fp, meta

        # Check for missing R packages
        if result.returncode == 2 or "MISSING_PACKAGES:" in result.stdout:
            missing_line = [l for l in result.stdout.splitlines() if "MISSING_PACKAGES:" in l]
            missing = missing_line[0].split("MISSING_PACKAGES:")[1] if missing_line else "unknown"
            warnings.warn(
                f"[{seq_name}] CTMM requires R packages that are not installed: {missing}. "
                f"Install them in R with: install.packages(c({', '.join(repr(p) for p in missing.split(','))})). "
                "Falling back to kernel UD.",
                UserWarning, stacklevel=2,
            )
            ud, fp, meta = calc_kernel_ud(
                seq_gdf, seq_name, pop_grid,
                smooth_param=config.get("smooth_param"),
                contour=contour, mult4buff=mult4buff,
                ud_dir=config.get("ud_dir"),
                footprint_dir=config.get("footprint_dir"),
            )
            meta["method_note"] = f"CTMM fallback — missing R packages ({missing}); produced via kernel UD."
            return ud, fp, meta

        # Read metadata from R
        r_meta = {}
        if os.path.isfile(meta_path):
            with open(meta_path, "r") as f:
                r_meta = json.load(f)

        if result.returncode != 0 or r_meta.get("error", "None") != "None":
            err_msg = r_meta.get("error", result.stderr[:500] if result.stderr else "Unknown R error")
            warnings.warn(
                f"[{seq_name}] CTMM R script failed: {err_msg}. "
                "Falling back to kernel UD.",
                UserWarning, stacklevel=2,
            )
            ud, fp, meta = calc_kernel_ud(
                seq_gdf, seq_name, pop_grid,
                smooth_param=config.get("smooth_param"),
                contour=contour, mult4buff=mult4buff,
                ud_dir=config.get("ud_dir"),
                footprint_dir=config.get("footprint_dir"),
            )
            meta["method_note"] = f"CTMM fallback — R error ({err_msg}); produced via kernel UD."
            return ud, fp, meta

        # Read the UD raster produced by R
        with rasterio.open(ud_path) as src:
            ud_full = src.read(1).astype(np.float32)

        # Read the footprint raster produced by R
        with rasterio.open(fp_path) as src:
            fp_full = src.read(1).astype(np.uint8)

        # Build footprint polygon from the binary raster
        fp_shapes = list(rio_shapes(fp_full, mask=(fp_full == 1), transform=pop_grid["transform"]))
        if fp_shapes:
            polys = [shape(s) for s, v in fp_shapes if v == 1]
            footprint_polygon = unary_union(polys) if len(polys) > 1 else polys[0]
        else:
            footprint_polygon = Polygon()

        # Copy UD/footprint tifs to the output dirs if requested
        ud_dir = config.get("ud_dir")
        fp_dir = config.get("footprint_dir")
        if ud_dir:
            import shutil
            os.makedirs(ud_dir, exist_ok=True)
            shutil.copy2(ud_path, os.path.join(ud_dir, f"{seq_name}.tif"))
        if fp_dir:
            import shutil
            os.makedirs(fp_dir, exist_ok=True)
            shutil.copy2(fp_path, os.path.join(fp_dir, f"{seq_name}.tif"))

        metadata: dict[str, Any] = {
            "method": "CTMM",
            "ctmm_model": r_meta.get("ctmm_model", "unknown"),
            "info_criteria": info_criteria,
            "contour": contour,
            "mult4buff": mult4buff,
            "n_fixes": len(seq_gdf),
            "grid_size": int(r_meta.get("grid_size", 0)),
            "grid_cell_size": float(r_meta.get("grid_cell_size", pop_grid["cell_size"])),
            "execution_time_s": float(r_meta.get("execution_time_s", 0)),
        }
        logger.info(
            "CTMM completed for '%s': model=%s, %.1fs",
            seq_name, metadata["ctmm_model"], metadata["execution_time_s"],
        )
        return ud_full, footprint_polygon, metadata


# ---------------------------------------------------------------------------
# 6. calc_dbbmm (real dBBMM via R subprocess, BBMM fallback)
# ---------------------------------------------------------------------------

def calc_dbbmm(
    seq_gdf: gpd.GeoDataFrame,
    seq_name: str,
    pop_grid: PopGrid,
    config: dict[str, Any],
) -> tuple[np.ndarray, Polygon | MultiPolygon, dict[str, Any]]:
    """Dynamic Brownian Bridge Movement Model via R's ``move`` package.

    Calls ``dbbmm_bridge.R`` via Rscript subprocess, matching CalcDBBMM.R
    from WMI MAPP3.x: move::brownian.bridge.dyn with margin/window params,
    burst segmentation at max_lag, 99.99% tail cutoff, contour footprint.

    Falls back to regular BBMM if R or required R packages are not available.
    """
    import json
    import os
    import subprocess
    import tempfile

    location_error = config.get("location_error", 20.0)
    max_lag = config.get("max_lag", config.get("max_lag_hours", 8.0))
    contour = config.get("contour", 99)
    dbbmm_margin = config.get("dbbmm_margin", 11)
    dbbmm_window = config.get("dbbmm_window", 31)
    mult4buff = config.get("mult4buff", 0.3)
    max_timeout = config.get("max_timeout", 600)

    def _fallback(reason: str):
        warnings.warn(
            f"[{seq_name}] {reason} Falling back to regular BBMM (EB).",
            UserWarning, stacklevel=3,
        )
        ud, fp, meta = calc_bbmm(
            seq_gdf, seq_name, pop_grid,
            bm_var=None,
            location_error=location_error,
            max_lag_hours=max_lag,
            contour=contour,
            time_step_min=config.get("time_step", 5.0),
            mult4buff=mult4buff,
            ud_dir=config.get("ud_dir"),
            footprint_dir=config.get("footprint_dir"),
        )
        meta["method_note"] = f"dBBMM fallback — {reason} Produced via regular BBMM (EB)."
        return ud, fp, meta

    user_rscript = config.get("rscript_path", "")
    if user_rscript and os.path.isfile(user_rscript):
        rscript = user_rscript
    else:
        rscript = _find_rscript()

    if rscript is None:
        logger.warning("dBBMM: Rscript not found — falling back to BBMM for '%s'.", seq_name)
        return _fallback(
            "R/Rscript not found. Install R and the move, sf, terra, "
            "R.utils, jsonlite packages for real dBBMM."
        )

    bridge_r = os.path.join(os.path.dirname(__file__), "dbbmm_bridge.R")

    with tempfile.TemporaryDirectory(prefix="dbbmm_") as tmpdir:
        csv_path = os.path.join(tmpdir, "seq_points.csv")
        coords = np.array([(g.x, g.y) for g in seq_gdf.geometry])
        ts_col = "date" if "date" in seq_gdf.columns else "timestamp"
        timestamps = seq_gdf[ts_col] if ts_col in seq_gdf.columns else seq_gdf.iloc[:, 0]
        csv_df = pd.DataFrame({
            "x_proj": coords[:, 0],
            "y_proj": coords[:, 1],
            "timestamp": pd.to_datetime(timestamps).dt.strftime("%Y-%m-%d %H:%M:%S"),
        })
        csv_df.to_csv(csv_path, index=False)

        popgrid_path = os.path.join(tmpdir, "popgrid.tif")
        nrows, ncols = pop_grid["shape"]
        with rasterio.open(
            popgrid_path, "w", driver="GTiff",
            height=nrows, width=ncols, count=1, dtype="uint8",
            crs=pop_grid["crs"], transform=pop_grid["transform"],
        ) as dst:
            dst.write(np.zeros((nrows, ncols), dtype=np.uint8), 1)

        ud_path = os.path.join(tmpdir, f"{seq_name}.tif")
        fp_path = os.path.join(tmpdir, f"{seq_name}_fp.tif")
        meta_path = os.path.join(tmpdir, "meta.json")

        cmd = [
            rscript, "--vanilla", bridge_r,
            csv_path, popgrid_path, ud_path, fp_path,
            str(location_error), str(max_lag), str(contour),
            str(dbbmm_margin), str(dbbmm_window),
            str(mult4buff), str(max_timeout), meta_path,
        ]

        logger.info(
            "dBBMM: running Rscript for '%s' (margin=%s, window=%s)...",
            seq_name, dbbmm_margin, dbbmm_window,
        )
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=max_timeout + 60,
            )
        except subprocess.TimeoutExpired:
            return _fallback(f"Rscript timed out after {max_timeout + 60}s.")

        if result.returncode == 2 or "MISSING_PACKAGES:" in result.stdout:
            missing_line = [l for l in result.stdout.splitlines() if "MISSING_PACKAGES:" in l]
            missing = missing_line[0].split("MISSING_PACKAGES:")[1] if missing_line else "unknown"
            return _fallback(
                f"Missing R packages ({missing}). Install them in R with: "
                f"install.packages(c({', '.join(repr(p) for p in missing.split(','))}))."
            )

        r_meta = {}
        if os.path.isfile(meta_path):
            with open(meta_path, "r") as f:
                r_meta = json.load(f)

        if result.returncode != 0 or r_meta.get("error", "None") != "None":
            err_msg = r_meta.get("error", result.stderr[:500] if result.stderr else "Unknown R error")
            return _fallback(f"R error ({err_msg}).")

        with rasterio.open(ud_path) as src:
            ud_full = src.read(1).astype(np.float32)

        with rasterio.open(fp_path) as src:
            fp_full = src.read(1).astype(np.uint8)

        fp_shapes = list(rio_shapes(fp_full, mask=(fp_full == 1), transform=pop_grid["transform"]))
        if fp_shapes:
            polys = [shape(s) for s, v in fp_shapes if v == 1]
            footprint_polygon = unary_union(polys) if len(polys) > 1 else polys[0]
        else:
            footprint_polygon = Polygon()

        ud_dir = config.get("ud_dir")
        fp_dir = config.get("footprint_dir")
        if ud_dir:
            import shutil
            os.makedirs(ud_dir, exist_ok=True)
            shutil.copy2(ud_path, os.path.join(ud_dir, f"{seq_name}.tif"))
        if fp_dir:
            import shutil
            os.makedirs(fp_dir, exist_ok=True)
            shutil.copy2(fp_path, os.path.join(fp_dir, f"{seq_name}.tif"))

        metadata: dict[str, Any] = {
            "method": "dBBMM",
            "dbb_mean_motion_variance": float(r_meta.get("dbb_mean_motion_variance", 0)),
            "location_error": location_error,
            "max_lag_hours": max_lag,
            "dbbmm_margin": dbbmm_margin,
            "dbbmm_window": dbbmm_window,
            "contour": contour,
            "mult4buff": mult4buff,
            "n_fixes": len(seq_gdf),
            "grid_size": int(r_meta.get("grid_size", 0)),
            "grid_cell_size": float(r_meta.get("grid_cell_size", pop_grid["cell_size"])),
            "execution_time_s": float(r_meta.get("execution_time_s", 0)),
        }
        logger.info(
            "dBBMM completed for '%s': mean_motion_var=%.2f, %.1fs",
            seq_name, metadata["dbb_mean_motion_variance"], metadata["execution_time_s"],
        )
        return ud_full, footprint_polygon, metadata


# ---------------------------------------------------------------------------
# 7. get_model_config
# ---------------------------------------------------------------------------

def get_model_config(
    method: str = "BBMM",
    fix_rate_hours: float | None = None,
) -> dict[str, Any]:
    """Return a default configuration dict for the requested model method.

    Parameters
    ----------
    method:
        One of ``'BBMM'``, ``'CTMM'``, ``'dBBMM'``, or ``'LineBuff'``
        (case-insensitive).
    fix_rate_hours:
        Nominal GPS fix rate in hours. When *> 12*, ``bm_var`` is set to a
        fixed value (1000) rather than ``None`` (auto-estimate), because
        auto-estimation is unreliable for coarse fix schedules. 1000 is the
        forced motion variance used by both Jaffe and Chloe for mule deer /
        bighorn (Chloe uses 1400 for elk). The R Migration Mapper itself does
        not auto-force a value (BMVar=NULL → always EB); this >12h fallback is
        a port-specific safeguard.

    Returns
    -------
    dict matching Migration Mapper App 4 config keys.
    """
    method_upper = method.upper()
    if method_upper not in {"BBMM", "CTMM", "DBBMM", "KERNEL", "LINEBUFF", "LINEBUFFER"}:
        raise ValueError(
            f"Unknown method '{method}'. "
            "Choose from: BBMM, CTMM, dBBMM, Kernel, LineBuffer."
        )

    # bm_var: None = auto-estimate; coarse fix rates need a fixed value
    bm_var: float | None = None
    if fix_rate_hours is not None and fix_rate_hours > 12:
        bm_var = 1000.0
        logger.info(
            "fix_rate_hours=%.1f > 12: setting bm_var=1000 (fixed) instead of auto-estimate.",
            fix_rate_hours,
        )

    config: dict[str, Any] = {
        # ---- identity ----
        "method": method_upper,
        # ---- computation ----
        "num_cores": 1,
        "max_timeout": 600,           # seconds per sequence before giving up
        # ---- grid / raster ----
        "mult4buff": 0.3,             # buffer multiplier for population grid
        "cell_size": 250,             # metres (default; user-overridable in Tab 3)
        # ---- BBMM / dBBMM ----
        "time_step": 5,               # minutes
        "bm_var": bm_var,             # Brownian motion variance (None = auto)
        "location_error": 20,         # metres
        "max_lag": 8,                 # hours
        "contour": 99,                # probability contour (%)
        # ---- dBBMM specific ----
        "dbbmm_margin": 3,
        "dbbmm_window": 11,
        # ---- CTMM specific ----
        "info_criteria": "AIC",       # 'AIC', 'BIC', 'AICc'
        # ---- Kernel UD ----
        "smooth_param": None,         # bandwidth (None = href, like R)
        # No subsampling by default — matches R's CalcKernel(subsample=NULL).
        # When set to N, keeps up to N fixes per year+Julian-day.
        "subsample": None,
        # ---- Line Buffer ----
        "buff_distance": 300,         # metres
    }
    return config


# ---------------------------------------------------------------------------
# 8. run_model
# ---------------------------------------------------------------------------

def run_model(
    seq_gdf: gpd.GeoDataFrame,
    method: str,
    pop_grid: PopGrid,
    config: dict[str, Any],
    seq_name: str,
) -> dict[str, Any]:
    """Dispatch to the appropriate modelling function for a single sequence.

    Parameters
    ----------
    seq_gdf:
        GeoDataFrame for the sequence.
    method:
        Model method string (``'BBMM'``, ``'CTMM'``, ``'dBBMM'``,
        ``'LineBuff'``, ``'Kernel'``).
    pop_grid:
        Grid metadata from :func:`create_population_grid`.
    config:
        Config dict from :func:`get_model_config`.
    seq_name:
        Human-readable sequence identifier.

    Returns
    -------
    dict with keys:
        ``ud_raster``        – numpy array or ``None`` (LineBuff without grid)
        ``footprint_polygon``– Shapely geometry
        ``metadata``         – dict of run parameters and provenance
    """
    method_key = method.upper()
    collected_warnings: list[str] = []

    dates = seq_gdf["date"] if "date" in seq_gdf.columns else None
    start_date = str(dates.min()) if dates is not None and len(dates) > 0 else None
    end_date = str(dates.max()) if dates is not None and len(dates) > 0 else None
    n_fixes = len(seq_gdf)

    ud_raster: np.ndarray | None = None
    footprint_polygon: Polygon | MultiPolygon
    method_metadata: dict[str, Any] = {}

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        if method_key == "BBMM":
            ud_raster, footprint_polygon, method_metadata = calc_bbmm_stub(seq_gdf, seq_name, pop_grid, config)
        elif method_key == "CTMM":
            ud_raster, footprint_polygon, method_metadata = calc_ctmm(seq_gdf, seq_name, pop_grid, config)
        elif method_key == "DBBMM":
            ud_raster, footprint_polygon, method_metadata = calc_dbbmm(seq_gdf, seq_name, pop_grid, config)
        elif method_key == "LINEBUFF":
            ud_raster, footprint_polygon, method_metadata = calc_line_buffer(
                seq_gdf,
                seq_name,
                buff_distance=config.get("buff_distance", 300),
                pop_grid=pop_grid,
                footprint_dir=config.get("footprint_dir"),
            )
        elif method_key == "KERNEL":
            ud_raster, footprint_polygon, method_metadata = calc_kernel_ud(
                seq_gdf,
                seq_name,
                pop_grid,
                smooth_param=config.get("smooth_param"),
                contour=config.get("contour", 99),
                mult4buff=config.get("mult4buff", 0.3),
                subsample=config.get("subsample"),
                ud_dir=config.get("ud_dir"),
                footprint_dir=config.get("footprint_dir"),
            )
        else:
            raise ValueError(
                f"Unknown method '{method}'. "
                "Choose from: BBMM, CTMM, dBBMM, LineBuff, Kernel."
            )

        collected_warnings.extend(str(warning.message) for warning in w)

    metadata: dict[str, Any] = {
        "seq_name": seq_name,
        "method": method_key,
        "start_date": start_date,
        "end_date": end_date,
        "n_fixes": n_fixes,
        "cell_size": config.get("cell_size"),
        "contour": config.get("contour"),
        "bm_var": config.get("bm_var"),
        "location_error": config.get("location_error"),
        "max_lag_hours": config.get("max_lag"),
        "buff_distance": config.get("buff_distance"),
        "smooth_param": config.get("smooth_param"),
        "warnings": collected_warnings,
    }
    # Merge in the per-method metadata (kernel_smooth_param, brownian_motion_variance,
    # errors, num_locs, num_days, execution_time_min, etc.) without clobbering the
    # canonical seq_name / method values.
    if method_metadata:
        for k, v in method_metadata.items():
            if k not in ("seq_name", "method"):
                metadata[k] = v

    return {
        "ud_raster": ud_raster,
        "footprint_polygon": footprint_polygon,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# 8b. calc_seq_distances — port of CalcSeqDistances.R
# ---------------------------------------------------------------------------

def calc_seq_distances(
    seq_gdf: gpd.GeoDataFrame,
    id_col: str = "mig",
) -> pd.DataFrame:
    """Maximum pairwise distance (km) per sequence id, plus aggregate stats.

    Direct port of ``CalcSeqDistances.R``. For each unique value of ``id_col``,
    computes the full pairwise distance matrix from the projected (metre)
    geometry and records the maximum. The aggregate stats (mean / sd / min /
    max of all max-distances) are appended to every row, matching R.
    """
    if seq_gdf.empty:
        return pd.DataFrame(columns=[
            "id_name", "max_dist_km",
            "mean_max_dist", "sd_max_dist", "min_max_dist", "max_max_dist",
        ])
    if id_col not in seq_gdf.columns:
        raise ValueError(f"calc_seq_distances: column '{id_col}' not in seq_gdf.")
    crs = seq_gdf.crs
    if crs is None or crs.is_geographic:
        raise ValueError("calc_seq_distances: seq_gdf must be in a projected (metre) CRS.")

    rows: list[dict[str, Any]] = []
    for uid, sub in seq_gdf.groupby(id_col, sort=False):
        xs = sub.geometry.x.to_numpy(dtype=np.float64)
        ys = sub.geometry.y.to_numpy(dtype=np.float64)
        if len(xs) < 2:
            max_d = 0.0
        else:
            # Pairwise squared distance via broadcasting.
            dx = xs[:, None] - xs[None, :]
            dy = ys[:, None] - ys[None, :]
            max_d = float(np.sqrt((dx * dx + dy * dy).max()))
        rows.append({"id_name": uid, "max_dist_km": max_d / 1000.0})

    df = pd.DataFrame(rows)
    if not df.empty:
        df["mean_max_dist"] = df["max_dist_km"].mean()
        df["sd_max_dist"] = df["max_dist_km"].std(ddof=1) if len(df) > 1 else 0.0
        df["min_max_dist"] = df["max_dist_km"].min()
        df["max_max_dist"] = df["max_dist_km"].max()
    return df


# ---------------------------------------------------------------------------
# 9. run_all_sequences
# ---------------------------------------------------------------------------

def _run_model_worker(
    args: tuple[str, gpd.GeoDataFrame, str, dict[str, Any], PopGrid],
) -> tuple[str, dict[str, Any]]:
    """Top-level worker function for ProcessPoolExecutor (must be picklable).

    GeoDataFrames pickle cleanly as long as they don't carry open Fiona file
    handles, which is true for our in-memory sequence frames — they were
    extracted via :func:`sequencing.extract_sequences` from a plain DataFrame.
    """
    seq_name, seq_gdf, method, config, pop_grid = args
    result = run_model(seq_gdf, method, pop_grid, config, seq_name)
    return seq_name, result


def run_all_sequences(
    sequences_dict: dict[str, gpd.GeoDataFrame],
    method: str,
    pop_grid: PopGrid,
    config: dict[str, Any],
    n_cores: int = 1,
) -> tuple[dict[str, dict[str, Any]], "gpd.GeoDataFrame"]:
    """Run the corridor model for every migration sequence.

    Parameters
    ----------
    sequences_dict:
        Mapping of migration name → GeoDataFrame for that sequence.
    method:
        Model method string passed to :func:`run_model`.
    pop_grid:
        Grid metadata from :func:`create_population_grid`.
    config:
        Config dict from :func:`get_model_config`.
    n_cores:
        Number of parallel worker processes. Values > 1 use
        :class:`concurrent.futures.ProcessPoolExecutor`. Note that stub
        methods fall back to kernel UD in each worker process; R-backed
        methods would need rpy2 initialised per-worker.

    Returns
    -------
    results_dict:
        Mapping of sequence name → result dict (same structure as
        :func:`run_model` output).
    metadata_df:
        :class:`~geopandas.GeoDataFrame` with one row per sequence containing
        all metadata fields plus a ``footprint_polygon`` geometry column.
    """
    import pandas as pd  # local import; pandas is a geopandas dependency

    results: dict[str, dict[str, Any]] = {}

    if n_cores <= 1 or len(sequences_dict) <= 1:
        # Serial execution
        for seq_name, seq_gdf in sequences_dict.items():
            logger.info("Running %s model for sequence '%s'…", method, seq_name)
            try:
                results[seq_name] = run_model(seq_gdf, method, pop_grid, config, seq_name)
            except Exception as exc:
                logger.error("Model failed for '%s': %s", seq_name, exc, exc_info=True)
                results[seq_name] = {
                    "ud_raster": None,
                    "footprint_polygon": None,
                    "metadata": {"seq_name": seq_name, "error": str(exc)},
                }
    else:
        # Parallel execution via ProcessPoolExecutor
        # GeoDataFrames are serialised as dicts to avoid pickling issues with
        # Fiona/GDAL file handles.
        work_items = []
        for seq_name, seq_gdf in sequences_dict.items():
            work_items.append(
                (seq_name, seq_gdf, method, config, pop_grid)
            )

        logger.info(
            "Launching %d worker processes for %d sequences…",
            n_cores,
            len(sequences_dict),
        )
        with ProcessPoolExecutor(max_workers=n_cores) as executor:
            futures = {
                executor.submit(_run_model_worker, item): item[0]
                for item in work_items
            }
            for future in as_completed(futures):
                seq_name = futures[future]
                try:
                    _, result = future.result()
                    results[seq_name] = result
                    logger.info("Finished '%s'.", seq_name)
                except Exception as exc:
                    logger.error(
                        "Model failed for '%s': %s", seq_name, exc, exc_info=True
                    )
                    results[seq_name] = {
                        "ud_raster": None,
                        "footprint_polygon": None,
                        "metadata": {"seq_name": seq_name, "error": str(exc)},
                    }

    # Build combined metadata GeoDataFrame
    rows = []
    geometries = []
    for seq_name, res in results.items():
        meta = dict(res.get("metadata", {}))
        meta["seq_name"] = seq_name
        rows.append(meta)
        geometries.append(res.get("footprint_polygon"))

    meta_df = gpd.GeoDataFrame(rows, geometry=geometries, crs=pop_grid.get("crs"))
    return results, meta_df


# ---------------------------------------------------------------------------
# 10. save_ud_raster
# ---------------------------------------------------------------------------

def save_ud_raster(
    ud_array: np.ndarray,
    pop_grid_meta: PopGrid,
    out_path: str,
) -> None:
    """Write a utilisation distribution raster as a single-band float32 GeoTIFF.

    Parameters
    ----------
    ud_array:
        2-D numpy array (nrows × ncols) of probability density values.
    pop_grid_meta:
        Grid metadata dict from :func:`create_population_grid`.
    out_path:
        Destination file path (e.g. ``'output/seq_01_ud.tif'``).
    """
    _write_raster(ud_array.astype(np.float32), pop_grid_meta, out_path)
    logger.info("UD raster saved to %s", out_path)


# ---------------------------------------------------------------------------
# 11. save_footprint
# ---------------------------------------------------------------------------

def save_footprint(
    footprint_geom: Polygon | MultiPolygon,
    crs: Any,
    out_path: str,
    attributes: dict[str, Any] | None = None,
) -> None:
    """Write a footprint polygon to a Shapefile or GeoPackage.

    The output format is inferred from the file extension:
    ``*.gpkg`` → GeoPackage, anything else → Shapefile.

    Parameters
    ----------
    footprint_geom:
        Shapely geometry for the footprint.
    crs:
        Coordinate reference system (pyproj CRS, EPSG int, or WKT string).
    out_path:
        Destination file path (e.g. ``'output/seq_01_footprint.gpkg'``).
    attributes:
        Optional dict of scalar attribute values to store alongside geometry.
    """
    row: dict[str, Any] = {"geometry": footprint_geom}
    if attributes:
        row.update(attributes)

    gdf = gpd.GeoDataFrame([row], crs=crs)

    driver = "GPKG" if str(out_path).lower().endswith(".gpkg") else "ESRI Shapefile"
    gdf.to_file(out_path, driver=driver)
    logger.info("Footprint saved to %s (driver=%s)", out_path, driver)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_raster(
    array: np.ndarray,
    grid_meta: PopGrid,
    out_path: str,
    nodata: float = -9999.0,
) -> None:
    """Write a 2-D float32 array to a GeoTIFF using rasterio."""
    nrows, ncols = grid_meta["shape"]
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype=np.float32,
        crs=grid_meta["crs"],
        transform=grid_meta["transform"],
        nodata=nodata,
        compress="lzw",
    ) as dst:
        dst.write(array.astype(np.float32), 1)


def _write_raster_uint8(
    array: np.ndarray,
    grid_meta: PopGrid,
    out_path: str,
) -> None:
    """Write a 2-D uint8 footprint array as a single-band GeoTIFF (matches
    R's ``datatype='INT1U'`` for footprint outputs)."""
    nrows, ncols = grid_meta["shape"]
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=nrows,
        width=ncols,
        count=1,
        dtype=np.uint8,
        crs=grid_meta["crs"],
        transform=grid_meta["transform"],
        compress="lzw",
    ) as dst:
        dst.write(array.astype(np.uint8), 1)


def _polygon_from_uint8_mask(
    mask: np.ndarray,
    pop_grid: PopGrid,
) -> Polygon | MultiPolygon:
    """Vectorise a uint8 binary mask into a Shapely geometry on the pop grid."""
    transform = pop_grid["transform"]
    polys = [
        shape(geom)
        for geom, val in rio_shapes(mask.astype(np.uint8), mask=(mask == 1), transform=transform)
        if val == 1
    ]
    if not polys:
        return Polygon()
    return unary_union(polys)


def load_model_outputs_from_disk(
    ud_dir,
    footprint_dir=None,
    metadata_csv=None,
):
    """Rebuild the in-memory model results (pop_grid + per-sequence UDs +
    footprints) from GeoTIFFs already written to a working directory, so Tab 4
    (population) and Tab 5 (map) can use a prior run without re-modelling.

    Reads every ``<seq>.tif`` in *ud_dir* as that sequence's UD raster, derives
    the population grid from the first raster's transform/shape/CRS, and (if a
    matching ``<seq>.tif`` exists in *footprint_dir*) polygonises the footprint
    mask. Optional *metadata_csv* (the ``model_results.csv`` written by a run)
    supplies display fields per sequence.

    Returns ``(pop_grid, results, utm_crs, method)`` or ``None`` if no UD tifs
    are found. ``results`` is ``{seq_name: {ud_raster, footprint_polygon,
    metadata}}`` — the same shape ``run_all_sequences`` produces.
    """
    import rasterio
    from pathlib import Path

    ud_dir = Path(ud_dir)
    if not ud_dir.is_dir():
        return None
    ud_files = sorted(ud_dir.glob("*.tif"))
    if not ud_files:
        return None
    footprint_dir = Path(footprint_dir) if footprint_dir else None

    # Optional per-sequence metadata table (display fields only).
    meta_by_seq: dict[str, dict] = {}
    method_guess = None
    if metadata_csv is not None and Path(metadata_csv).exists():
        try:
            mdf = pd.read_csv(metadata_csv)
            key_col = next((c for c in ("sequence", "seq_name") if c in mdf.columns), None)
            if key_col:
                for _, r in mdf.iterrows():
                    meta_by_seq[str(r[key_col])] = r.to_dict()
            if "method" in mdf.columns and mdf["method"].notna().any():
                method_guess = str(mdf["method"].dropna().iloc[0])
        except Exception:
            pass

    pop_grid: PopGrid | None = None
    results: dict[str, dict] = {}
    utm_crs = None

    for f in ud_files:
        seq = f.stem
        with rasterio.open(f) as src:
            arr = src.read(1).astype(np.float32)
            if pop_grid is None:
                tr = src.transform
                pop_grid = {
                    "transform": tr,
                    "shape": (int(src.height), int(src.width)),
                    "crs": src.crs,
                    "cell_size": float(abs(tr.a)),
                    "bounds": tuple(src.bounds),
                }
                utm_crs = str(src.crs)

        fp_poly = None
        if footprint_dir is not None:
            fpf = footprint_dir / f.name
            if fpf.exists():
                try:
                    with rasterio.open(fpf) as fsrc:
                        fmask = fsrc.read(1).astype(np.uint8)
                    fp_poly = _polygon_from_uint8_mask(fmask, pop_grid)
                except Exception:
                    fp_poly = None

        md = meta_by_seq.get(seq, {})
        metadata = {
            "seq_name": seq,
            "method": md.get("method", method_guess or "Loaded"),
            "num_locs": md.get("n_locs", md.get("num_locs", "")),
            "start_date": md.get("start_date", ""),
            "end_date": md.get("end_date", ""),
            "execution_time_min": md.get("runtime_min", md.get("execution_time_min", "")),
            # A tif on disk means the sequence succeeded (errored sequences write
            # no raster), so treat loaded results as error-free.
            "errors": "None",
        }
        results[seq] = {
            "ud_raster": arr,
            "footprint_polygon": fp_poly,
            "metadata": metadata,
        }

    return pop_grid, results, utm_crs, (method_guess or "Loaded")


def _rasterize_polygon(
    geom: Polygon | MultiPolygon,
    pop_grid: PopGrid,
    nrows: int,
    ncols: int,
    burn_value: float = 1.0,
) -> np.ndarray:
    """Rasterise a Shapely polygon onto the population grid."""
    out = rio_rasterize(
        [(mapping(geom), burn_value)],
        out_shape=(nrows, ncols),
        transform=pop_grid["transform"],
        fill=0.0,
        dtype=np.float32,
    )
    return out.astype(np.float32)


def _contour_polygon(
    density: np.ndarray,
    pop_grid: PopGrid,
    contour: float,
) -> Polygon | MultiPolygon:
    """Extract a polygon encompassing the given probability contour from a UD raster.

    Cells are sorted by descending density and accumulated until the cumulative
    sum reaches ``contour / 100``. The mask is then vectorised with rasterio.

    Returns a Shapely geometry (Polygon or MultiPolygon).
    """
    from rasterio.features import shapes as rio_shapes

    flat = density.ravel()
    sorted_idx = np.argsort(flat)[::-1]
    cumsum = np.cumsum(flat[sorted_idx])
    threshold_idx = np.searchsorted(cumsum, contour / 100.0)

    mask = np.zeros(density.shape, dtype=np.uint8)
    mask.ravel()[sorted_idx[: threshold_idx + 1]] = 1

    transform = pop_grid["transform"]
    crs = pop_grid["crs"]

    polys = [
        shape(geom)
        for geom, val in rio_shapes(mask, mask=(mask == 1), transform=transform)
        if val == 1
    ]

    if not polys:
        logger.warning("No polygon extracted at contour=%d%%.", contour)
        return Polygon()

    return unary_union(polys)


# ---------------------------------------------------------------------------
# 11. Winter/Summer range sequences + per-individual / range-density outputs
#     (ports of Chloe's CB_MAPP 3b/3c range logic and the per-individual
#     averaging in 3a). See DIFFERENCES.md for the comparison.
# ---------------------------------------------------------------------------

def build_range_sequences(
    gdf_utm: gpd.GeoDataFrame,
    migtime_df: pd.DataFrame,
    seq_labels,
    mindays: int = 30,
    id_col: str = "animal_id",
    date_col: str = "timestamp",
):
    """Derive winter & summer *range* sequences from the migration windows.

    For each animal-year:
      - summer = spring_end -> fall_start (same year)
      - winter = fall_end   -> next-year spring_start
    Spring vs fall is identified by the Tab-2 season labels when present
    (label contains 'spring'/'fall'), else by date order (earliest window =
    spring/outbound, latest = fall/return). An animal-year is **skipped** (with
    a recorded reason) when a bounding migration date is missing or the window
    holds fewer than ``mindays`` distinct days of GPS fixes.

    Returns ``(range_seqs, key_to_animal, skip_notes)`` where
    ``range_seqs = {"Summer": {key: gdf}, "Winter": {key: gdf}}`` (each gdf has
    UTM geometry + a "date" column, ready for run_all_sequences), ``key`` is
    ``<animal>_<year>_<Season>``, and ``key_to_animal`` maps key -> animal id.
    """
    notes: list[str] = []
    labels = [str(x).lower() for x in (seq_labels or [])]

    g = gdf_utm.copy()
    g[date_col] = pd.to_datetime(g[date_col], errors="coerce")
    g = g.dropna(subset=[date_col])

    def _windows(row):
        wins = []
        for i in range(1, 9):
            sk, ek = f"mig{i}_start", f"mig{i}_end"
            sv = str(row[sk]) if sk in row.index else ""
            if sv and sv not in ("", "NaT", "nan", "None"):
                s = pd.Timestamp(sv)
                ev = str(row[ek]) if ek in row.index else ""
                e = pd.Timestamp(ev) if (ev and ev not in ("", "NaT", "nan", "None")) else s
                lab = labels[i - 1] if i - 1 < len(labels) else f"mig{i}"
                wins.append((s, e, lab))
        return wins

    def _identify(wins):
        spring = fall = None
        for s, e, lab in wins:
            if spring is None and ("spring" in lab or lab.startswith("spr")):
                spring = (s, e)
            if fall is None and ("fall" in lab or "autumn" in lab or lab.startswith("fal")):
                fall = (s, e)
        if (spring is None or fall is None) and wins:
            ws = sorted(wins, key=lambda w: w[0])
            if spring is None:
                spring = (ws[0][0], ws[0][1])
            if fall is None:
                fall = (ws[-1][0], ws[-1][1])
        return spring, fall

    win_map: dict = {}
    for _, row in migtime_df.iterrows():
        animal = str(row.get("animal_id", "")).strip()
        yr_raw = str(row.get("bio_year", "")).strip()
        try:
            year = int(float(yr_raw))
            if year < 100:
                year += 2000
        except (ValueError, TypeError):
            continue
        if not animal:
            continue
        sp, fa = _identify(_windows(row)) if _windows(row) else (None, None)
        win_map[(animal, year)] = {"spring": sp, "fall": fa}

    pts_by_animal = {a: sub for a, sub in g.groupby(g[id_col].astype(str))}

    def _extract(animal, start, end):
        sub = pts_by_animal.get(animal)
        if sub is None:
            return ("no_animal", 0)
        s = sub[(sub[date_col] >= start) & (sub[date_col] <= end)]
        if len(s) == 0:
            return ("no_points", 0)
        ndays = int(s[date_col].dt.normalize().nunique())
        if ndays < mindays:
            return ("mindays", ndays)
        s = s.sort_values(date_col).copy().rename(columns={date_col: "date"})
        s["x"] = s.geometry.x
        s["y"] = s.geometry.y
        return ("ok", s)

    range_seqs = {"Summer": {}, "Winter": {}}
    key_to_animal: dict = {}

    for (animal, year), w in sorted(win_map.items()):
        sp, fa = w["spring"], w["fall"]
        # ---- Summer: spring_end -> fall_start (same year) ----
        if sp and fa and sp[1] is not None and fa[0] is not None and sp[1] < fa[0]:
            r = _extract(animal, sp[1], fa[0])
            if r[0] == "ok":
                key = f"{animal}_{year}_Summer"
                range_seqs["Summer"][key] = r[1]
                key_to_animal[key] = animal
            elif r[0] == "mindays":
                notes.append(f"{animal} {year}: summer range skipped — only {r[1]} day(s) of data (need >= {mindays}).")
            else:
                notes.append(f"{animal} {year}: summer range skipped — no GPS points between spring end and fall start.")
        else:
            notes.append(f"{animal} {year}: summer range skipped — missing spring-end or fall-start migration date.")
        # ---- Winter: fall_end(year) -> spring_start(year+1) ----
        nxt = win_map.get((animal, year + 1))
        if fa and fa[1] is not None and nxt and nxt.get("spring") and nxt["spring"][0] is not None:
            r = _extract(animal, fa[1], nxt["spring"][0])
            if r[0] == "ok":
                key = f"{animal}_{year}_Winter"
                range_seqs["Winter"][key] = r[1]
                key_to_animal[key] = animal
            elif r[0] == "mindays":
                notes.append(f"{animal} {year}: winter range skipped — only {r[1]} day(s) of data (need >= {mindays}).")
            else:
                notes.append(f"{animal} {year}: winter range skipped — no GPS points between fall end and next-year spring start.")
        else:
            notes.append(f"{animal} {year}: winter range skipped — missing fall-end or next-year spring-start migration date.")

    return range_seqs, key_to_animal, notes


def _normalize_ud(u) -> np.ndarray:
    """NaN-safe normalisation of a UD raster to sum=1."""
    u = np.nan_to_num(np.asarray(u, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    s = u.sum()
    return u / s if s > 0 else u


def _mean_normalized(ud_list):
    """Normalise each UD to sum=1, mean them, renormalise. None if empty."""
    arrs = [_normalize_ud(u) for u in ud_list if u is not None]
    if not arrs:
        return None
    return _normalize_ud(np.mean(np.stack(arrs, axis=0), axis=0))


def _safe_token(s) -> str:
    return "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in str(s))


def _valid_uds_grouped(results, key_to_animal, key_to_label):
    """Return (by_animal, by_animal_label) dicts of UD arrays from a results
    dict, skipping errored/empty sequences. Animal/label come from the supplied
    maps (animal ids can contain underscores, so we can't parse the key)."""
    by_a: dict = {}
    by_al: dict = {}
    for key, res in results.items():
        meta = res.get("metadata") or {}
        err = meta.get("errors") or meta.get("error") or ""
        ud = res.get("ud_raster")
        if ud is None or (err and err != "None"):
            continue
        animal = key_to_animal.get(key, str(key))
        label = key_to_label.get(key, "mig")
        by_a.setdefault(animal, []).append(ud)
        by_al.setdefault((animal, label), []).append(ud)
    return by_a, by_al


def write_individual_uds(results, pop_grid, out_dir, key_to_animal, key_to_label, mode="both"):
    """Write per-individual UD GeoTIFFs. ``mode``: 'season' (one per animal per
    label), 'combined' (one per animal across all its sequences), or 'both'.
    Each individual's sequences are normalised then averaged (per Chloe's
    per-individual averaging). Returns the list of written paths."""
    from pathlib import Path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_a, by_al = _valid_uds_grouped(results, key_to_animal, key_to_label)
    written = []
    if mode in ("season", "both"):
        for (animal, label), uds in by_al.items():
            m = _mean_normalized(uds)
            if m is None:
                continue
            p = out_dir / f"{_safe_token(animal)}_{_safe_token(label)}_UD.tif"
            _write_raster(m.astype(np.float32), pop_grid, str(p))
            written.append(p)
    if mode in ("combined", "both"):
        for animal, uds in by_a.items():
            m = _mean_normalized(uds)
            if m is None:
                continue
            p = out_dir / f"{_safe_token(animal)}_combined_UD.tif"
            _write_raster(m.astype(np.float32), pop_grid, str(p))
            written.append(p)
    return written


def write_range_density(results, pop_grid, out_path, key_to_animal):
    """Population mean-UD density for a range season (Chloe's averageUD_*):
    average each individual's UDs across years, then mean across individuals,
    renormalise. Returns (n_individuals, path_or_None)."""
    by_a, _ = _valid_uds_grouped(results, key_to_animal, {})
    if not by_a:
        return (0, None)
    per_ind = [_mean_normalized(uds) for uds in by_a.values()]
    per_ind = [p for p in per_ind if p is not None]
    if not per_ind:
        return (0, None)
    pop = _normalize_ud(np.mean(np.stack(per_ind, axis=0), axis=0))
    _write_raster(pop.astype(np.float32), pop_grid, str(out_path))
    return (len(per_ind), out_path)
