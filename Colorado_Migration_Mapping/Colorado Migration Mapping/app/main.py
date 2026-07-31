"""
main.py
-------
Colorado Migration Corridor Mapper — Dash application entry point.

Run with:
    python app/main.py        (from project root)
    python main.py            (from app/ directory)
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import tempfile
import threading
import traceback
import webbrowser
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure imports work whether launched from project root or app/ directory.
# Both parents go on sys.path so `from app.modules.X` (root launch) AND
# `from modules.X` (app/ launch) both resolve. Bat files use the first form;
# devs running `python main.py` from inside app/ get the second.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent           # .../app
_ROOT = _HERE.parent                              # .../Colorado Migration Mapping
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import dash
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dash_table, dcc, html
from dash.exceptions import PreventUpdate

# These are NOT real Python objects — they're string references to JS functions
# that Dash will look up on `window.dashExtensions.default` at runtime. The
# definitions live in app/assets/map_functions.js, which Dash auto-serves from
# /assets/. If that file is renamed or missing, the browser console shows
# "No match for [dashExtensions.default.seqPointStyle]" and the Tab 5 map
# silently renders unstyled.
_seq_point_style = {"variable": "dashExtensions.default.seqPointStyle"}
# Polygon style fn for Tab 5 population/footprint contour overlays — colours by
# feature.properties._color and shades fill opacity by contour %. Defined in
# assets/map_functions.js (dashExtensions.default.contourStyle).
_contour_style = {"variable": "dashExtensions.default.contourStyle"}
_seq_line_style = {"variable": "dashExtensions.default.seqLineStyle"}
_vec_point_style = {"variable": "dashExtensions.default.vecPointStyle"}

# ---------------------------------------------------------------------------
# Module imports — three-tier fallback so the Dash UI still loads even when
# the analysis modules can't be imported (e.g., missing geopandas/rasterio).
# Tier 1: `from app.modules.X` — succeeds when launched from project root.
# Tier 2: `from modules.X` — succeeds when launched from inside app/.
# Tier 3: stubs that raise NotImplementedError on call — UI comes up, every
#         analysis button errors loudly with a clear message instead of a
#         silent crash at startup. Useful for diagnosing install problems.
# ---------------------------------------------------------------------------
try:
    from app.modules.data_ingestion import DEFAULT_CONFIG, process_data
    from app.modules.sequencing import (
        apply_auto_detections,
        build_migtime_table,
        detect_migrations_nsd,
        extract_sequences,
        get_nsd_plot_data,
    )
    from app.modules.modeling import (
        calc_bbmm_stub,
        calc_ctmm,
        calc_dbbmm,
        calc_kernel_ud,
        calc_line_buffer,
        create_population_grid,
        get_model_config,
        load_model_outputs_from_disk,
        build_range_sequences,
        write_individual_uds,
        write_individual_footprints,
        write_range_density,
        run_model,
        run_all_sequences,
    )
    from app.modules.population_outputs import (
        calc_population_use,
        calc_population_footprint,
        calc_season_stacked_outputs,
        compute_season_stacked_products,
        write_product,
        write_mig_outputs,
        write_flags_removed_shapefile,
        write_herd_metadata,
        generate_metadata_summary,
        export_all,
    )
    from app.modules.road_crossings import detect_crossings_batch
    from app.modules.raster_sampler import sample_rasters, AVAILABLE_VARIABLES
    from app.modules.wld_reader import (
        WLD_COLUMNS,
        DEFAULT_SELECTED as WLD_DEFAULT_SELECTED,
        read_wld_fast,
        read_wld_metadata,
        merge_wld_to_gps,
    )
except ImportError:
    try:
        from modules.data_ingestion import DEFAULT_CONFIG, process_data
        from modules.sequencing import (
            apply_auto_detections,
            build_migtime_table,
            detect_migrations_nsd,
            extract_sequences,
            get_nsd_plot_data,
        )
        from modules.modeling import (
            calc_bbmm_stub,
            calc_ctmm,
            calc_dbbmm,
            calc_kernel_ud,
            calc_line_buffer,
            create_population_grid,
            get_model_config,
            load_model_outputs_from_disk,
            build_range_sequences,
            write_individual_uds,
            write_range_density,
            run_model,
            run_all_sequences,
        )
        from modules.population_outputs import (
            calc_population_use,
            calc_population_footprint,
            calc_season_stacked_outputs,
            compute_season_stacked_products,
            write_product,
            write_mig_outputs,
            write_flags_removed_shapefile,
            write_herd_metadata,
            generate_metadata_summary,
            export_all,
        )
        from modules.road_crossings import detect_crossings_batch
        from modules.raster_sampler import sample_rasters, AVAILABLE_VARIABLES
        from modules.wld_reader import (
            WLD_COLUMNS,
            DEFAULT_SELECTED as WLD_DEFAULT_SELECTED,
            read_wld_fast,
            read_wld_metadata,
            merge_wld_to_gps,
        )
    except ImportError:
        def detect_crossings_batch(*a, **k):
            return {}
        def sample_rasters(df, *a, **k):
            return df
        AVAILABLE_VARIABLES = {}
        WLD_COLUMNS = {}
        WLD_DEFAULT_SELECTED = []
        def read_wld_fast(*a, **k):
            raise NotImplementedError("wld_reader module not found")
        def read_wld_metadata(*a, **k):
            raise NotImplementedError("wld_reader module not found")
        def merge_wld_to_gps(gps_df, *a, **k):
            return gps_df
        DEFAULT_CONFIG = {
            "animal_id_col": "LoclAID",
            "timestamp_col": "DT_MST",
            "lon_col": "Long",
            "lat_col": "Lat",
            "max_speed_kmh": 10.8,
            "mort_distance_m": 50,
            "mort_time_hours": 48,
            "bio_year_start_month": 2,
            "bio_year_start_day": 1,
        }

        def process_data(filepath, config=None):
            raise NotImplementedError("data_ingestion module not found")

        def detect_migrations_nsd(*a, **k):
            raise NotImplementedError("sequencing module not found")

        def build_migtime_table(*a, **k):
            raise NotImplementedError("sequencing module not found")

        def apply_auto_detections(*a, **k):
            raise NotImplementedError("sequencing module not found")

        def extract_sequences(*a, **k):
            raise NotImplementedError("sequencing module not found")

        def get_nsd_plot_data(*a, **k):
            raise NotImplementedError("sequencing module not found")

        def run_model(*a, **k):
            raise NotImplementedError("modeling module not found")

        def run_all_sequences(*a, **k):
            raise NotImplementedError("modeling module not found")

        def get_model_config(*a, **k):
            raise NotImplementedError("modeling module not found")

        def calc_population_use(*a, **k):
            raise NotImplementedError("population_outputs module not found")

        def calc_population_footprint(*a, **k):
            raise NotImplementedError("population_outputs module not found")

        def calc_season_stacked_outputs(*a, **k):
            raise NotImplementedError("population_outputs module not found")

        def compute_season_stacked_products(*a, **k):
            raise NotImplementedError("population_outputs module not found")

        def write_product(*a, **k):
            raise NotImplementedError("population_outputs module not found")

        def write_mig_outputs(*a, **k):
            raise NotImplementedError("population_outputs module not found")

        def write_flags_removed_shapefile(*a, **k):
            return None

        def write_herd_metadata(*a, **k):
            return {}

        def generate_metadata_summary(*a, **k):
            raise NotImplementedError("population_outputs module not found")

        def export_all(*a, **k):
            raise NotImplementedError("population_outputs module not found")

# ---------------------------------------------------------------------------
# App initialisation
# ---------------------------------------------------------------------------
# CYBORG = dark Bootstrap theme. suppress_callback_exceptions=True is
# REQUIRED because many callbacks target component IDs that only exist in
# certain tabs — Dash would otherwise refuse to register them at startup.
_ASSETS_DIR = str(Path(__file__).resolve().parent / "assets")

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Colorado Migration Corridor Mapper",
    assets_folder=_ASSETS_DIR,
)
server = app.server  # expose the underlying Flask server for WSGI deployment

# Dash's built-in asset serving skips .html files. Add an explicit Flask
# route so the Tab 2 MapLibre iframe can load maplibre_map.html.
from flask import send_from_directory as _send_from_directory

@server.route("/assets/<path:filename>")
def _serve_asset(filename):
    return _send_from_directory(_ASSETS_DIR, filename)

# ---------------------------------------------------------------------------
# Server-side caches. These are the workaround for the OOM-when-processing-
# large-datasets bug (see INFORMATION_K.md 2026-05-18 entry). The old design
# round-tripped the whole processed DataFrame through dcc.Store as JSON, which
# Chrome killed on 100k+ point datasets. Now dcc.Store holds tiny tokens like
# {"__cache_key": "processed", "v": 3} and the real data lives here in
# process memory, keyed by the same cache_key.
# ---------------------------------------------------------------------------
from flask_caching import Cache

# flask_caching's SimpleCache is currently unused for DataFrames but kept for
# future use (e.g., heavy plot data). DataFrames go in _DF_CACHE below.
_cache = Cache(app.server, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 600})

# Process-memory caches. Lost on app restart — the "processed" key is
# rehydrated from session_data/<project>/processed_data.parquet by _json_to_df,
# but downstream keys (migtime, model_results) require re-running their step.
_DF_CACHE: dict[str, pd.DataFrame] = {}
_MAP_CACHE: dict[str, dict] = {}  # animal_id -> cached map arrays
# Track the bio-year start (month, day) the current _MAP_CACHE entries were
# built with. When the UI changes the bio-year start, cache keys go stale and
# we wipe + rebuild lazily so the per-animal slices match the UI settings.
_MAP_CACHE_BIO_KEY: tuple[int, int] | None = None
# Tab 3 stashes the per-sequence UD rasters + footprint polygons + pop_grid
# here after a model run, because numpy arrays and Shapely geoms are not
# JSON-serialisable through dcc.Store. Tab 4 reads from this cache.
_MODEL_CACHE: dict[str, Any] = {}

# Background model run state. The run_modeling callback starts a thread and
# returns immediately; a polling callback watches this dict for completion.
_MODEL_RUN: dict[str, Any] = {
    "thread": None,       # threading.Thread or None
    "run_id": None,       # unique id for the current run
    "status": "idle",     # "idle" | "running" | "done" | "error"
    "result": None,       # tuple of callback outputs when done
    "progress_msg": "",   # latest progress message for the UI
}

# In-memory cache of Tab 4 population outputs awaiting export. Fully deferred:
# Tab 4 computes the products and stashes them here (NOT to disk); Tab 5 flushes
# the user-selected subset to ModelOutputs/ on demand. Like _MODEL_CACHE this is
# process-local and does NOT survive an app restart — regenerate Tab 4 if lost.
#   {"products": [ {key,label,category,rel_path,kind,array|gdf}, ... ],
#    "grid_meta": <pop_grid dict>}
_POP_OUTPUT_CACHE: dict[str, Any] = {}

# Persistent data directory — survives app restarts
_PROJECTS_DIR = _ROOT / "app" / "session_data"
_PROJECTS_DIR.mkdir(exist_ok=True)
_ACTIVE_PROJECT: str = ""


def _project_dir(name: str) -> Path:
    d = _PROJECTS_DIR / name.replace(" ", "_")
    d.mkdir(exist_ok=True)
    return d


def _list_projects() -> list[str]:
    # A project is "real" only if processed_data.parquet exists in its folder —
    # empty subdirs (e.g., a half-finished Process Data run) are skipped.
    # Sort key bubbles the active project to the top, then alphabetical.
    if not _PROJECTS_DIR.exists():
        return []
    return sorted(
        [d.name for d in _PROJECTS_DIR.iterdir()
         if d.is_dir() and (d / "processed_data.parquet").exists()],
        key=lambda x: (x != _ACTIVE_PROJECT, x.lower()),
    )


def _save_processed_to_disk(df: pd.DataFrame, project_name: str = ""):
    # Side effect: also mutates module-level _ACTIVE_PROJECT so subsequent
    # _load_notes() / _save_project_meta() calls without an explicit name
    # target the right folder. Process Data is the canonical entry point that
    # sets this for the rest of the session.
    global _ACTIVE_PROJECT
    name = project_name or _ACTIVE_PROJECT or "default"
    _ACTIVE_PROJECT = name
    d = _project_dir(name)
    df.to_parquet(str(d / "processed_data.parquet"), index=False)


def _load_processed_from_disk(project_name: str = "") -> pd.DataFrame | None:
    global _ACTIVE_PROJECT
    name = project_name or _ACTIVE_PROJECT or "default"
    pq = _project_dir(name) / "processed_data.parquet"
    if pq.exists():
        _ACTIVE_PROJECT = name
        return pd.read_parquet(str(pq))
    return None


def _save_project_meta(meta: dict, project_name: str = "") -> None:
    """Persist small project metadata (input source path, processed timestamp,
    workdir) next to processed_data.parquet so it survives app restarts and
    can be redisplayed in the 'Project Loaded' summary."""
    name = project_name or _ACTIVE_PROJECT or "default"
    p = _project_dir(name) / "project_meta.json"
    p.write_text(json.dumps(meta, indent=2))


def _load_project_meta(project_name: str = "") -> dict:
    name = project_name or _ACTIVE_PROJECT or "default"
    p = _project_dir(name) / "project_meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _load_notes(project_name: str = "") -> dict:
    name = project_name or _ACTIVE_PROJECT or "default"
    p = _project_dir(name) / "animal_notes.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _save_notes(notes: dict, project_name: str = ""):
    name = project_name or _ACTIVE_PROJECT or "default"
    p = _project_dir(name) / "animal_notes.json"
    p.write_text(json.dumps(notes, indent=2))


def _load_classifications(project_name: str = "") -> dict:
    """Per-animal-year movement classification (resident / nomadic / migratory),
    keyed by id_bio_year. Lives next to animal_notes.json."""
    name = project_name or _ACTIVE_PROJECT or "default"
    p = _project_dir(name) / "animal_classifications.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save_classifications(data: dict, project_name: str = ""):
    name = project_name or _ACTIVE_PROJECT or "default"
    p = _project_dir(name) / "animal_classifications.json"
    p.write_text(json.dumps(data, indent=2))


# Canonical Notes sentence each classification stamps into the textarea. The
# road/highway crossing phrase (if any) is appended after this.
_CLASSIFICATION_NOTE = {
    "resident": "Resident. No migration identified.",
    "nomadic": "Non-migratory, nomadic. Lots of movements but no migration identified.",
    "migratory": "Migration identified.",
}

# Classifications whose animal-years are dropped from the analysis on export.
_REMOVED_CLASSIFICATIONS = ("resident", "nomadic")


def _classification_note(classification: str, crosses_road: bool, crosses_highway: bool) -> str:
    """Compose the auto-populated Notes text for a classification, appending the
    canonical road/highway crossing phrase when applicable."""
    base = _CLASSIFICATION_NOTE.get(classification or "", "")
    phrase = _crossing_phrase(crosses_road, crosses_highway)
    if base and phrase:
        return f"{base} {phrase}"
    return base or phrase


# ===========================================================================
# Working directory — user picks a folder; we maintain ModelInputs/,
# ModelOutputs/, and session_log.txt inside it. Recents are tracked in
# app/session_data/recent_workdirs.json so they can be repopulated across
# app restarts.
# ===========================================================================

_ACTIVE_WORKDIR: Path | None = None
# Current output version. Model + population/export outputs go in
# <workdir>/ModelOutputs/V{n}/; Tab 1/2 shared inputs stay at the top level. A
# new version is created per model run (Tab 3); Tab 5 exports target the current
# one. Process-local — restored to the latest on-disk version when a workdir is
# (re)set. None until the first model run or a workdir with existing versions.
_ACTIVE_VERSION: int | None = None
# The version whose folder physically holds the in-use model UDs/Footprints. A
# population-only re-run branches to a new version that REFERENCES this one's
# model data instead of recomputing it.
_MODEL_SOURCE_VERSION: int | None = None
# version -> signature of the population config last exported into it. Lets an
# export detect "population options changed since I last wrote this version" and
# branch to a fresh version. Seeded from disk manifests on workdir load.
_POP_EXPORTED: dict[int, str] = {}
_RECENT_WORKDIRS_FILE = _PROJECTS_DIR / "recent_workdirs.json"
_MAX_RECENT_WORKDIRS = 12


def _workdir_inputs(workdir: Path | None = None) -> Path:
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        raise RuntimeError("No working directory set.")
    p = base / "ModelInputs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _workdir_outputs(workdir: Path | None = None) -> Path:
    """The SHARED, top-level output folder <workdir>/ModelOutputs/. Tab 1
    processed data / logs / FlagsRemoved and Tab 2 migtime exports live here and
    are referenced by every version. Versioned model/population outputs go under
    V{n}/ — see :func:`_workdir_version`."""
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        raise RuntimeError("No working directory set.")
    p = base / "ModelOutputs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parse_version_num(dirname: str) -> int | None:
    """Extract the version number from a folder name like 'V3' or 'V3_072126'."""
    if not dirname.startswith("V"):
        return None
    rest = dirname[1:]
    num_part = rest.split("_", 1)[0]
    if num_part.isdigit():
        return int(num_part)
    return None


def _list_versions(workdir: Path | None = None) -> list[int]:
    """Existing version numbers under <workdir>/ModelOutputs/ (V1, V2_072126, …), ascending."""
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        return []
    mo = base / "ModelOutputs"
    if not mo.is_dir():
        return []
    out: list[int] = []
    for p in mo.glob("V*"):
        if p.is_dir():
            v = _parse_version_num(p.name)
            if v is not None:
                out.append(v)
    return sorted(out)


def _resolve_version_dir(base: Path, v: int) -> Path:
    """Find the actual directory for version *v* under ModelOutputs/.
    Handles both old-style 'V3' and new-style 'V3_072126' folder names."""
    mo = base / "ModelOutputs"
    if mo.is_dir():
        for p in mo.glob(f"V{v}*"):
            if p.is_dir() and _parse_version_num(p.name) == v:
                return p
    return mo / f"V{v}"


def _workdir_version(workdir: Path | None = None, version: int | None = None) -> Path:
    """Path to the active versioned output folder <workdir>/ModelOutputs/V{n}_MMDDYY/.
    Uses the explicit ``version``, else the active one, else the latest existing
    (or V1 if none). Created if absent. Model runs start a NEW version via
    :func:`_start_new_version`; everything downstream writes into the current one."""
    global _ACTIVE_VERSION
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        raise RuntimeError("No working directory set.")
    v = version or _ACTIVE_VERSION
    if v is None:
        existing = _list_versions(base)
        v = existing[-1] if existing else 1
        _ACTIVE_VERSION = v
    p = _resolve_version_dir(base, v)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _start_new_version(workdir: Path | None = None) -> int:
    """Begin a new output version (max existing + 1) and make it active. Called
    at the start of a model run so each run's outputs land in their own folder.
    Folder name includes the creation date, e.g. V3_072126.

    Copies all contents from the previous version so the new folder is
    self-contained — the model run then overwrites whatever it regenerates."""
    import datetime as _dt
    import shutil
    global _ACTIVE_VERSION
    base = workdir or _ACTIVE_WORKDIR
    existing = _list_versions(base)
    v = (existing[-1] + 1) if existing else 1
    _ACTIVE_VERSION = v
    date_stamp = _dt.datetime.now().strftime("%m%d%y")
    new_dir = base / "ModelOutputs" / f"V{v}_{date_stamp}"
    if existing:
        prev_dir = _resolve_version_dir(base, existing[-1])
        shutil.copytree(str(prev_dir), str(new_dir), dirs_exist_ok=True)
    else:
        new_dir.mkdir(parents=True, exist_ok=True)
    return v


def _write_version_manifest(version: int, model: str, model_params: dict,
                            workdir: Path | None = None) -> None:
    """Write V{n}/version_manifest.json: model, params, parent version, the
    parameter diffs vs the parent, and references to the SHARED inputs this run
    drew from (reference-not-copy — shared inputs live at the ModelOutputs top
    level). Best-effort; never raises."""
    import datetime as _dt
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        return
    mo = base / "ModelOutputs"
    vdir = _resolve_version_dir(base, version)
    vdir.mkdir(parents=True, exist_ok=True)

    # Parent = highest existing version below this one.
    parents = [v for v in _list_versions(base) if v < version]
    parent = parents[-1] if parents else None
    changed: dict[str, dict] = {}
    if parent is not None:
        try:
            prev = json.loads(_resolve_version_dir(base, parent).joinpath("version_manifest.json").read_text(encoding="utf-8"))
            prev_params = prev.get("model_params", {}) or {}
            for k in sorted(set(prev_params) | set(model_params)):
                a, b = prev_params.get(k), model_params.get(k)
                if a != b:
                    changed[k] = {"from": a, "to": b}
        except Exception:
            pass

    # Shared inputs referenced (relative to the version folder).
    shared_inputs: dict[str, str] = {}
    for rel in ("processed_data.parquet", "road_crossings.json"):
        if (mo / rel).exists():
            shared_inputs[rel] = f"../{rel}"
    mig_dir = mo / "Migtime_Exports"
    if mig_dir.is_dir():
        migs = sorted(mig_dir.glob("migtime_*.csv"))
        if migs:
            shared_inputs["migtime"] = f"../Migtime_Exports/{migs[-1].name}"

    manifest = {
        "version": version,
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "model_params": model_params,
        "parent_version": parent,
        "changed_from_parent": changed,
        "shared_inputs": shared_inputs,
    }
    try:
        (vdir / "version_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass

    _write_version_log(vdir, version, parent, model=model,
                       params=model_params, changed=changed, vtype="model")


def _write_version_log(vdir: Path, version: int, parent: int | None,
                       model: str | None = None, params: dict | None = None,
                       changed: dict | None = None, vtype: str = "model",
                       pop_config: dict | None = None,
                       model_source: int | None = None) -> None:
    """Write a human-readable processing_log.txt inside V{n}/ summarising
    what this version is and what changed from its parent."""
    import datetime as _dt
    lines = [
        f"{'=' * 60}",
        f"Version V{version}  —  {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"{'=' * 60}",
        "",
    ]
    if vtype == "model":
        lines.append(f"Type: Model run ({model})")
        if params:
            lines.append("")
            lines.append("Parameters:")
            for k, v in sorted(params.items()):
                lines.append(f"  {k}: {v}")
    elif vtype == "population":
        lines.append(f"Type: Population outputs (model data from V{model_source})")
        if pop_config:
            lines.append("")
            lines.append("Population config:")
            for k, v in sorted(pop_config.items()):
                lines.append(f"  {k}: {v}")

    if parent is not None:
        lines.append("")
        if changed:
            lines.append(f"Changes from V{parent}:")
            for k, diff in sorted(changed.items()):
                lines.append(f"  {k}: {diff.get('from')} -> {diff.get('to')}")
        else:
            lines.append(f"No parameter changes from V{parent}.")

    lines.append("")
    try:
        (vdir / "processing_log.txt").write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


def _set_model_source(version: int) -> None:
    """Record which version holds the model UDs the in-memory results came from."""
    global _MODEL_SOURCE_VERSION
    _MODEL_SOURCE_VERSION = version


def _pop_config_signature(config) -> str:
    """Stable signature of a population config, for detecting 'options changed'."""
    try:
        return json.dumps(config or {}, sort_keys=True, default=str)
    except Exception:
        return str(config)


def _latest_version_with_model(workdir: Path | None = None) -> int | None:
    """Highest version whose folder actually contains model UD tifs (UDs/*.tif).
    Used so a population-only version transparently reuses the model version's
    UDs for loaders."""
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        return None
    for v in reversed(_list_versions(base)):
        ud = _resolve_version_dir(base, v) / "UDs"
        if ud.is_dir() and any(ud.glob("*.tif")):
            return v
    return None


def _write_pop_version_manifest(version: int, parent: int | None,
                                model_source: int | None, pop_config,
                                workdir: Path | None = None) -> None:
    """Manifest for a population-only branch version: it holds new population
    outputs but REFERENCES a prior version's model data (reference-not-copy)."""
    import datetime as _dt
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        return
    mo = base / "ModelOutputs"
    vdir = _resolve_version_dir(base, version)
    vdir.mkdir(parents=True, exist_ok=True)

    reused: dict[str, str] = {}
    if model_source is not None:
        src_dir = _resolve_version_dir(base, model_source)
        for sub in ("UDs", "Footprints", "model_results.csv"):
            reused[sub] = f"../{src_dir.name}/{sub}"
    shared_inputs: dict[str, str] = {}
    for rel in ("processed_data.parquet", "road_crossings.json"):
        if (mo / rel).exists():
            shared_inputs[rel] = f"../{rel}"
    mig_dir = mo / "Migtime_Exports"
    if mig_dir.is_dir():
        migs = sorted(mig_dir.glob("migtime_*.csv"))
        if migs:
            shared_inputs["migtime"] = f"../Migtime_Exports/{migs[-1].name}"

    changed: dict[str, dict] = {}
    if parent is not None:
        try:
            prev = json.loads(_resolve_version_dir(base, parent).joinpath("version_manifest.json").read_text(encoding="utf-8"))
            prev_pop = prev.get("pop_config") or prev.get("model_params") or {}
            cur_pop = pop_config or {}
            for k in sorted(set(prev_pop) | set(cur_pop)):
                a, b = prev_pop.get(k), cur_pop.get(k)
                if a != b:
                    changed[k] = {"from": a, "to": b}
        except Exception:
            pass

    manifest = {
        "version": version,
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "type": "population",
        "parent_version": parent,
        "model_source_version": model_source,
        "changed_from_parent": changed,
        "reused_from": reused,
        "pop_config": pop_config,
        "shared_inputs": shared_inputs,
    }
    try:
        (vdir / "version_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass

    _write_version_log(vdir, version, parent, vtype="population",
                       pop_config=pop_config, changed=changed,
                       model_source=model_source)


def _record_pop_export(version: int, pop_config, workdir: Path | None = None) -> None:
    """After a population export, merge the exported pop_config into the target
    version's manifest (creating it if absent) and remember its signature so
    later exports can detect option changes — even across an app restart."""
    global _POP_EXPORTED
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        return
    _POP_EXPORTED[version] = _pop_config_signature(pop_config)
    vdir = _resolve_version_dir(base, version)
    vdir.mkdir(parents=True, exist_ok=True)
    mpath = vdir / "version_manifest.json"
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {"version": version}
    except Exception:
        manifest = {"version": version}
    manifest["pop_config"] = pop_config
    manifest["population_exported"] = True
    try:
        mpath.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def _seed_pop_exported(workdir: Path | None = None) -> None:
    """Populate _POP_EXPORTED from on-disk manifests so branch detection survives
    a restart. Reads each version's recorded pop_config signature."""
    global _POP_EXPORTED
    _POP_EXPORTED = {}
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        return
    for v in _list_versions(base):
        mpath = _resolve_version_dir(base, v) / "version_manifest.json"
        if not mpath.exists():
            continue
        try:
            man = json.loads(mpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        if man.get("population_exported") and "pop_config" in man:
            _POP_EXPORTED[v] = _pop_config_signature(man["pop_config"])


def _workdir_log(workdir: Path | None = None) -> Path:
    base = workdir or _ACTIVE_WORKDIR
    if base is None:
        raise RuntimeError("No working directory set.")
    return base / "session_log.txt"


def _set_active_workdir(path: str | Path) -> Path:
    """Set the active working directory, scaffold subfolders, log it,
    and remember in recents. Returns the resolved Path."""
    global _ACTIVE_WORKDIR, _ACTIVE_VERSION
    p = Path(path).resolve()
    p.mkdir(parents=True, exist_ok=True)
    _ACTIVE_WORKDIR = p
    # Adopt the latest existing output version (None if this workdir has none
    # yet — the first model run will create V1). Restore model-source + the
    # population-export signatures so branch detection survives across projects.
    existing_versions = _list_versions(p)
    _ACTIVE_VERSION = existing_versions[-1] if existing_versions else None
    _set_model_source(_latest_version_with_model(p))
    _seed_pop_exported(p)
    # Scaffold
    _workdir_inputs(p)
    _workdir_outputs(p)
    # Touch the log so users can see it appear
    _log_action("WORKDIR_SET", path=str(p))
    _remember_workdir(p)
    return p


def _log_action(action: str, **fields) -> None:
    """Append a timestamped line to <workdir>/session_log.txt.
    Format: 'YYYY-MM-DD HH:MM:SS  ACTION  key1=value1 key2=value2'."""
    # Two deliberate silences: (1) no workdir = silent no-op so calls are safe
    # before the user has picked a folder; (2) any exception during write is
    # swallowed so a full disk / locked log file can't crash the app mid-run.
    if _ACTIVE_WORKDIR is None:
        return
    try:
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        kv = " ".join(f"{k}={v}" for k, v in fields.items())
        line = f"{ts}  {action}" + (f"  {kv}" if kv else "") + "\n"
        with open(_workdir_log(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _append_processing_log(lines: list[str], header: str | None = None) -> None:
    """Append a timestamped section to both the top-level processing_log.txt
    and the active version's processing_log.txt.

    The top-level file is a cumulative record across all versions; each
    version folder gets its own complete log of everything that happened
    during that run. Silent no-op if no workdir; never raises."""
    if _ACTIVE_WORKDIR is None:
        return
    try:
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        block: list[str] = ["", "=" * 60]
        if header:
            block.append(f"{header}   [{ts}]")
        block.extend(str(ln) for ln in lines)
        text = "\n".join(block) + "\n"
        with open(_workdir_outputs() / "processing_log.txt", "a", encoding="utf-8") as f:
            f.write(text)
        if _ACTIVE_VERSION is not None:
            try:
                vdir = _resolve_version_dir(_ACTIVE_WORKDIR, _ACTIVE_VERSION)
                vdir.mkdir(parents=True, exist_ok=True)
                with open(vdir / "processing_log.txt", "a", encoding="utf-8") as f:
                    f.write(text)
            except Exception:
                pass
    except Exception:
        pass


def _recent_workdirs() -> list[Path]:
    """Read the recent-workdirs list. Drops entries that no longer exist."""
    if not _RECENT_WORKDIRS_FILE.exists():
        return []
    try:
        data = json.loads(_RECENT_WORKDIRS_FILE.read_text())
        paths = [Path(p) for p in data if Path(p).is_dir()]
        return paths
    except Exception:
        return []


def _remember_workdir(path: Path) -> None:
    """Add path to the front of the recents list. Deduplicated. Capped."""
    try:
        recents = [str(path.resolve())] + [str(p) for p in _recent_workdirs() if p != path]
        # Dedupe preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for s in recents:
            if s in seen:
                continue
            seen.add(s)
            deduped.append(s)
        deduped = deduped[:_MAX_RECENT_WORKDIRS]
        _RECENT_WORKDIRS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RECENT_WORKDIRS_FILE.write_text(json.dumps(deduped, indent=2))
    except Exception:
        pass


def _find_system_python() -> str | None:
    """Find a system Python that has tkinter (the bundled embed lacks it)."""
    import shutil, subprocess as _sp
    candidates = [
        r"C:\Program Files\Python313\python.exe",
        r"C:\Program Files\Python312\python.exe",
        r"C:\Program Files\Python311\python.exe",
        r"C:\Program Files (x86)\Python313\python.exe",
        shutil.which("python") or "",
        shutil.which("python3") or "",
    ]
    for p in candidates:
        if not (p and os.path.isfile(p) and os.path.normcase(p) != os.path.normcase(sys.executable)):
            continue
        try:
            r = _sp.run([p, "-c", "import tkinter"], capture_output=True, timeout=10)
            if r.returncode == 0:
                return p
        except Exception:
            continue
    return None


def _pick_directory_native() -> str | None:
    """Open a native folder-picker dialog. Returns the chosen path or None.

    Uses the system Python (with tkinter) in a subprocess — the bundled
    embeddable Python does not include tkinter.
    """
    import subprocess
    code = (
        "import tkinter as tk, sys\n"
        "from tkinter import filedialog\n"
        "root = tk.Tk()\n"
        "root.withdraw()\n"
        "root.attributes('-topmost', True)\n"
        "path = filedialog.askdirectory(title='Choose project working directory')\n"
        "root.destroy()\n"
        "sys.stdout.write(path or '')\n"
    )
    sys_py = _find_system_python()
    if sys_py:
        try:
            result = subprocess.run(
                [sys_py, "-c", code],
                capture_output=True, text=True, timeout=300,
            )
            chosen = result.stdout.strip()
            if chosen:
                return chosen
        except Exception:
            pass

    # Fallback: PowerShell folder picker (less convenient tree-style dialog)
    print(
        "NOTE: For a better folder picker, install Python 3.11+ from "
        "python.org (full installer, not embeddable). The app will "
        "automatically detect it and use the File Explorer dialog."
    )
    ps_code = (
        "$shell = New-Object -ComObject Shell.Application; "
        "$folder = $shell.BrowseForFolder(0, 'Choose project working directory', 0x40, 0); "
        "if ($folder) { Write-Host $folder.Self.Path -NoNewline }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_code],
            capture_output=True, text=True, timeout=300,
        )
        chosen = result.stdout.strip()
        return chosen or None
    except Exception:
        return None


# ===========================================================================
# Helper utilities
# ===========================================================================

def _err_alert(msg: str) -> dbc.Alert:
    return dbc.Alert(str(msg), color="danger", dismissable=True, className="mt-2")


def _ok_alert(msg: str) -> dbc.Alert:
    return dbc.Alert(str(msg), color="success", dismissable=True, className="mt-2")


_DF_TOKEN_REV = 0


def _df_to_json(df: pd.DataFrame, cache_key: str = "latest") -> str:
    # Server-side handle pattern: the DataFrame lives in _DF_CACHE; the browser
    # only ever sees this tiny token. Previously this serialised the full
    # DataFrame into the dcc.Store, which OOM'd the browser tab on 100k+ row
    # herds (50–200 MB JSON payloads).
    _DF_CACHE[cache_key] = df
    payload = {"__cache_key": cache_key, "rows": int(len(df)), "cols": int(len(df.columns))}
    # The migtime table is edited IN PLACE by several Tab-2 callbacks (auto-detect
    # fills dates, Clear Sequences blanks them, slider drags rewrite a slot) —
    # the row/col shape never changes, so the token string above would be byte-
    # identical between writes and Dash would suppress the downstream map/chart
    # refresh (auto-detected points stayed black; cleared bands lingered). Stamp
    # a monotonic revision so every migtime write yields a distinct token and the
    # `store-migtime-table` Input fires its consumers.
    if cache_key == "migtime":
        global _DF_TOKEN_REV
        _DF_TOKEN_REV += 1
        payload["rev"] = _DF_TOKEN_REV
    return json.dumps(payload)


def _json_to_df(j: str, cache_key: str = "latest") -> pd.DataFrame:
    # Hot path: process-memory hit. Skips JSON parsing entirely.
    if cache_key in _DF_CACHE:
        return _DF_CACHE[cache_key]
    try:
        parsed = json.loads(j) if j else None
    except Exception:
        parsed = None
    # New token format → cache miss (process restart). Rehydrate "processed"
    # from disk; other keys must be regenerated by re-running upstream steps.
    if isinstance(parsed, dict) and "__cache_key" in parsed:
        if cache_key == "processed":
            df = _load_processed_from_disk()
            if df is not None:
                _DF_CACHE[cache_key] = df
                return df
        raise RuntimeError(
            f"Server cache miss for '{cache_key}' after process restart — re-run the upstream step."
        )
    # Legacy full-JSON payload — kept for browser stores still holding the
    # pre-token-switch format. Safe to delete once we're confident no live
    # session has an old store cached. (Old format = full DF as JSON,
    # serialised via to_json(orient="split").)
    df = pd.read_json(io.StringIO(j), orient="split")
    _DF_CACHE[cache_key] = df
    return df


def _build_loaded_project_summary(df: pd.DataFrame, project_name: str, meta: dict | None = None) -> html.Div:
    """Build the summary card for a project that was loaded from disk
    (Process Data clicked after Load Project, no new upload). *meta* is the
    optional project_meta.json contents — used to surface the original input
    file path so the user can see exactly which data this project came from."""
    meta = meta or {}
    # Coerce timestamps for date-range display
    ts = pd.to_datetime(df["timestamp"], errors="coerce") if "timestamp" in df.columns else None
    n_animals = df["animal_id"].nunique() if "animal_id" in df.columns else "?"
    n_points = len(df)
    n_flagged = int(df["problem"].sum()) if "problem" in df.columns else 0
    n_mort = int(df["mortality_flag"].sum()) if "mortality_flag" in df.columns else 0
    date_min = ts.min() if ts is not None else "?"
    date_max = ts.max() if ts is not None else "?"

    # Detect enrichment columns already present in the loaded project. These
    # tell the user which optional Tab 1 raster/WLD pulls were done in the
    # original processing run, so they know what's available without re-running.
    # Validity rule: float cols count notna; int/bool cols count nonzero
    # (raster sampler writes 0 for misses, not NaN, on integer outputs).
    enrichment_cols = []
    for c in ("elevation_m", "snow_depth_m", "swe_m", "snow_density_kgm3"):
        if c in df.columns:
            n_valid = int(df[c].notna().sum() if df[c].dtype == float else (df[c] != 0).sum())
            enrichment_cols.append(f"{c} ({n_valid:,})")
    _RASTER_COLS = {"elevation_m", "snow_depth_m", "swe_m", "snow_density_kgm3"}
    wld_col_names = {name for (name, _label, _grp) in WLD_COLUMNS.values()} - _RASTER_COLS
    wld_present = [c for c in df.columns if c in wld_col_names]
    if wld_present:
        enrichment_cols.append(f"+ {len(wld_present)} WLD vars")

    info_lines = [
        html.Div([html.Strong("Project: "), str(project_name).replace("_", " ") or "(unnamed)"]),
        html.Div([html.Strong("Source: "), "Loaded from session_data/ (previously processed)"]),
    ]
    src = (meta.get("input_source_path") or "").strip()
    if src:
        info_lines.append(
            html.Div(
                [html.Strong("Input file: "), html.Code(src, style={"fontSize": "0.85em"})],
                style={"wordBreak": "break-all"},
            )
        )
    wld_src = (meta.get("wld_source_path") or "").strip()
    if wld_src:
        info_lines.append(
            html.Div(
                [html.Strong("WLD file: "), html.Code(wld_src, style={"fontSize": "0.85em"})],
                style={"wordBreak": "break-all"},
            )
        )
    processed_at = (meta.get("processed_at") or "").strip()
    if processed_at:
        info_lines.append(html.Div([html.Strong("Processed at: "), processed_at]))
    saved_crs = (meta.get("input_crs") or "").strip()
    if saved_crs:
        proj_name = _crs_to_projection_name(saved_crs)
        info_lines.append(html.Div([
            html.Strong("Projection: "), proj_name,
            html.Small(f" ({saved_crs})", className="text-muted ms-1"),
        ]))
    if enrichment_cols:
        info_lines.append(html.Div([html.Strong("Enrichment present: "), ", ".join(enrichment_cols)]))

    return html.Div([
        dbc.Card(
            dbc.CardBody(
                [
                    html.H6("Project Loaded", className="card-title text-info"),
                    dbc.Row(
                        [
                            dbc.Col(html.Div([html.Strong("Animals: "), str(n_animals)]), width=3),
                            dbc.Col(html.Div([html.Strong("Points: "), f"{n_points:,}"]), width=3),
                            dbc.Col(html.Div([html.Strong("Flagged: "), f"{n_flagged:,}"]), width=3),
                            dbc.Col(html.Div([html.Strong("Mortality Flags: "), f"{n_mort:,}"]), width=3),
                        ],
                        className="mb-2",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(html.Div([html.Strong("Date Range: "), f"{date_min} → {date_max}"]), width=12),
                        ],
                        className="mb-2",
                    ),
                    *info_lines,
                ]
            ),
            className="border-info mb-3",
        ),
        dbc.Alert(
            "This project was processed in a previous session. To rerun the full pipeline "
            "(re-detect bursts, re-flag mortality, re-sample rasters, etc.), upload the "
            "raw CSV/shapefile again and click Process Data.",
            color="info",
            className="small",
        ),
    ])


def _make_preview_table(df: pd.DataFrame, max_rows: int = 20) -> dash_table.DataTable:
    preview = df.head(max_rows).copy()
    # Drop geopandas' geometry column — its Shapely values aren't JSON-serialisable
    # and Dash chokes when sending the preview to the browser. (The lon/lat
    # columns already carry the coords; this is a tabular preview, not a map.)
    drop_cols = [
        c for c in preview.columns
        if c == "geometry" or str(preview[c].dtype) == "geometry"
    ]
    if drop_cols:
        preview = preview.drop(columns=drop_cols)
    # Convert remaining non-serialisable types to strings.
    for col in preview.columns:
        if pd.api.types.is_datetime64_any_dtype(preview[col]):
            preview[col] = preview[col].astype(str)
        elif preview[col].dtype == object:
            preview[col] = preview[col].astype(str)
    return dash_table.DataTable(
        data=preview.to_dict("records"),
        columns=[{"name": c, "id": c} for c in preview.columns],
        page_size=10,
        style_table={"overflowX": "auto"},
        style_cell={
            "backgroundColor": "#2a2a2a",
            "color": "#f0f0f0",
            "border": "1px solid #444",
            "fontSize": "12px",
            "padding": "4px 8px",
            "whiteSpace": "nowrap",
        },
        style_header={
            "backgroundColor": "#1a1a1a",
            "fontWeight": "bold",
            "color": "#aef",
        },
    )


# ===========================================================================
# Layout components
# ===========================================================================

# ---------------------------------------------------------------------------
# Navbar
# ---------------------------------------------------------------------------
def _load_user_guide() -> str:
    guide_path = _HERE / "assets" / "user_guide.md"
    try:
        return guide_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "*User guide not found.*"

navbar = dbc.Navbar(
    dbc.Container(
        [
            html.Div(
                [
                    html.Span(
                        "Colorado Migration Corridor Mapper",
                        className="navbar-brand fw-bold",
                        style={"fontSize": "1.25rem", "color": "#7ecfff"},
                    ),
                    html.Span(
                        "| Colorado Parks & Wildlife",
                        style={"color": "#B0B0B0", "fontSize": "0.9rem", "marginLeft": "12px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
            ),
            html.Button(
                "? Help",
                id="help-guide-btn",
                style={
                    "background": "none", "border": "1px solid #7ecfff",
                    "color": "#7ecfff", "borderRadius": "4px", "padding": "4px 12px",
                    "cursor": "pointer", "fontSize": "0.85rem",
                },
            ),
        ],
        fluid=True,
        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
    ),
    color="dark",
    dark=True,
    className="mb-3 px-3",
    style={"borderBottom": "2px solid #334"},
)

help_modal = dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle("User Guide"), close_button=True),
        dbc.ModalBody(
            html.Div(
                dcc.Markdown(_load_user_guide()),
                className="help-guide-content",
            ),
            style={"backgroundColor": "#1a1a2e", "maxHeight": "75vh", "overflowY": "auto"},
        ),
    ],
    id="help-guide-modal",
    size="xl",
    is_open=False,
    centered=True,
)


# ---------------------------------------------------------------------------
# Tab 1: Data Import & Cleaning
# ---------------------------------------------------------------------------
# Layout shape (top-down, left col width=4, right col width=8):
#   LEFT:
#     1. Working Directory card     — picks/displays the folder that holds
#                                     ModelInputs/, ModelOutputs/, session_log.txt.
#                                     The workdir is THE session-wide root for
#                                     all file I/O.
#     2. Project card               — load a previously-processed project from
#                                     app/session_data/<name>/ without re-running
#                                     the pipeline.
#     3. Select or Upload Data card — file picker; auto-populates from
#                                     <workdir>/ModelInputs/ via a dropdown OR
#                                     accepts drag-and-drop.
#     4. Column Mapping card        — dropdowns auto-populated from columns
#                                     detected on upload (animal_id, timestamp,
#                                     lon, lat, optional UTM).
#     5. Processing Parameters card — DOP / min-sats / mortality / speed
#                                     thresholds + bio-year start date + manual
#                                     herd-ID override.
#     6. Environmental Variables    — raster sampling toggles (DEM, SNODAS).
#     7. WLD File Upload card       — optional .wld enrichment, hidden behind
#                                     a checkbox (wld-section-toggle).
#     8. Process Data button        — fires process_uploaded_data callback.
#   RIGHT: tab1-status / tab1-summary / tab1-preview output zones, wrapped in
#          dcc.Loading so a circle spinner shows during long Process Data runs.
#
# Component IDs are the contracts with the callback layer further down.
# Search for an ID (e.g. "param-herd-id-override") to find both its layout
# definition here and the callback that reads it.
_CRS_NAMES = {
    "EPSG:4326": "WGS84 (Geographic)",
    "EPSG:32613": "WGS84 UTM Zone 13N",
    "EPSG:32612": "WGS84 UTM Zone 12N",
    "EPSG:32614": "WGS84 UTM Zone 14N",
    "EPSG:26913": "NAD83 UTM Zone 13N",
    "EPSG:26912": "NAD83 UTM Zone 12N",
    "EPSG:26914": "NAD83 UTM Zone 14N",
    "EPSG:3857": "Web Mercator",
}


def _crs_to_projection_name(crs_str: str) -> str:
    if not crs_str:
        return "Unknown"
    name = _CRS_NAMES.get(crs_str)
    if name:
        return name
    try:
        from pyproj import CRS
        c = CRS.from_user_input(crs_str)
        return c.name or crs_str
    except Exception:
        return crs_str


def _col_map_row(label, dropdown_id, options=None, multi=False):
    return dbc.Row(
        [
            dbc.Col(dbc.Label(label, style={"fontSize": "0.85rem"}), width=4),
            dbc.Col(
                dcc.Dropdown(
                    id=dropdown_id,
                    options=options or [],
                    placeholder="Select column…" if not multi else "Select column(s)…",
                    style={"fontSize": "0.85rem"},
                    className="dash-dark-dropdown",
                    multi=multi,
                ),
                width=8,
            ),
        ],
        className="mb-2",
    )


_INFO_LABEL_COUNTER = [0]

def _info_label(label_text, description, recommended=None):
    _INFO_LABEL_COUNTER[0] += 1
    btn_id = f"info-btn-{_INFO_LABEL_COUNTER[0]}"
    body = description
    if recommended is not None:
        body += f"\n\nRecommended: {recommended}"
    return html.Div([
        dbc.Label(label_text, style={"fontSize": "0.85rem", "display": "inline"}),
        html.Button(
            "ⓘ",
            id=btn_id,
            style={
                "background": "none", "border": "none", "color": "#6c9bd2",
                "cursor": "pointer", "fontSize": "0.95rem", "padding": "0 0 0 5px",
                "verticalAlign": "middle", "lineHeight": "1",
            },
        ),
        dbc.Popover(
            dbc.PopoverBody(body, style={"fontSize": "0.78rem", "whiteSpace": "pre-line"}),
            target=btn_id,
            trigger="click",
            placement="right",
        ),
    ], style={"marginBottom": "2px"})


tab1_layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            [
                # LEFT: upload + column mapping
                dbc.Col(
                    [
                        # ===== Working Directory =====
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    dbc.Row([
                                        dbc.Col(html.Span("Working Directory", style={"fontSize": "0.85rem"}), width="auto"),
                                        dbc.Col(
                                            html.Small("inputs / outputs / log live here", className="text-muted"),
                                            width="auto", className="ms-auto",
                                        ),
                                    ], align="center", className="g-0"),
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Row([
                                            dbc.Col(
                                                dbc.Button(
                                                    "Browse...",
                                                    id="btn-pick-workdir",
                                                    color="primary",
                                                    size="sm",
                                                    className="w-100",
                                                ),
                                                width=4,
                                            ),
                                            dbc.Col(
                                                dbc.Input(
                                                    id="workdir-display",
                                                    type="text",
                                                    placeholder="No working directory set",
                                                    value="",
                                                    readonly=True,
                                                    size="sm",
                                                    style={"fontSize": "0.78rem", "backgroundColor": "#222", "color": "#E0E0E0"},
                                                ),
                                                width=8,
                                            ),
                                        ], className="g-2"),
                                        html.Div([
                                            dbc.Label("Recent working directories", style={"fontSize": "0.8rem", "marginTop": "0.5rem"}),
                                            dcc.Dropdown(
                                                id="workdir-recents",
                                                options=[],
                                                placeholder="Pick a recent directory...",
                                                style={"fontSize": "0.78rem"},
                                            ),
                                        ]),
                                        html.Div(id="workdir-status", className="mt-2 small"),
                                    ]
                                ),
                            ],
                            className="mb-3",
                        ),
                        dbc.Card(
                            [
                                dbc.CardHeader("Project"),
                                dbc.CardBody(
                                    [
                                        html.Small(
                                            "Load a project you have already created, or enter a name for the "
                                            "current project so you can come back to it later and quickly re-load it.",
                                            className="text-muted d-block mb-2",
                                            style={"fontSize": "0.75rem"},
                                        ),
                                        dbc.Row([
                                            dbc.Col(
                                                dcc.Dropdown(
                                                    id="project-selector",
                                                    options=[],
                                                    placeholder="Load previous project...",
                                                    style={"fontSize": "0.85rem"},
                                                ),
                                                width=8,
                                            ),
                                            dbc.Col(
                                                dbc.Button("Load", id="btn-load-project", color="info", size="sm", className="w-100"),
                                                width=4,
                                            ),
                                        ], className="mb-2"),
                                        dbc.Input(
                                            id="project-name",
                                            type="text",
                                            placeholder="New project name (e.g. A37_Pronghorn_2026)",
                                            size="sm",
                                        ),
                                        html.Div(id="project-load-status", className="mt-1 small"),
                                    ]
                                ),
                            ],
                            className="mb-3",
                        ),
                        dbc.Card(
                            [
                                dbc.CardHeader("Select or Upload Data"),
                                dbc.CardBody(
                                    [
                                        dbc.Label(
                                            "Pick from ModelInputs/",
                                            style={"fontSize": "0.8rem"},
                                        ),
                                        dcc.Dropdown(
                                            id="modelinputs-select",
                                            options=[],
                                            placeholder="(set a working directory to populate)",
                                            style={"fontSize": "0.82rem", "marginBottom": "8px"},
                                        ),
                                        html.Small(
                                            "Files copied into ModelInputs/ when you set a workdir, "
                                            "plus anything you upload below.",
                                            className="text-muted d-block mb-2",
                                            style={"fontSize": "0.72rem"},
                                        ),
                                        html.Hr(className="my-1"),
                                        dcc.Upload(
                                            id="upload-data",
                                            children=html.Div(
                                                [
                                                    "Drag & Drop or ",
                                                    html.A("Browse", style={"color": "#7ecfff"}),
                                                    html.Br(),
                                                    html.Small(
                                                        "Accepts .csv or .zip (shapefile)",
                                                        style={"color": "#B0B0B0"},
                                                    ),
                                                ]
                                            ),
                                            style={
                                                "width": "100%",
                                                "height": "90px",
                                                "lineHeight": "30px",
                                                "borderWidth": "2px",
                                                "borderStyle": "dashed",
                                                "borderRadius": "8px",
                                                "borderColor": "#556",
                                                "textAlign": "center",
                                                "padding": "12px",
                                                "cursor": "pointer",
                                            },
                                            multiple=False,
                                            accept=".csv,.zip,.shp",
                                        ),
                                        dcc.Loading(
                                            html.Div(id="upload-filename", className="mt-1 text-muted small"),
                                            type="circle",
                                            style={"display": "inline-block"},
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-3",
                        ),
                        dbc.Card(
                            [
                                dbc.CardHeader("Column Mapping"),
                                dbc.CardBody(
                                    [
                                        html.Small(
                                            "Select the names of the fields in your dataset that represent "
                                            "animal ID, timestamp, longitude, latitude, DOP (precision), "
                                            "number of satellites, and age class.",
                                            className="text-muted d-block mb-2",
                                            style={"fontSize": "0.75rem"},
                                        ),
                                        _col_map_row("Animal ID column", "col-animal-id"),
                                        _col_map_row("Timestamp column(s)", "col-timestamp", multi=True),
                                        html.Div(
                                            [
                                                _col_map_row("Longitude column", "col-lon"),
                                                _col_map_row("Latitude column", "col-lat"),
                                            ],
                                            id="coord-lonlat-group",
                                        ),
                                        html.Div(
                                            [
                                                _col_map_row("UTM Easting column", "col-utm-easting"),
                                                _col_map_row("UTM Northing column", "col-utm-northing"),
                                            ],
                                            id="coord-utm-group",
                                            style={"display": "none"},
                                        ),
                                        _col_map_row("DOP / Precision column", "col-dop"),
                                        _col_map_row("Satellites column", "col-sats"),
                                        dbc.Collapse(
                                            dbc.Alert(
                                                [
                                                    html.Strong("Note: "),
                                                    "This app automatically assumes the input CSV data is in the "
                                                    "WGS84 (EPSG:4326) projection, consistent with the collar data "
                                                    "stored in Wildlife Tracker. If instead of Latitude/Longitude "
                                                    "information your data uses UTM Northing/Easting, it may be in "
                                                    "the other commonly used projection/CRS, such as WGS84 UTM "
                                                    "Zone 13N (EPSG:32613). If this is the case, check the box below. "
                                                    "If not, please transform your CSV data externally or import a "
                                                    "zipped shapefile instead.",
                                                ],
                                                color="warning",
                                                className="small mt-2 mb-2",
                                            ),
                                            id="csv-crs-warning",
                                            is_open=False,
                                        ),
                                        html.Div(
                                            dbc.Checkbox(
                                                id="utm-input-toggle",
                                                label="Yes, my CSV data is in UTM Zone 13N (EPSG:32613)",
                                                value=False,
                                                className="small",
                                            ),
                                            id="utm-toggle-wrapper",
                                            style={"display": "none"},
                                        ),
                                        html.Hr(className="my-2"),
                                        _col_map_row("Age class column", "col-age-class"),
                                        html.Div(
                                            [
                                                html.Small(
                                                    "Select which age classes you would like to include in the analysis. "
                                                    "Calves/Fawns are typically excluded from movement models due to collars dropping.",
                                                    className="text-muted d-block mb-1",
                                                ),
                                                dbc.Checklist(
                                                    id="age-class-include",
                                                    options=[],
                                                    value=[],
                                                    inline=True,
                                                    className="small",
                                                ),
                                                html.Small(
                                                    id="age-class-hint",
                                                    className="text-muted",
                                                ),
                                            ],
                                            id="age-class-checklist-wrapper",
                                            style={"display": "none"},
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-3",
                        ),
                        dbc.Card(
                            [
                                dbc.CardHeader("Processing Parameters"),
                                dbc.CardBody(
                                    [
                                        html.Small(
                                            "These thresholds control automatic data cleaning. Points that exceed "
                                            "the max speed, DOP cutoff, or fall below the minimum satellites will be "
                                            "flagged as problem points. Animals whose fixes remain within the "
                                            "mortality distance for longer than the mortality time will be "
                                            "automatically flagged as mortalities. Flagged points will appear in "
                                            "Tab 2, but will be removed from the analysis unless you select and unflag them.",
                                            className="text-muted d-block mb-2",
                                            style={"fontSize": "0.75rem"},
                                        ),
                                        dbc.Checkbox(
                                            id="auto-flagging-toggle",
                                            label="Flag problem points and mortalities based on movement and GPS parameters",
                                            value=True,
                                            style={"fontSize": "0.85rem"},
                                            className="mb-2",
                                        ),
                                        dbc.Collapse(
                                            id="auto-flagging-collapse",
                                            is_open=True,
                                            children=[
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        _info_label("Max Speed (km/h)",
                                                                    "Consecutive GPS fixes that imply travel above this speed are flagged as problem points. "
                                                                    "Both the origin and destination fixes of the impossible movement are flagged.",
                                                                    "10.8 km/h for mule deer / elk"),
                                                        dbc.Input(
                                                            id="param-max-speed",
                                                            type="number",
                                                            value=10.8,
                                                            min=0,
                                                            step=0.1,
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                                dbc.Col(
                                                    [
                                                        _info_label("Mortality Distance (m)",
                                                                    "If all of an animal's GPS fixes in its last Mortality Time window fall within this radius "
                                                                    "of their centroid, those fixes are flagged as a mortality event.",
                                                                    "50 m"),
                                                        dbc.Input(
                                                            id="param-mort-dist",
                                                            type="number",
                                                            value=50,
                                                            min=0,
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                            ],
                                            className="mb-2",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        _info_label("Mortality Time (hrs)",
                                                                    "The trailing time window used to evaluate mortality. If an animal stays within the "
                                                                    "Mortality Distance for this duration at the end of its track, it is flagged as a mortality.",
                                                                    "48 hours"),
                                                        dbc.Input(
                                                            id="param-mort-time",
                                                            type="number",
                                                            value=48,
                                                            min=0,
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                                dbc.Col(
                                                    [
                                                        _info_label("DOP (Dilution of Precision) Cutoff",
                                                                    "GPS fixes with a Dilution of Precision value above this threshold are flagged as problem points. "
                                                                    "Higher DOP means lower positional accuracy.",
                                                                    "10"),
                                                        dbc.Input(
                                                            id="param-dop-cutoff",
                                                            type="number",
                                                            value=10,
                                                            min=0,
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                            ],
                                            className="mb-2",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        _info_label("Minimum Satellites",
                                                                    "GPS fixes acquired with fewer satellites than this threshold are flagged as problem points. "
                                                                    "Fewer satellites generally means less accurate positioning.",
                                                                    "5"),
                                                        dbc.Input(
                                                            id="param-sat-cutoff",
                                                            type="number",
                                                            value=5,
                                                            min=0,
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                            ],
                                            className="mb-2",
                                        ),
                                            ],
                                        ),
                                        html.Hr(className="my-3"),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Bio Year Start (M/D)", style={"fontSize": "0.85rem", "fontWeight": "bold"}),
                                                        dbc.InputGroup(
                                                            [
                                                                dbc.Input(
                                                                    id="param-bio-month",
                                                                    type="number",
                                                                    value=2,
                                                                    min=1,
                                                                    max=12,
                                                                    placeholder="Mo",
                                                                ),
                                                                dbc.Input(
                                                                    id="param-bio-day",
                                                                    type="number",
                                                                    value=1,
                                                                    min=1,
                                                                    max=31,
                                                                    placeholder="Day",
                                                                ),
                                                            ]
                                                        ),
                                                        html.Small(
                                                            "Recommended: Mule Deer Feb. 1; Elk Feb. 15",
                                                            className="text-muted d-block mt-1",
                                                            style={"fontSize": "0.7rem"},
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label(
                                                            "Herd ID (optional override)",
                                                            style={"fontSize": "0.85rem", "fontWeight": "bold"},
                                                        ),
                                                        dbc.Input(
                                                            id="param-herd-id-override",
                                                            type="text",
                                                            value="",
                                                            placeholder="e.g. E18_E22 (leave blank to auto-derive from DAU column)",
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                            ],
                                            className="mb-2",
                                        ),
                                    ]
                                ),
                            ]
                        ),
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    dbc.Row([
                                        dbc.Col(html.Span("Environmental Variables", style={"fontSize": "0.85rem"}), width="auto"),
                                        dbc.Col(
                                            html.Small("sampled at each GPS fix", className="text-muted"),
                                            width="auto", className="ms-auto",
                                        ),
                                    ], align="center", className="g-0"),
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Checklist(
                                            id="raster-var-checklist",
                                            options=[
                                                {"label": v, "value": k}
                                                for k, v in AVAILABLE_VARIABLES.items()
                                            ],
                                            # Elevation is on by default — it's wanted in
                                            # almost every run. Users can uncheck it to skip
                                            # DEM sampling (the slowest part of processing).
                                            value=["elevation_m"],
                                            style={"fontSize": "0.82rem"},
                                            labelStyle={"display": "block", "marginBottom": "2px"},
                                        ),
                                        html.Small(
                                            "Sampled from the USGS 3DEP 1/3 arc-second DEM (~10 m)",
                                            className="text-muted d-block mt-1",
                                        ),
                                        html.Hr(className="my-2"),
                                        dbc.Checkbox(
                                            id="detect-road-crossings",
                                            value=True,
                                            label="Detect road crossings (TIGER) per animal-year",
                                            style={"fontSize": "0.82rem"},
                                        ),
                                        html.Small(
                                            "Off by default — adds time on big datasets. "
                                            "Enable only if you need the road / highway crossing badges in Tab 2.",
                                            className="text-muted d-block",
                                            style={"fontSize": "0.72rem"},
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-3",
                        ),
                        # ----- WLD enrichment (optional, hidden until checked) -----
                        # The whole card collapses via dbc.Collapse keyed on
                        # `wld-section-toggle` (Checkbox in the CardHeader).
                        # Inside, an "Advanced variables" subsection collapses
                        # separately via `wld-advanced-collapse`. Only the
                        # variables in WLD_DEFAULT_SELECTED are shown by default;
                        # the rest live behind the second collapse to keep the
                        # initial UI uncluttered.
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    dbc.Checkbox(
                                        id="wld-section-toggle",
                                        value=False,
                                        label=".wld File Upload (optional)",
                                        style={"fontSize": "0.85rem"},
                                    ),
                                ),
                                html.Small(
                                    "This checkbox can be ignored — wait for updates coming soon to "
                                    "learn more about .wld files.",
                                    className="text-muted d-block",
                                    style={"fontSize": "0.75rem", "padding": "0 12px 4px 12px"},
                                ),
                                dbc.Collapse(
                                    dbc.CardBody(
                                        [
                                            dcc.Upload(
                                                id="upload-wld",
                                                children=html.Div(
                                                    [
                                                        "Drag & Drop a ",
                                                        html.Code(".wld"),
                                                        " file or ",
                                                        html.A("Browse", style={"color": "#7ecfff"}),
                                                    ],
                                                    style={"fontSize": "0.85rem"},
                                                ),
                                                style={
                                                    "width": "100%",
                                                    "minHeight": "55px",
                                                    "borderWidth": "2px",
                                                    "borderStyle": "dashed",
                                                    "borderRadius": "8px",
                                                    "borderColor": "#556",
                                                    "textAlign": "center",
                                                    "padding": "10px",
                                                    "cursor": "pointer",
                                                },
                                                multiple=False,
                                                accept=".wld",
                                            ),
                                            html.Div(id="wld-upload-status", className="mt-1 text-muted small"),
                                            html.Hr(className="my-2"),
                                            html.Small(
                                                "Variables to merge onto each GPS fix:",
                                                className="text-muted d-block mb-1",
                                            ),
                                            dbc.Checklist(
                                                id="wld-var-checklist",
                                                options=[
                                                    {
                                                        "label": f"{label}  ({name})",
                                                        "value": idx,
                                                    }
                                                    for idx, (name, label, _grp) in sorted(WLD_COLUMNS.items())
                                                    if idx in WLD_DEFAULT_SELECTED
                                                ],
                                                value=list(WLD_DEFAULT_SELECTED),
                                                style={"fontSize": "0.78rem"},
                                                labelStyle={"display": "block", "marginBottom": "1px"},
                                            ),
                                            dbc.Button(
                                                "Show all 36 variables ▾",
                                                id="btn-toggle-wld-advanced",
                                                color="link",
                                                size="sm",
                                                className="p-0 mt-1",
                                                style={"fontSize": "0.75rem"},
                                            ),
                                            dbc.Collapse(
                                                dbc.Checklist(
                                                    id="wld-var-advanced-checklist",
                                                    options=[
                                                        {
                                                            "label": f"{label}  ({name}) — {grp}",
                                                            "value": idx,
                                                        }
                                                        for idx, (name, label, grp) in sorted(WLD_COLUMNS.items())
                                                        if idx not in WLD_DEFAULT_SELECTED
                                                    ],
                                                    value=[],
                                                    style={"fontSize": "0.75rem"},
                                                    labelStyle={"display": "block", "marginBottom": "1px"},
                                                ),
                                                id="wld-advanced-collapse",
                                                is_open=False,
                                                className="mt-1",
                                            ),
                                        ]
                                    ),
                                    id="wld-section-collapse",
                                    is_open=False,
                                ),
                            ],
                            className="mb-3",
                        ),
                        html.Div([
                            dbc.Button(
                                "Process Data",
                                id="btn-process",
                                color="primary",
                                className="w-100",
                            ),
                            dcc.Loading(
                                html.Div(id="process-loading-indicator"),
                                type="circle",
                                style={"display": "inline-block", "marginLeft": "8px"},
                            ),
                        ], style={"display": "flex", "alignItems": "center", "marginTop": "8px"}),
                        # ===== Import an existing migtime table =====
                        # For users who already defined migration sequences
                        # elsewhere (e.g. the WMI Migration Mapper export, or a
                        # prior run of this app). Maps the file onto our internal
                        # schema and loads it straight into store-migtime-table so
                        # Tab 2 shows the sequences and modeling can use them.
                        dbc.Card(
                            [
                                dbc.CardHeader("Import Migtime CSV (optional)"),
                                dbc.CardBody(
                                    [
                                        html.Small(
                                            "Already have a reviewed migtime table? Load it here "
                                            "instead of re-detecting. Process your GPS data above "
                                            "first so the animal-years line up.",
                                            className="text-muted d-block mb-2",
                                            style={"fontSize": "0.72rem"},
                                        ),
                                        dcc.Upload(
                                            id="upload-migtime",
                                            children=html.Div(
                                                [
                                                    "Drag & Drop or ",
                                                    html.A("Browse", style={"color": "#7ecfff"}),
                                                    html.Br(),
                                                    html.Small(
                                                        "A migtime .csv (one row per animal-year)",
                                                        style={"color": "#B0B0B0"},
                                                    ),
                                                ]
                                            ),
                                            style={
                                                "width": "100%",
                                                "minHeight": "70px",
                                                "borderWidth": "2px",
                                                "borderStyle": "dashed",
                                                "borderRadius": "8px",
                                                "borderColor": "#556",
                                                "textAlign": "center",
                                                "padding": "10px",
                                                "cursor": "pointer",
                                            },
                                            multiple=False,
                                            accept=".csv",
                                        ),
                                        html.Div(id="migtime-import-filename", className="mt-1 text-muted small"),
                                        html.Hr(className="my-2"),
                                        dbc.Label("Animal-ID column", style={"fontSize": "0.8rem"}),
                                        dcc.Dropdown(
                                            id="migtime-import-animalid-col",
                                            options=[],
                                            placeholder="(upload a file to choose)",
                                            style={"fontSize": "0.82rem", "marginBottom": "8px"},
                                            className="dash-dark-dropdown",
                                        ),
                                        dbc.Label("Bio-year start (month / day)", style={"fontSize": "0.8rem"}),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    dbc.Input(
                                                        id="migtime-import-bio-month",
                                                        type="number", value=2, min=1, max=12,
                                                        placeholder="Mo", size="sm",
                                                    ),
                                                    width=6,
                                                ),
                                                dbc.Col(
                                                    dbc.Input(
                                                        id="migtime-import-bio-day",
                                                        type="number", value=1, min=1, max=31,
                                                        placeholder="Day", size="sm",
                                                    ),
                                                    width=6,
                                                ),
                                            ],
                                            className="g-2 mb-2",
                                        ),
                                        html.Small(
                                            "Must match the bio-year start defined in the Processing Parameters so "
                                            "the animal-year keys align (auto-filled from the file when present). "
                                            "Recommended: Mule Deer Feb. 1; Elk Feb. 15",
                                            className="text-muted d-block mb-2",
                                            style={"fontSize": "0.7rem"},
                                        ),
                                        dbc.Button(
                                            "Import Migtime",
                                            id="btn-import-migtime",
                                            color="info",
                                            size="sm",
                                            className="w-100",
                                        ),
                                        html.Div(id="migtime-import-status", className="mt-2 small"),
                                    ]
                                ),
                            ],
                            className="mb-3 mt-3",
                        ),
                    ],
                    width=4,
                ),
                # RIGHT: preview + status. All three Divs are filled by
                # process_uploaded_data (or load_project / handle_upload):
                #   tab1-status  — Alert banner (success/error)
                #   tab1-summary — Processing Summary card built by
                #                  _build_loaded_project_summary OR the in-line
                #                  summary block in process_uploaded_data.
                #   tab1-preview — DataTable of the first 20 rows (made by
                #                  _make_preview_table).
                # dcc.Loading wraps all three so a single circle spinner covers
                # the whole right column during the long Process Data run.
                dbc.Col(
                    [
                        dcc.Loading(
                            id="loading-tab1",
                            type="circle",
                            children=[
                                html.Div(id="tab1-status"),
                                html.Div(id="tab1-summary", className="mt-2"),
                                html.Div(id="tab1-preview", className="mt-3"),
                            ],
                        )
                    ],
                    width=8,
                ),
            ]
        )
    ],
    className="mt-3",
)


# ---------------------------------------------------------------------------
# Tab 2: Migration Sequencing (NSD Review)
# ---------------------------------------------------------------------------
# Three-column workflow for reviewing one animal-year at a time:
#
#   LEFT (width=2): bio-year settings + animal navigation + migtime I/O.
#       - Bio Year Start month/day controls how `id_bio_year` keys are derived
#         AT REVIEW TIME (re-derived on every callback — see render_seq_panels
#         and update_seq_map). Changing this re-shapes every animal's window.
#       - Auto-detect All (build_migtime_store) populates the migtime store;
#         Clear Sequences blanks the current animal's row. Per-animal slider
#         edits also write into the migtime store via slider_to_migtime. The
#         renderer (render_seq_panels) paints bands/cards from that store.
#       - Migtime card writes/loads <workdir>/ModelOutputs/Migtime_Exports/.
#
#   MIDDLE (width=5, stacked):
#       1. Sequence Date Ranges card — vertically resizable. Contains the
#          per-sequence dcc.RangeSlider widgets generated dynamically by
#          render_seq_panels (one per sequence slot from the migtime table).
#       2. NSD plot — vertically resizable, scrollZoom enabled.
#       3. Displacement, Speed, Elevation plots — fixed height, in
#          dcc.Loading.
#       All four plots share the same bio-year x-range; sliders drive the
#          shaded bands on the NSD plot AND the point colours on the map.
#
#   RIGHT (width=5): MapLibre GL iframe (assets/maplibre_map.html) plus
#       per-animal notes textarea + Crosses Road/Highway badges, plus the
#       point-flagging button cluster. The iframe communicates with Dash via
#       postMessage — selection state lands in store-tab2-selection, which
#       the flag callbacks consume.
#
# Hidden coupling worth knowing:
# - The point colours on the map come from the migtime store (NOT a separate
#   per-animal selection). When sliders move, slider_to_migtime updates
#   migtime, and update_seq_map repaints colours in response.
# - Default unassigned point colour is BLACK (#000), not gray — to make
#   un-reviewed animals visually obvious.
tab2_layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            [
                # LEFT SIDEBAR: settings + navigation
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader("Biological Year & Sequence Settings"),
                                dbc.CardBody(
                                    [
                                        dbc.Label("Bio Year Start Date", style={"fontSize": "0.85rem"}),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    dbc.Input(id="seq-bio-year-month", type="number", value=2, min=1, max=12, placeholder="Mo", size="sm"),
                                                    width=6,
                                                ),
                                                dbc.Col(
                                                    dbc.Input(id="seq-bio-year-day", type="number", value=1, min=1, max=31, placeholder="Day", size="sm"),
                                                    width=6,
                                                ),
                                            ],
                                            className="mb-1",
                                        ),
                                        html.Small(
                                            "Each animal-year starts on this date. "
                                            "Recommended: Mule Deer Feb. 1; Elk Feb. 15",
                                            className="text-muted d-block mb-2",
                                        ),
                                        dbc.Label("Max Sequences", style={"fontSize": "0.85rem"}),
                                        dbc.Input(id="seq-num-sequences", type="number", value=4, min=1, max=8, size="sm", className="mb-1"),
                                        dbc.Label("Sequence Names", style={"fontSize": "0.85rem"}),
                                        html.Div(id="seq-name-inputs"),
                                    ]
                                ),
                            ],
                            className="mb-2",
                        ),
                        dbc.Card(
                            [
                                dbc.CardHeader("Animal Selection"),
                                dbc.CardBody(
                                    [
                                        dcc.Dropdown(id="seq-animal-dropdown", options=[], placeholder="Select animal-year…", className="mb-2"),
                                        dbc.ButtonGroup(
                                            [
                                                dbc.Button("◀ Prev", id="btn-prev-animal", color="secondary", size="sm"),
                                                dbc.Button("Next ▶", id="btn-next-animal", color="secondary", size="sm"),
                                            ],
                                            className="w-100 mb-2",
                                        ),
                                        html.Div(id="seq-progress", className="text-center text-muted small mb-2"),
                                        html.Div(
                                            [
                                                dbc.Button("Auto-detect All", id="btn-autodetect-all", color="info", className="w-100 mb-1", size="sm"),
                                                dbc.Button("Clear Sequences", id="btn-clear-sequences", color="secondary", outline=True, className="w-100 mb-2", size="sm"),
                                                dbc.ButtonGroup(
                                                    [
                                                        dbc.Button("Accept", id="btn-accept-animal", color="success", size="sm"),
                                                        dbc.Button("Reject", id="btn-reject-animal", color="danger", size="sm"),
                                                    ],
                                                    className="w-100",
                                                ),
                                            ],
                                            style={"display": "none"},
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-2",
                        ),
                        # Migtime table management — save/load/overwrite the
                        # current migtime to <workdir>/ModelOutputs/Migtime_Exports/.
                        dbc.Card(
                            [
                                dbc.CardHeader("Migtime Table"),
                                dbc.CardBody(
                                    [
                                        dbc.Button(
                                            "Export Updated Table",
                                            id="btn-export-migtime",
                                            color="primary",
                                            size="sm",
                                            className="w-100 mb-1",
                                        ),
                                        dbc.Button(
                                            "Load Previous Table",
                                            id="btn-load-migtime",
                                            color="secondary",
                                            size="sm",
                                            className="w-100 mb-1",
                                        ),
                                        dbc.Button(
                                            "Overwrite Table",
                                            id="btn-overwrite-migtime",
                                            color="warning",
                                            size="sm",
                                            className="w-100",
                                        ),
                                        html.Div(id="migtime-status", className="mt-2 small"),
                                    ]
                                ),
                            ],
                            className="mb-2",
                        ),
                        html.Div(id="seq-confidence", className="text-muted small"),
                    ],
                    width=2,
                ),
                # MIDDLE: sequence sliders + NSD/displacement/speed charts
                dbc.Col(
                    [
                        # Sequence range sliders — wrapped in a vertically
                        # resizable div. Drag the bottom-right corner to
                        # shrink/grow; the inner card scrolls when content
                        # exceeds the chosen height.
                        html.Div(
                            dbc.Card(
                                [
                                    dbc.CardHeader(
                                        html.Span("Sequence Date Ranges  ↕ drag corner to resize",
                                                  style={"fontSize": "0.85rem"}),
                                    ),
                                    dbc.CardBody(
                                        html.Div(id="seq-date-ranges"),
                                        className="py-2 px-3",
                                        style={"overflowY": "auto", "height": "calc(100% - 38px)"},
                                    ),
                                ],
                                className="mb-1",
                                style={"height": "100%"},
                            ),
                            style={
                                "height": "260px",
                                "minHeight": "80px",
                                "maxHeight": "800px",
                                "resize": "vertical",
                                "overflow": "hidden",
                            },
                        ),
                        dbc.Checklist(
                            id="nsd-overlay-toggles",
                            options=[
                                {"label": " Problem points", "value": "problem"},
                                {"label": " Mortality points", "value": "mortality"},
                                {"label": " Fix gaps (>26 h)", "value": "gaps"},
                            ],
                            value=["problem", "mortality", "gaps"],
                            inline=True,
                            className="small mb-1",
                            style={"fontSize": "0.8rem"},
                        ),
                        dbc.Tabs(
                            [
                                dbc.Tab(
                                    html.Div(
                                        dcc.Graph(
                                            id="nsd-plot",
                                            style={"height": "100%", "width": "100%"},
                                            config={
                                                "displayModeBar": False,
                                                "scrollZoom": True,
                                                "responsive": True,
                                            },
                                            responsive=True,
                                        ),
                                        style={
                                            "height": "400px",
                                            "minHeight": "200px",
                                            "maxHeight": "900px",
                                            "resize": "vertical",
                                            "overflow": "hidden",
                                        },
                                    ),
                                    label="NSD",
                                    tab_id="chart-nsd",
                                ),
                                dbc.Tab(
                                    html.Div(
                                        dcc.Graph(
                                            id="displacement-plot",
                                            style={"height": "100%", "width": "100%"},
                                            config={"displayModeBar": False, "scrollZoom": True, "responsive": True},
                                            responsive=True,
                                        ),
                                        style={
                                            "height": "400px",
                                            "minHeight": "200px",
                                            "maxHeight": "900px",
                                            "resize": "vertical",
                                            "overflow": "hidden",
                                        },
                                    ),
                                    label="Displacement",
                                    tab_id="chart-displacement",
                                ),
                                dbc.Tab(
                                    html.Div(
                                        dcc.Graph(
                                            id="speed-plot",
                                            style={"height": "100%", "width": "100%"},
                                            config={"displayModeBar": False, "scrollZoom": True, "responsive": True},
                                            responsive=True,
                                        ),
                                        style={
                                            "height": "400px",
                                            "minHeight": "200px",
                                            "maxHeight": "900px",
                                            "resize": "vertical",
                                            "overflow": "hidden",
                                        },
                                    ),
                                    label="Speed",
                                    tab_id="chart-speed",
                                ),
                                dbc.Tab(
                                    html.Div(
                                        dcc.Graph(
                                            id="elevation-plot",
                                            style={"height": "100%", "width": "100%"},
                                            config={"displayModeBar": False, "scrollZoom": True, "responsive": True},
                                            responsive=True,
                                        ),
                                        style={
                                            "height": "400px",
                                            "minHeight": "200px",
                                            "maxHeight": "900px",
                                            "resize": "vertical",
                                            "overflow": "hidden",
                                        },
                                    ),
                                    label="Elevation",
                                    tab_id="chart-elevation",
                                ),
                            ],
                            active_tab="chart-nsd",
                            className="mb-1",
                        ),
                    ],
                    # Grow to fill whatever horizontal space the (resizable)
                    # map column gives back. minWidth:0 lets the NSD/charts
                    # shrink below their content width if the map is widened,
                    # rather than forcing the row to wrap. Pair this with the
                    # map column's `resize: horizontal` (below): narrowing the
                    # map hands its width to this column, so the NSD plot
                    # genuinely gets wider (its dcc.Graph is responsive).
                    width=True,
                    style={"minWidth": "0"},
                ),
                # RIGHT: MapLibre GL map + notes + road crossings
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    dbc.Row(
                                        [
                                            dbc.Col(html.Span("Animal Locations", style={"fontSize": "0.85rem"}), width="auto"),
                                            dbc.Col(
                                                dbc.RadioItems(
                                                    id="seq-basemap-toggle",
                                                    options=[
                                                        {"label": "Satellite", "value": "esri"},
                                                        {"label": "Topo", "value": "topo"},
                                                    ],
                                                    value="esri",
                                                    inline=True,
                                                    className="small",
                                                ),
                                                width="auto",
                                                className="ms-auto",
                                            ),
                                        ],
                                        align="center",
                                        className="g-0",
                                    ),
                                ),
                                dbc.CardBody(
                                    # Resizable map wrapper. `resize: both` puts a single grip at
                                    # the bottom-right corner that changes BOTH width and height.
                                    # Width is the key one: this wrapper has an explicit width, and
                                    # its column (RIGHT, below) is content-sized (col-auto), so
                                    # narrowing the map shrinks the whole column and hands that
                                    # space to the flex-grow NSD column — the NSD plot gets wider.
                                    # The notes/flag boxes below use a width:0 / minWidth:100% trick
                                    # so their text can't set a minimum column width; they simply
                                    # follow the map's width.
                                    # paddingBottom leaves a thin iframe-free strip so the native
                                    # resize grip isn't swallowed by the iframe's mouse capture;
                                    # the iframe fills the rest at width/height 100%. MapLibre GL
                                    # (4.7.1) watches its container with a ResizeObserver, so the
                                    # map re-fits automatically as the wrapper changes size.
                                    html.Div(
                                        html.Iframe(
                                            id="seq-map-iframe",
                                            src="/assets/maplibre_map.html",
                                            style={
                                                "height": "100%",
                                                "width": "100%",
                                                "border": "none",
                                                "borderRadius": "4px",
                                                "display": "block",
                                            },
                                        ),
                                        style={
                                            "width": "40vw",
                                            "minWidth": "300px",
                                            "maxWidth": "75vw",
                                            "height": "calc(100vh - 320px)",
                                            "minHeight": "200px",
                                            "maxHeight": "90vh",
                                            "resize": "both",
                                            "overflow": "hidden",
                                            "paddingBottom": "10px",
                                        },
                                    ),
                                    className="p-1",
                                ),
                            ],
                        ),
                        # Resize hint. width:0 / minWidth:100% so this caption
                        # fills the column but never widens it (keeps the map the
                        # sole width driver). whiteSpace normal lets it wrap.
                        html.Div(
                            "⤡ Drag the map's bottom-right corner to resize it — "
                            "narrow it to give the NSD plot more width.",
                            className="text-muted",
                            style={
                                "width": "0",
                                "minWidth": "100%",
                                "whiteSpace": "normal",
                                "fontSize": "0.7rem",
                                "margin": "2px 0 4px 0",
                            },
                        ),
                        # Notes + road crossing indicators
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            dbc.Col(
                                                [
                                                    dbc.Label("Classification", style={"fontSize": "0.8rem"}),
                                                    html.Div(
                                                        [
                                                            dbc.RadioItems(
                                                                id="animal-classification",
                                                                options=[
                                                                    {"label": "Resident", "value": "resident"},
                                                                    {"label": "Nomadic", "value": "nomadic"},
                                                                    {"label": "Migratory", "value": "migratory"},
                                                                ],
                                                                value=None,
                                                                inline=True,
                                                                style={"fontSize": "0.8rem"},
                                                                labelStyle={"marginRight": "1.25rem"},
                                                                className="d-inline-block me-2",
                                                            ),
                                                            dbc.Button(
                                                                "Unclassify",
                                                                id="btn-unclassify",
                                                                color="secondary",
                                                                outline=True,
                                                                size="sm",
                                                                className="py-0",
                                                            ),
                                                        ],
                                                        className="mb-2 d-flex align-items-center",
                                                    ),
                                                ],
                                            ),
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Notes", style={"fontSize": "0.8rem"}),
                                                        dbc.Textarea(
                                                            id="animal-notes",
                                                            placeholder="e.g. Migration identified, resident animal...",
                                                            # Auto-save: send the value to the server 800 ms after
                                                            # the user stops typing (and immediately on blur /
                                                            # animal navigation). One small write per pause — no
                                                            # per-keystroke round-trip. See autosave_animal_notes.
                                                            debounce=800,
                                                            style={"fontSize": "0.8rem", "height": "60px", "resize": "vertical"},
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Road Crossings", style={"fontSize": "0.8rem"}),
                                                        html.Div(
                                                            [
                                                                html.Div(
                                                                    [html.Strong("Crosses Road: ", style={"fontSize": "0.8rem"}),
                                                                     html.Span(id="crosses-road-badge", children="—",
                                                                               className="badge", style={"fontSize": "0.8rem"})],
                                                                    className="mb-1",
                                                                ),
                                                                html.Div(
                                                                    [html.Strong("Crosses Highway: ", style={"fontSize": "0.8rem"}),
                                                                     html.Span(id="crosses-highway-badge", children="—",
                                                                               className="badge", style={"fontSize": "0.8rem"})],
                                                                ),
                                                            ],
                                                        ),
                                                    ],
                                                    width=3,
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Notes save automatically", style={"fontSize": "0.7rem"}, className="text-muted"),
                                                        # Notes auto-save (textarea debounce=800 →
                                                        # autosave_animal_notes). This div just surfaces the
                                                        # "✓ Saved" indicator; there's no manual save button.
                                                        html.Div(id="notes-save-status", className="mt-1 small"),
                                                    ],
                                                    width=3,
                                                ),
                                            ],
                                        ),
                                    ],
                                    className="py-2 px-3",
                                ),
                            ],
                            className="mt-1",
                            # width:0 / minWidth:100% — fill the column but don't
                            # let this card's text widen it (so the map stays the
                            # sole width driver). See the map wrapper comment.
                            style={"width": "0", "minWidth": "100%"},
                        ),
                        # ----- Point flagging controls -----
                        # The MapLibre iframe supports click / shift+click /
                        # shift+drag selection. Whatever's selected gets sent
                        # to store-tab2-selection via a postMessage bridge.
                        # The four buttons below act on that selection.
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    html.Small(
                                                        [
                                                            html.Strong("Flag selected points: "),
                                                            html.Span(id="seq-selection-count", children="0 selected"),
                                                            html.Span(
                                                                " — click a point (Shift+click adds, Shift+drag = box-select)",
                                                                className="text-muted",
                                                            ),
                                                        ],
                                                    ),
                                                    width=12,
                                                ),
                                            ],
                                            className="mb-1",
                                        ),
                                        dbc.ButtonGroup(
                                            [
                                                dbc.Button(
                                                    "Flag as Problem",
                                                    id="btn-flag-problem",
                                                    color="danger",
                                                    size="sm",
                                                ),
                                                dbc.Button(
                                                    "Flag as Mortality",
                                                    id="btn-flag-mortality",
                                                    color="secondary",
                                                    size="sm",
                                                ),
                                                dbc.Button(
                                                    "Unflag Selected",
                                                    id="btn-unflag",
                                                    color="info",
                                                    size="sm",
                                                ),
                                                dbc.Button(
                                                    "Clear Selection",
                                                    id="btn-clear-selection",
                                                    color="link",
                                                    size="sm",
                                                ),
                                            ],
                                            className="w-100",
                                        ),
                                        html.Div(id="seq-flag-status", className="small mt-1"),
                                    ],
                                    className="py-2 px-3",
                                ),
                            ],
                            className="mt-1",
                            # Same neutralisation as the notes card above.
                            style={"width": "0", "minWidth": "100%"},
                        ),
                    ],
                    # Content-sized map column. width="auto" => Bootstrap
                    # `col-auto` (flex: 0 0 auto), so the column width tracks its
                    # widest content. The map wrapper above is the width driver
                    # (it has an explicit, resizable width); the notes/flag cards
                    # are neutralised (width:0 / minWidth:100%) so their text
                    # doesn't widen the column. Net effect: dragging the map's
                    # corner narrower shrinks this whole column, and the flex-grow
                    # NSD column to the left expands to fill the freed space.
                    width="auto",
                    style={
                        "flex": "0 0 auto",
                        "overflow": "hidden",
                    },
                ),
            ]
        ),
    ],
    className="mt-3",
)


# ---------------------------------------------------------------------------
# Tab 3: Modeling
# ---------------------------------------------------------------------------
# Two-column shape:
#   LEFT (width=4): Model Selection card.
#     - `model-select` dropdown swaps `model-param-panel` (built dynamically
#       by render_model_params, one parameter set per method).
#     - `model-cores` slider — capped at os.cpu_count(); default = half-cores.
#       Currently the executor only parallelises across sequences in
#       run_all_sequences, so n_cores > n_sequences has no effect.
#     - `model-auto-logic` surfaces the auto-parameter overrides decided in
#       modeling.get_model_config (e.g., "Fix rate > 12h → bm_var fixed at
#       1000"). Updated by the same callback that builds the param panel.
#     - Run Models fires run_modeling, which writes to _MODEL_CACHE and
#       returns a results-table HTML payload.
#   RIGHT (width=8): status banner + dbc.Progress bar (toggled visible by a
#     clientside callback during long runs) + DataTable of per-sequence
#     metadata. All three sit inside one dcc.Loading.
#
# CTMM and dBBMM call R via Rscript subprocess; CTMM falls back to Kernel UD
# and dBBMM falls back to regular BBMM if R or required packages are missing.
tab3_layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            [
                # LEFT: model controls
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader("Model Selection"),
                                dbc.CardBody(
                                    [
                                        dcc.Dropdown(
                                            id="model-select",
                                            options=[
                                                {"label": "BBMM (Brownian Bridge)", "value": "BBMM"},
                                                {"label": "dBBMM (Dynamic BBMM)", "value": "DBBMM"},
                                                {"label": "Kernel UD", "value": "Kernel"},
                                                {"label": "CTMM", "value": "CTMM"},
                                                {"label": "Line Buffer", "value": "LineBuffer"},
                                            ],
                                            value="Kernel",
                                            clearable=False,
                                            className="mb-3",
                                        ),
                                        html.Div(id="model-param-panel"),
                                        html.Div([
                                            _info_label("Number of Cores",
                                                       "The number of cores in this slider changes based on the number of "
                                                       "cores available on your device. This slider sets how many sequences "
                                                       "are modeled in parallel. More cores = faster total modeling time, but "
                                                       "uses more CPU and RAM. The default is half your available CPU cores "
                                                       "to leave headroom for the OS and the app itself.",
                                                       "4–5"),
                                        ], className="mt-3"),
                                        dcc.Slider(
                                            id="model-cores",
                                            min=1,
                                            max=os.cpu_count() or 4,
                                            step=1,
                                            value=max(1, (os.cpu_count() or 4) // 2),
                                            marks={
                                                i: {"label": str(i), "style": {"color": "white"}}
                                                for i in range(1, (os.cpu_count() or 4) + 1)
                                            },
                                        ),
                                        html.Div(id="model-auto-logic", className="mt-2 small text-info"),
                                        dbc.Label("Output grid cell size (m)", className="mt-3", style={"fontSize": "0.85rem"}),
                                        dbc.Input(id="model-cell-size", type="number", value=250, min=10, step=10),
                                        html.Small(
                                            "Resolution of the UD (utilization distribution) / footprint / population rasters. Default 250 m. "
                                            "Larger = coarser & faster.",
                                            className="text-muted d-block mb-1", style={"fontSize": "0.7rem"},
                                        ),
                                        dbc.Button(
                                            "Run Models",
                                            id="btn-run-models",
                                            color="success",
                                            className="w-100 mt-3",
                                        ),
                                        html.Hr(className="my-2"),
                                        dbc.Button(
                                            "Load Previous Results",
                                            id="btn-load-model-results",
                                            color="info",
                                            outline=True,
                                            size="sm",
                                            className="w-100",
                                        ),
                                        html.Small(
                                            "Loads the UD / footprint GeoTIFFs already in this working "
                                            "directory's ModelOutputs/ (and any saved population outputs) "
                                            "so you can skip re-running the models.",
                                            className="text-muted d-block mt-1",
                                            style={"fontSize": "0.7rem"},
                                        ),
                                    ]
                                ),
                            ]
                        )
                    ],
                    width=4,
                ),
                # RIGHT: progress + results
                dbc.Col(
                    [
                        dcc.Loading(
                            type="circle",
                            children=[
                                html.Div(id="model-status", className="mb-2"),
                                html.Div(
                                    dbc.Progress(id="model-progress", value=0, className="mb-3"),
                                    id="model-progress-wrapper",
                                    style={"display": "none"},  # toggled by clientside callback
                                ),
                                html.Div(id="model-results-table"),
                            ],
                        )
                    ],
                    width=8,
                ),
            ]
        )
    ],
    className="mt-3",
)


# ---------------------------------------------------------------------------
# Tab 4: Population Outputs
# ---------------------------------------------------------------------------
# Two-column shape. All controls feed generate_pop_outputs, which reads the
# per-sequence UDs out of _MODEL_CACHE (populated by Tab 3) and produces
# population-level contour polygons.
#
#   LEFT (width=4): Population Output Settings card.
#     - pop-seasons         — which sequence labels to merge ("Spring",
#                             "Fall"; auto-refreshed by
#                             refresh_pop_seasons_checklist when Tab 3 runs
#                             produce more season names).
#     - pop-merge-order     — id_year vs year_id. Controls whether we collapse
#                             across years per animal first OR across animals
#                             per year first; see calc_population_use docstring
#                             for the math.
#     - pop-contour-type    — area (proportion of individuals whose UD > 0 at
#                             a cell) vs volume (cumulative UD volume rank).
#     - pop-contour-levels  — free-text comma-sep list. Each level is the %
#                             of sequences that must overlap a cell for the
#                             cell to be inside that contour. 5-30% is the
#                             common corridor band; >50% is rare bottlenecks.
#     - pop-min-drop /
#       pop-min-fill        — cleanup pass on the contour polygons. Drop
#                             polygons smaller than min_drop m²; fill holes
#                             smaller than min_fill m².
#     - pop-smooth-toggle /
#       pop-smooth-bw       — optional Gaussian smoothing of the UD raster
#                             before contouring.
#   RIGHT (width=8): pop-status banner + pop-map-preview (a small leaflet/Tab 5
#     preview rendered after generation completes).
tab4_layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader("Population Output Settings"),
                                dbc.CardBody(
                                    [
                                        _info_label("Seasons to Merge",
                                                   "Select which migration seasons to include when building "
                                                   "the population-level surface. Sequences from checked seasons "
                                                   "are stacked together.",
                                                   "Spring + Fall (both checked)"),
                                        dbc.Checklist(
                                            id="pop-seasons",
                                            options=[
                                                {"label": "Spring", "value": "Spring"},
                                                {"label": "Fall", "value": "Fall"},
                                            ],
                                            value=["Spring", "Fall"],
                                            className="mb-2",
                                            inline=True,
                                        ),
                                        _info_label("Merge Order",
                                                   "Controls the order in which individual sequences are "
                                                   "stacked onto the population grid. 'ID first' groups all "
                                                   "years for each animal, then moves to the next animal. "
                                                   "'Year first' groups all animals within a year, then moves "
                                                   "to the next year.",
                                                   "ID first, then Year"),
                                        dcc.Dropdown(
                                            id="pop-merge-order",
                                            options=[
                                                {"label": "ID first, then Year", "value": "id_year"},
                                                {"label": "Year first, then ID", "value": "year_id"},
                                            ],
                                            value="id_year",
                                            clearable=False,
                                            className="mb-2",
                                        ),
                                        _info_label("Contour Type",
                                                   "Area: each contour level is the percentage of sequences "
                                                   "whose UDs (utilization distributions) overlap a cell. "
                                                   "Volume: each level is based on the cumulative UD volume rank "
                                                   "(isopleth), similar to home-range contours.",
                                                   "Area"),
                                        dcc.RadioItems(
                                            id="pop-contour-type",
                                            options=[
                                                {"label": " Area", "value": "area"},
                                                {"label": " Volume", "value": "volume"},
                                            ],
                                            value="area",
                                            className="mb-2",
                                            inline=True,
                                            labelStyle={"color": "white"},
                                        ),
                                        _info_label("Contour Levels (%)",
                                                   "Comma-separated list of percentage thresholds for generating "
                                                   "population corridor polygons. Each level produces a separate "
                                                   "shapefile. Lower values capture broader use areas; higher values "
                                                   "capture only the most heavily used corridors.",
                                                   "5, 10, 15, 20, 30, 50"),
                                        dbc.Input(
                                            id="pop-contour-levels",
                                            type="text",
                                            value="5, 10, 15, 20, 30, 50",
                                            placeholder="e.g. 5, 10, 15, 20, 30, 50",
                                            className="mb-1",
                                        ),
                                        html.Small(
                                            "Each level is the percentage of sequences whose UDs (utilization distributions) overlap a cell. "
                                            "For migration corridors, 5-30% gives broad-use polygons; >50% would "
                                            "require majority overlap and is rare except at bottlenecks.",
                                            className="text-muted d-block mb-2",
                                            style={"fontSize": "0.72rem"},
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        _info_label("Min Area Drop (m²)",
                                                                   "Polygon fragments smaller than this area are removed "
                                                                   "from the contour output. Eliminates tiny isolated "
                                                                   "patches that are too small to be ecologically meaningful.",
                                                                   "10,000 m²"),
                                                        dbc.Input(id="pop-min-drop", type="number", value=10000, min=0),
                                                    ],
                                                    width=6,
                                                ),
                                                dbc.Col(
                                                    [
                                                        _info_label("Min Area Fill (m²)",
                                                                   "Interior holes in contour polygons smaller than this "
                                                                   "area are filled in. Prevents small donut holes from "
                                                                   "fragmenting otherwise continuous corridors.",
                                                                   "5,000 m²"),
                                                        dbc.Input(id="pop-min-fill", type="number", value=5000, min=0),
                                                    ],
                                                    width=6,
                                                ),
                                            ],
                                            className="mb-2",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        _info_label("Smoothing",
                                                                   "When enabled, contour polygon outlines are smoothed "
                                                                   "after generation. This rounds jagged pixel-staircase "
                                                                   "edges without changing the underlying raster surface.",
                                                                   "On"),
                                                        dbc.Switch(id="pop-smooth-toggle", value=True, label=""),
                                                    ],
                                                    width=4,
                                                ),
                                                dbc.Col(
                                                    [
                                                        _info_label("Smoothness — ksmooth",
                                                                   "Controls how aggressively the contour outlines are "
                                                                   "smoothed. A port of R's smoothr::smooth ksmooth — same "
                                                                   "parameter as Migration Mapper's ksmooth_smoothness. "
                                                                   "Higher values produce rounder edges; polygon areas are "
                                                                   "preserved.",
                                                                   "2"),
                                                        dbc.Input(id="pop-smooth-bw", type="number", value=2, min=0, step=0.5),
                                                    ],
                                                    width=8,
                                                ),
                                            ],
                                            className="mb-1",
                                        ),
                                        dbc.Checkbox(
                                            id="pop-stopover-toggle",
                                            value=True,
                                            label="Calculate stopovers",
                                            style={"fontSize": "0.85rem"},
                                            className="mb-1",
                                        ),
                                        dbc.Collapse(
                                            [
                                                _info_label("Stopover Density (%)",
                                                           "The top X% of the population-level UD (Utilization Distribution; "
                                                           "probability density) surface is classified as stopover habitat — "
                                                           "areas where animals concentrate during migration. Consistent with "
                                                           "WMI's Migration Mapper methodology.",
                                                           "10%"),
                                                dbc.Input(
                                                    id="pop-stopover-pct",
                                                    type="number",
                                                    value=10,
                                                    min=0,
                                                    max=100,
                                                    step=1,
                                                ),
                                                html.Small(
                                                    "Recommended: 10 — the top 10% of the population-level UD (utilization distribution) "
                                                    "considered as stopovers, consistent with WMI's Migration Mapper.",
                                                    className="text-muted d-block mb-2",
                                                    style={"fontSize": "0.72rem"},
                                                ),
                                            ],
                                            id="pop-stopover-collapse",
                                            is_open=True,
                                        ),
                                        dbc.Checkbox(
                                            id="pop-minimumx-toggle",
                                            value=False,
                                            label="Custom MinimumX layer",
                                            style={"fontSize": "0.85rem"},
                                            className="mt-2 mb-1",
                                        ),
                                        dbc.Collapse(
                                            [
                                                _info_label("Minimum number of animals — MinimumX",
                                                           "The app automatically outputs layers showing cells used by "
                                                           "at least 2 and at least 3 animals. This option lets you define "
                                                           "a custom X — the output is a clipped raster and smoothed polygon "
                                                           "showing cells where at least X animals used the area.",
                                                           "4"),
                                                html.Span(id="pop-minimumx-label", style={"display": "none"}),
                                                dbc.Input(
                                                    id="pop-minimumx-value",
                                                    type="number",
                                                    value=4,
                                                    min=1,
                                                    max=999,
                                                    step=1,
                                                ),
                                            ],
                                            id="pop-minimumx-collapse",
                                            is_open=False,
                                        ),
                                        dbc.Button(
                                            "Generate Population Outputs",
                                            id="btn-gen-pop",
                                            color="primary",
                                            className="w-100 mt-2",
                                        ),
                                        html.Hr(className="my-2"),
                                        dbc.Button(
                                            "Load Previous Population Outputs",
                                            id="btn-load-pop-outputs",
                                            color="info",
                                            outline=True,
                                            size="sm",
                                            className="w-100",
                                        ),
                                        html.Small(
                                            "Loads the saved contour shapefiles from "
                                            "this working directory so you can view them in Tab 5 without "
                                            "re-generating.",
                                            className="text-muted d-block mt-1",
                                            style={"fontSize": "0.7rem"},
                                        ),
                                    ]
                                ),
                            ]
                        )
                    ],
                    width=4,
                ),
                dbc.Col(
                    [
                        dcc.Loading(
                            type="circle",
                            children=[
                                html.Div(id="pop-status", className="mb-2"),
                                html.Div(id="pop-map-preview"),
                            ],
                        )
                    ],
                    width=8,
                ),
            ]
        )
    ],
    className="mt-3",
)


# ---------------------------------------------------------------------------
# Tab 5: Interactive Map & Export
# ---------------------------------------------------------------------------
# Two-column shape. This tab uses dash-leaflet (NOT the MapLibre iframe that
# Tab 2 uses) because it needs to layer multiple GeoJSON sources with Dash
# callbacks driving visibility. The trade-off: less basemap polish than Tab 2,
# but tighter integration with Dash callbacks for export.
#
#   LEFT (width=3):
#     - Layer Controls card — `map-layers` Checklist drives which GeoJSON
#       layers are populated by update_map_layers (raw points, tracks,
#       footprints, pop-use contours). `map-base-layer` swaps between OSM
#       tiles and Esri World Imagery.
#     - Export card — a checklist of the Tab 4 population outputs held in
#       memory (built by populate_export_checklist from the store-pop-outputs
#       manifest) plus "Export Selected" / "Export All" buttons handled by
#       handle_export. Fully deferred: Tab 4 computes products into
#       _POP_OUTPUT_CACHE and nothing touches disk until exported here. Output
#       goes to `export-dir`; if blank, falls back to the active workdir.
#   RIGHT (width=9):
#     - dl.Map with `preferCanvas=True` for performance with large point
#       layers. Default tile source is Esri satellite (the TileLayer here is
#       the default; the `map-base-layer` radio swaps it via a callback that
#       isn't shown in this layout — see callbacks section).
#     - dl.GeoJSON layers (tracks / points / contours) — initially empty
#       FeatureCollections, populated by update_map_layers. The points layer
#       uses _seq_point_style (a JS function in assets/map_functions.js) for
#       per-point styling so points can carry colour by sequence without
#       spawning a Marker per point.
#     - raster-overlay-group: a dl.LayerGroup holding one dl.ImageOverlay per
#       selected .tif (multi-select picker + "Select all in category"), so any
#       number of output rasters can be stacked. PNG builds are memoised
#       (_OVERLAY_CACHE) so the opacity slider is cheap.
#     - vector-overlay-group: a dl.LayerGroup holding one coloured dl.GeoJSON
#       per selected .shp/.geojson found recursively under ModelOutputs/.
#     - map-click-info — populated by a click callback (not shown) to surface
#       feature attributes on click.
tab5_layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            [
                # LEFT: export panel
                dbc.Col(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader("Layer Controls"),
                                dbc.CardBody(
                                    [
                                        dbc.Checklist(
                                            id="map-layers",
                                            options=[
                                                {"label": "Raw Points", "value": "raw_points"},
                                                {"label": "Migration Tracks", "value": "tracks"},
                                                {"label": "Footprint Contours", "value": "footprints"},
                                                {"label": "Population Use Contours", "value": "pop_contours"},
                                            ],
                                            value=["raw_points", "tracks"],
                                            className="mb-2",
                                        ),
                                        dbc.Label("Base Layer", style={"fontSize": "0.85rem", "color": "#FFFFFF"}),
                                        dcc.RadioItems(
                                            id="map-base-layer",
                                            options=[
                                                {"label": " Topographic", "value": "topo"},
                                                {"label": " Satellite", "value": "esri"},
                                            ],
                                            value="esri",
                                            labelStyle={"color": "#FFFFFF", "display": "block", "fontSize": "0.85rem"},
                                            inputStyle={"marginRight": "6px"},
                                            className="mb-2",
                                        ),
                                    ]
                                ),
                            ],
                            className="mb-3",
                        ),
                        # Output overlays — raster and vector in one card,
                        # each in its own accordion item.
                        dbc.Card(
                            [
                                dbc.CardHeader("Output Overlays"),
                                dbc.CardBody(
                                    dbc.Accordion(
                                        [
                                            dbc.AccordionItem(
                                                [
                                                    html.Div(
                                                        id="raster-tree-container",
                                                        style={
                                                            "maxHeight": "360px",
                                                            "overflowY": "auto",
                                                            "fontSize": "0.8rem",
                                                        },
                                                    ),
                                                    dcc.Store(id="raster-overlay-file", data=[]),
                                                    dcc.Store(id="raster-overlay-category", data=""),
                                                    dbc.Button(
                                                        "Clear overlay",
                                                        id="btn-clear-raster-overlay",
                                                        color="secondary", outline=True, size="sm",
                                                        className="w-100 mt-2",
                                                    ),
                                                    dbc.Button(
                                                        "Select all",
                                                        id="btn-select-all-rasters",
                                                        color="secondary", outline=True, size="sm",
                                                        className="w-100 mt-1",
                                                        style={"display": "none"},
                                                    ),
                                                    html.Hr(className="my-2"),
                                                    dbc.Label("Colour scale", style={"fontSize": "0.85rem"}),
                                                    dcc.Dropdown(
                                                        id="raster-overlay-cmap",
                                                        options=[
                                                            {"label": "Viridis", "value": "viridis"},
                                                            {"label": "Black & white", "value": "gray"},
                                                        ],
                                                        value="viridis",
                                                        clearable=False,
                                                        style={"fontSize": "0.82rem", "marginBottom": "8px"},
                                                        className="dash-dark-dropdown",
                                                    ),
                                                    dbc.Label("Opacity", style={"fontSize": "0.85rem"}),
                                                    dcc.Slider(
                                                        id="raster-overlay-opacity",
                                                        min=0, max=1, step=0.05, value=1,
                                                        marks={i: {"label": str(i), "style": {"color": "white"}} for i in [0, 0.5, 1]},
                                                    ),
                                                    html.Div(id="raster-overlay-info", className="mt-2 small text-muted"),
                                                ],
                                                title="Raster (.tif)",
                                            ),
                                            dbc.AccordionItem(
                                                [
                                                    html.Div(
                                                        id="vector-tree-container",
                                                        style={
                                                            "maxHeight": "300px",
                                                            "overflowY": "auto",
                                                            "fontSize": "0.8rem",
                                                        },
                                                    ),
                                                    dcc.Store(id="vector-overlay-files", data=[]),
                                                    dbc.Button(
                                                        "Select all",
                                                        id="btn-select-all-vectors",
                                                        color="secondary", outline=True, size="sm",
                                                        className="w-100 mt-1",
                                                        style={"display": "none"},
                                                    ),
                                                    dbc.Button(
                                                        "Refresh list",
                                                        id="btn-refresh-vectors",
                                                        color="secondary", outline=True, size="sm",
                                                        className="w-100 mt-1",
                                                    ),
                                                    html.Hr(className="my-2"),
                                                    dbc.Label("Fill opacity", style={"fontSize": "0.85rem"}),
                                                    dcc.Slider(
                                                        id="vector-overlay-opacity",
                                                        min=0, max=1, step=0.05, value=0.35,
                                                        marks={i: {"label": str(i), "style": {"color": "white"}} for i in [0, 0.5, 1]},
                                                    ),
                                                    html.Div(id="vector-overlay-info", className="mt-2 small text-muted"),
                                                ],
                                                title="Vector (.shp / .geojson)",
                                            ),
                                        ],
                                        start_collapsed=True,
                                        always_open=True,
                                    ),
                                ),
                            ],
                            className="mb-3",
                        ),
                        dbc.Card(
                            [
                                dbc.CardHeader("Export"),
                                dbc.CardBody(
                                    [
                                        dbc.Label("Output Directory", style={"fontSize": "0.85rem"}),
                                        dbc.Input(
                                            id="export-dir",
                                            type="text",
                                            placeholder="e.g. C:/output/results",
                                            className="mb-2",
                                        ),
                                        # Checkbox list of the Tab 4 population
                                        # outputs currently held in memory. Built
                                        # by populate_export_checklist from the
                                        # store-pop-outputs manifest; empty until
                                        # Tab 4 has generated outputs this session.
                                        dbc.Accordion(
                                            [
                                                dbc.AccordionItem(
                                                    [
                                                        dbc.Row(
                                                            [
                                                                dbc.Col(
                                                                    dbc.Button(
                                                                        "Select all",
                                                                        id="btn-export-select-all",
                                                                        color="secondary", outline=True, size="sm",
                                                                        className="w-100",
                                                                    ),
                                                                    width=6,
                                                                ),
                                                                dbc.Col(
                                                                    dbc.Button(
                                                                        "Clear",
                                                                        id="btn-export-clear",
                                                                        color="secondary", outline=True, size="sm",
                                                                        className="w-100",
                                                                    ),
                                                                    width=6,
                                                                ),
                                                            ],
                                                            className="g-1 mb-2",
                                                        ),
                                                        html.Div(
                                                            id="export-checklist-wrap",
                                                            style={
                                                                "maxHeight": "280px",
                                                                "overflowY": "auto",
                                                                "border": "1px solid #444",
                                                                "borderRadius": "6px",
                                                                "padding": "8px",
                                                                "marginBottom": "8px",
                                                            },
                                                        ),
                                                    ],
                                                    title="Outputs",
                                                    item_id="outputs-accordion",
                                                ),
                                            ],
                                            start_collapsed=True,
                                            className="mb-2",
                                        ),
                                        html.Div(
                                            "Generate population outputs in Tab 4 first — "
                                            "they are held in memory until you export here.",
                                            id="export-checklist-empty",
                                            className="small text-muted mb-2",
                                        ),
                                        dbc.Button(
                                            "Export Selected",
                                            id="btn-export-selected",
                                            color="primary",
                                            className="w-100 mb-2",
                                            size="sm",
                                        ),
                                        dbc.Button(
                                            "Export All",
                                            id="btn-export-all",
                                            color="secondary",
                                            className="w-100 mb-2",
                                            size="sm",
                                        ),
                                        dbc.Button(
                                            "Export Recommended for Bios",
                                            id="btn-export-bios",
                                            color="info",
                                            className="w-100",
                                            size="sm",
                                        ),
                                        html.Div(id="export-status", className="mt-2"),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    width=3,
                ),
                # RIGHT: map
                dbc.Col(
                    [
                        dl.Map(
                            id="main-map",
                            center=[39.5, -105.5],
                            zoom=7,
                            style={"height": "70vh", "borderRadius": "8px"},
                            preferCanvas=True,
                            children=[
                                dl.TileLayer(
                                    id="base-tile-layer",
                                    url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                                    attribution="Esri",
                                    maxZoom=18,
                                ),
                                dl.GeoJSON(
                                    id="map-geojson-tracks",
                                    data={"type": "FeatureCollection", "features": []},
                                ),
                                dl.GeoJSON(
                                    id="map-geojson-points",
                                    data={"type": "FeatureCollection", "features": []},
                                    options=dict(pointToLayer=_seq_point_style),
                                ),
                                # One or more stacked raster overlays (.tif).
                                dl.LayerGroup(id="raster-overlay-group", children=[]),
                                dl.GeoJSON(
                                    id="map-geojson-contours",
                                    data={"type": "FeatureCollection", "features": []},
                                    style=_contour_style,
                                ),
                                # One or more stacked vector overlays (.shp/.geojson).
                                dl.LayerGroup(id="vector-overlay-group", children=[]),
                            ],
                        ),
                        html.Div(id="map-click-info", className="mt-2 small text-muted"),
                    ],
                    width=9,
                ),
            ]
        )
    ],
    className="mt-3",
)


# ---------------------------------------------------------------------------
# Main layout with tabs
# ---------------------------------------------------------------------------
app.layout = dbc.Container(
    fluid=True,
    children=[
        navbar,
        help_modal,
        # ---- Application state stores ----
        # Each dcc.Store is one slot of client-side state shared between
        # callbacks. Default storage_type is "memory" (lost on page reload);
        # "local" persists in browser localStorage across reloads.
        #
        # For "processed", "migtime-table", "model-results", and "pop-outputs"
        # the actual data lives in process-memory caches (_DF_CACHE /
        # _MODEL_CACHE); these stores only carry tiny tokens like
        # {"__cache_key": "processed", "rows": 12345}. See _df_to_json /
        # _json_to_df. This avoids the OOM bug from large JSON payloads.
        dcc.Store(id="store-processed-data"),    # token → _DF_CACHE["processed"] (rehydrates from parquet)
        dcc.Store(id="store-migtime-table"),     # token → _DF_CACHE["migtime"]   (regen by Tab 2 only)
        dcc.Store(id="store-seq-names", data=[]), # current Seq 1..n labels (from the Sequence Names inputs);
                                                  # the single source of truth for sequence labels shown on
                                                  # the NSD chart, slider cards, and exported migtime table
                                                  # so a rename propagates everywhere.
        dcc.Store(id="store-model-results"),     # token → _MODEL_CACHE           (regen by Tab 3 only)
        dcc.Store(id="store-config"),            # pipeline config from Process Data
        dcc.Store(id="store-animal-index", data=0),       # currently-selected animal-year index (Tab 2 nav)
        dcc.Store(id="store-slider-date-min", data=None), # ISO date string mirrored into window._sliderDateMin
                                                          # by a clientside callback so slider tooltip JS
                                                          # (dayToDate in map_functions.js) can render dates
        dcc.Store(id="store-pop-outputs"),       # token → population output cache (Tab 4)
        dcc.Store(id="store-upload-path"),       # temp file path from upload (consumed by Process Data)
        dcc.Store(id="store-migtime-import-raw"), # raw text of an uploaded external migtime CSV (Tab 1 importer)
        dcc.Store(id="store-wld-upload-path"),   # temp file path from .wld upload (optional)
        dcc.Store(id="store-wld-env-labels", data={}),    # {col_name: human_label} for popup display
        dcc.Store(id="store-workdir", data=""),  # active working directory path — session-only
                                                 # (NOT local-storage — different machine setups must not
                                                 # auto-restore stale paths)
        dcc.Store(id="store-tab2-selection", data=[]),    # ISO-date keys of points selected via the
                                                          # MapLibre iframe's postMessage bridge
        dcc.Store(id="store-animal-notes", data={}, storage_type="local"),  # persists per-browser across sessions
        dcc.Store(id="store-animal-classification", data={}, storage_type="local"),  # id_bio_year -> resident/nomadic/migratory
        dcc.Store(id="store-map-payload"),       # JSON payload sent into MapLibre iframe (Tab 2)
        dcc.Store(id="store-road-crossings", data={}),    # animal_key -> {road: bool, highway: bool}
        dcc.Store(id="store-model-run-id", data=None),    # unique id when a background model run is active
        dcc.Interval(id="model-poll-interval", interval=3000, disabled=True),
        dbc.Tabs(
            id="main-tabs",
            active_tab="tab-1",
            children=[
                dbc.Tab(tab1_layout, label="1 · Data Import & Cleaning", tab_id="tab-1"),
                dbc.Tab(tab2_layout, label="2 · Migration Sequencing", tab_id="tab-2"),
                dbc.Tab(tab3_layout, label="3 · Modeling", tab_id="tab-3"),
                dbc.Tab(tab4_layout, label="4 · Population Outputs", tab_id="tab-4"),
                dbc.Tab(tab5_layout, label="5 · Map & Export", tab_id="tab-5"),
            ],
        ),
    ],
    style={"backgroundColor": "#111", "minHeight": "100vh", "paddingBottom": "40px"},
)


@app.callback(
    Output("help-guide-modal", "is_open"),
    Input("help-guide-btn", "n_clicks"),
    State("help-guide-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_help_modal(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open


# ===========================================================================
# Working directory — pick a folder, scaffold ModelInputs/ModelOutputs/log,
# track recents, persist across sessions.
#
# Two callbacks write to `store-workdir`: pick_workdir (Browse button) and
# pick_workdir_from_recents (dropdown). Dash requires `allow_duplicate=True`
# on every Output that's claimed by more than one callback — the pattern is
# repeated throughout main.py wherever multiple controls can mutate the
# same state slot.
# ===========================================================================

@app.callback(
    Output("store-workdir", "data", allow_duplicate=True),
    Input("btn-pick-workdir", "n_clicks"),
    prevent_initial_call=True,
)
def pick_workdir(n_clicks):
    """Open a native folder picker and set the working directory."""
    if not n_clicks:
        raise PreventUpdate
    chosen = _pick_directory_native()
    if not chosen:
        raise PreventUpdate
    resolved = _set_active_workdir(chosen)
    return str(resolved)


@app.callback(
    Output("store-workdir", "data", allow_duplicate=True),
    Output("workdir-recents", "options", allow_duplicate=True),
    Output("workdir-recents", "value", allow_duplicate=True),
    Input("workdir-recents", "value"),
    prevent_initial_call=True,
)
def pick_workdir_from_recents(selected):
    """Recents dropdown selection sets the working directory.

    The synthetic ``__CLEAR_ALL__`` value (last option in the dropdown) wipes
    the recent_workdirs.json file and does NOT touch the active workdir.
    """
    if not selected:
        raise PreventUpdate
    if selected == "__CLEAR_ALL__":
        try:
            if _RECENT_WORKDIRS_FILE.exists():
                _RECENT_WORKDIRS_FILE.unlink()
        except Exception:
            pass
        return dash.no_update, [], None
    if not Path(selected).is_dir():
        raise PreventUpdate
    resolved = _set_active_workdir(selected)
    return str(resolved), dash.no_update, dash.no_update


@app.callback(
    Output("workdir-display", "value"),
    Output("workdir-status", "children"),
    Output("workdir-recents", "options"),
    Input("store-workdir", "data"),
    Input("main-tabs", "active_tab"),
)
def render_workdir_state(workdir_path, _active_tab):
    """Reflect the active workdir back into the UI."""
    # _active_tab is in the Input list so the workdir display also refreshes on
    # tab switches — e.g., the log size in the status string is "live" without
    # needing a dedicated Interval timer.
    global _ACTIVE_WORKDIR, _ACTIVE_VERSION
    # If the store has a path but our process-level state doesn't, sync — this
    # is how the workdir gets restored on app reload: the browser keeps the
    # store value but the Python process forgot _ACTIVE_WORKDIR on restart.
    if workdir_path and (_ACTIVE_WORKDIR is None or str(_ACTIVE_WORKDIR) != workdir_path):
        try:
            if Path(workdir_path).is_dir():
                _ACTIVE_WORKDIR = Path(workdir_path).resolve()
                # Re-adopt the latest on-disk output version + branch-tracking.
                _vers = _list_versions(_ACTIVE_WORKDIR)
                _ACTIVE_VERSION = _vers[-1] if _vers else None
                _set_model_source(_latest_version_with_model(_ACTIVE_WORKDIR))
                _seed_pop_exported(_ACTIVE_WORKDIR)
        except Exception:
            pass

    recents_opts = [{"label": str(p), "value": str(p)} for p in _recent_workdirs()]
    if recents_opts:
        recents_opts.append({"label": "— Clear all recent directories —", "value": "__CLEAR_ALL__"})

    if not workdir_path:
        return "", html.Span("No working directory set. Click Browse to choose one.", className="text-muted"), recents_opts

    p = Path(workdir_path)
    if not p.is_dir():
        return workdir_path, html.Span(f"Path no longer exists: {workdir_path}", className="text-danger"), recents_opts

    inputs_p = p / "ModelInputs"
    outputs_p = p / "ModelOutputs"
    log_p = p / "session_log.txt"
    log_size = log_p.stat().st_size if log_p.exists() else 0
    status = html.Div([
        html.Div([html.Strong("Inputs: "), str(inputs_p)], style={"fontSize": "0.75rem"}),
        html.Div([html.Strong("Outputs: "), str(outputs_p)], style={"fontSize": "0.75rem"}),
        html.Div([html.Strong("Log: "), f"{log_p} ({log_size:,} bytes)"], style={"fontSize": "0.75rem"}),
    ], className="text-info")
    return str(p), status, recents_opts


# ===========================================================================
# Project management
# ===========================================================================

@app.callback(
    Output("project-selector", "options"),
    Input("main-tabs", "active_tab"),
    Input("store-processed-data", "data"),
)
def refresh_project_list(active_tab, _processed):
    # Re-runs when the user switches tabs OR when store-processed-data is
    # rewritten by a fresh Process Data run — so a newly-saved project shows
    # up in the dropdown immediately, no manual refresh needed.
    projects = _list_projects()
    opts = [{"label": p.replace("_", " "), "value": p} for p in projects]
    if opts:
        # Synthetic sentinel; handled by maybe_clear_all_projects below.
        opts.append({"label": "— Clear all previous projects —", "value": "__CLEAR_ALL__"})
    return opts


@app.callback(
    Output("project-selector", "options", allow_duplicate=True),
    Output("project-selector", "value", allow_duplicate=True),
    Output("project-load-status", "children", allow_duplicate=True),
    Input("project-selector", "value"),
    prevent_initial_call=True,
)
def maybe_clear_all_projects(selected):
    """When the user picks the synthetic '__CLEAR_ALL__' option, delete every
    project folder under app/session_data/ (each one's processed_data.parquet,
    animal_notes.json, road_crossings.json, project_meta.json). The user's
    working directory and its ModelOutputs/ are NOT touched."""
    if selected != "__CLEAR_ALL__":
        raise PreventUpdate
    import shutil
    deleted = 0
    try:
        for d in _PROJECTS_DIR.iterdir():
            if d.is_dir() and (d / "processed_data.parquet").exists():
                shutil.rmtree(d, ignore_errors=True)
                deleted += 1
    except Exception as exc:
        return dash.no_update, None, _err_alert(f"Clear failed: {exc}")
    return [], None, _ok_alert(f"Cleared {deleted} previous project(s) from session_data/.")


@app.callback(
    Output("store-processed-data", "data", allow_duplicate=True),
    Output("store-animal-notes", "data", allow_duplicate=True),
    Output("store-road-crossings", "data", allow_duplicate=True),
    Output("project-load-status", "children"),
    Output("project-name", "value"),
    Output("store-config", "data", allow_duplicate=True),
    Input("btn-load-project", "n_clicks"),
    State("project-selector", "value"),
    prevent_initial_call=True,
)
def load_project(n_clicks, project_name):
    if not project_name or project_name == "__CLEAR_ALL__":
        raise PreventUpdate

    # Hard reset both caches before loading — switching projects without this
    # would leave stale entries keyed on old animal IDs in _MAP_CACHE, which
    # the Tab 2 map would happily render alongside the new project's points.
    _DF_CACHE.clear()
    _MAP_CACHE.clear()

    saved_df = _load_processed_from_disk(project_name)
    if saved_df is None:
        return dash.no_update, dash.no_update, dash.no_update, _err_alert("No data found for this project."), dash.no_update, dash.no_update

    # Pre-populate _MAP_CACHE so the first Tab 2 render is instant. Without
    # this the first animal-select after load would block for several seconds
    # rebuilding the cache.
    _precompute_animal_maps(saved_df.copy())

    df_out = saved_df.copy()
    # dcc.Store payloads must be JSON-serialisable; pandas datetime dtypes
    # aren't, so cast every datetime column to its ISO-string form. The
    # cache holds the raw datetime version separately.
    for col in df_out.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        df_out[col] = df_out[col].astype(str)

    notes = _load_notes(project_name)

    road_crossings = {}
    rc_path = _project_dir(project_name) / "road_crossings.json"
    if rc_path.exists():
        road_crossings = json.loads(rc_path.read_text())

    # Restore config (including herd_id) from saved project metadata so
    # output file naming uses the original herd ID, not the "Herd" fallback.
    config_json = None
    meta = _load_project_meta(project_name)
    if meta and "config" in meta:
        config_json = json.dumps(meta["config"])
    elif project_name:
        config_json = json.dumps({"herd_id": project_name.split("_")[0]})

    n_animals = saved_df["animal_id"].nunique() if "animal_id" in saved_df.columns else "?"
    status = _ok_alert(f"Loaded {project_name.replace('_', ' ')} — {len(saved_df):,} points, {n_animals} animals")

    return _df_to_json(df_out, "processed"), notes, road_crossings, status, project_name.replace("_", " "), config_json


# ===========================================================================
# Callbacks — Tab 1: Data Import & Cleaning
# ===========================================================================

def _shp_sidecars_complete(shp_path: Path) -> bool:
    """True if a shapefile has all required sidecar files."""
    return all(shp_path.with_suffix(s).exists() for s in (".shp", ".shx", ".dbf", ".prj"))


def _create_companion_file_sync(file_path: Path) -> None:
    """If file_path is a CSV, create a companion .shp in the same folder.
    If it's a .shp, create a companion .csv. Silently skips if the companion
    already exists (with all sidecars) or if the conversion fails.
    Writes to a temp name first, then renames, so a partial write never
    blocks future retries."""
    import geopandas as gpd
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".csv":
            companion = file_path.with_suffix(".shp")
            if _shp_sidecars_complete(companion):
                return
            df = pd.read_csv(str(file_path), low_memory=False)
            lon_col = lat_col = utm_e_col = utm_n_col = utm_zone_col = None
            for c in df.columns:
                cl = c.lower()
                if cl in ("long", "lon", "longitude", "x"):
                    lon_col = c
                elif cl in ("lat", "latitude", "y"):
                    lat_col = c
                elif cl in ("utm_e", "utme", "easting", "utm_easting"):
                    utm_e_col = c
                elif cl in ("utm_n", "utmn", "northing", "utm_northing"):
                    utm_n_col = c
                elif cl in ("utm_zone", "utmzone", "zone"):
                    utm_zone_col = c
            gdf = None
            if lon_col and lat_col:
                gdf = gpd.GeoDataFrame(
                    df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
                    crs="EPSG:4326",
                )
            elif utm_e_col and utm_n_col:
                zone_num = None
                if utm_zone_col:
                    zone_num = int(pd.to_numeric(df[utm_zone_col], errors="coerce").dropna().mode().iloc[0])
                else:
                    for c in df.columns:
                        if "zone" in c.lower():
                            zone_num = int(pd.to_numeric(df[c], errors="coerce").dropna().mode().iloc[0])
                            break
                if zone_num:
                    crs = f"EPSG:326{zone_num:02d}"
                    gdf = gpd.GeoDataFrame(
                        df, geometry=gpd.points_from_xy(df[utm_e_col], df[utm_n_col]),
                        crs=crs,
                    )
                    gdf = gdf.to_crs("EPSG:4326")
            if gdf is not None:
                tmp_shp = file_path.with_suffix(".tmp.shp")
                gdf.to_file(tmp_shp)
                for s in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                    src = file_path.with_suffix(".tmp" + s)
                    dst = file_path.with_suffix(s)
                    if src.exists():
                        src.replace(dst)
        elif suffix == ".shp":
            companion = file_path.with_suffix(".csv")
            if companion.exists():
                return
            gdf = gpd.read_file(str(file_path))
            df = pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore"))
            if "geometry" in gdf.columns and not gdf.geometry.is_empty.all():
                df["lon"] = gdf.geometry.x
                df["lat"] = gdf.geometry.y
            df.to_csv(companion, index=False)
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "Companion file creation failed for %s: %s", file_path, exc
        )


def _create_companion_file(file_path: Path) -> None:
    """Run companion file creation in a background thread so it doesn't block
    the UI during file upload/selection."""
    import threading
    threading.Thread(
        target=_create_companion_file_sync,
        args=(file_path,),
        daemon=False,
    ).start()


def _preview_input_file(file_path: str | Path, display_name: str | None = None) -> tuple:
    """Read the first 200 rows of *file_path*, auto-detect common column names,
    and return the tuple of outputs the upload / auto-load callbacks expect.

    Tuple shape (matches the 26-output callback signature):
        (fname_display,
         col_opts x4, id_val, ts_val, lon_val, lat_val,
         preview_table, source_path,
         csv_warning_open, utm_toggle_style, utm_checked,
         utm_opts x2, utm_e_val, utm_n_val,
         lonlat_style, utm_group_style,
         dop_opts, sat_opts, dop_val, sat_val,
         age_opts, age_val)
    """
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    display_name = display_name or file_path.name

    _UTM_DEFAULTS = (
        False, {"display": "none"}, False,
        [], [], None, None,
        {"display": "block"}, {"display": "none"},
    )
    _DOP_SAT_DEFAULTS = ([], [], None, None)
    _AGE_DEFAULTS = ([], None)

    detected_crs = None

    if suffix == ".csv":
        df = pd.read_csv(str(file_path), nrows=200, low_memory=False)
        source_path = str(file_path)
    elif suffix == ".shp":
        import geopandas as gpd_local
        gdf_preview = gpd_local.read_file(str(file_path)).head(200)
        detected_crs = gdf_preview.crs
        df = gdf_preview
        source_path = str(file_path)
    elif suffix == ".zip":
        import zipfile
        zdir = tempfile.mkdtemp()
        with zipfile.ZipFile(str(file_path)) as z:
            z.extractall(zdir)
        shp_files = list(Path(zdir).rglob("*.shp"))
        if not shp_files:
            return (
                f"No .shp found in ZIP: {display_name}",
                [], [], [], [],
                None, None, None, None,
                _err_alert("No shapefile found inside the ZIP."),
                None,
                *_UTM_DEFAULTS,
                *_DOP_SAT_DEFAULTS,
                *_AGE_DEFAULTS,
            )
        import geopandas as gpd_local
        gdf_preview = gpd_local.read_file(str(shp_files[0])).head(200)
        detected_crs = gdf_preview.crs
        df = gdf_preview
        source_path = str(shp_files[0])
    else:
        return (
            f"Unsupported file type: {display_name}",
            [], [], [], [],
            None, None, None, None,
            _err_alert(f"Unsupported file type '{suffix}'."),
            None,
            *_UTM_DEFAULTS,
            *_DOP_SAT_DEFAULTS,
        )

    is_projected = (
        detected_crs is not None
        and detected_crs.is_projected
    )
    is_csv = suffix == ".csv"

    cols = [{"label": c, "value": c} for c in df.columns if c != "geometry"]

    def _auto(candidates):
        for c in candidates:
            for col in df.columns:
                if col.lower() == c.lower():
                    return col
        return None

    id_val = _auto(["TrakAID", "animalTrackerId", "LoclAID", "animalIdLocal", "animal_id", "ID", "id", "AnimalID"])
    _ts_match = _auto(["DT_MST", "timestamp", "datetime", "date_time", "DateTime"])
    ts_val = [_ts_match] if _ts_match else []

    if is_projected:
        lon_val = None
        lat_val = None
        utm_e_val = _auto(["UTME", "UTM_E", "Easting", "easting", "x", "X", "POINT_X"])
        utm_n_val = _auto(["UTMN", "UTM_N", "Northing", "northing", "y", "Y", "POINT_Y"])
    else:
        lon_val = _auto(["Long", "lon", "longitude", "x", "Longitude"])
        lat_val = _auto(["Lat", "lat", "latitude", "y", "Latitude"])
        utm_e_val = None
        utm_n_val = None

    dop_val = _auto(["DOP", "dop", "PDOP", "pdop", "HDOP", "hdop", "Precision"])
    sat_val = _auto(["NumSats", "numsats", "Satellites", "satellites", "n_sats", "NSats", "SatCount"])
    age_val = _auto(["captureAgeClass", "AgeClass", "age_class", "Age", "ageclass"])

    preview_table = _make_preview_table(df)

    crs_note = ""
    if detected_crs and detected_crs.to_epsg():
        epsg = f"EPSG:{detected_crs.to_epsg()}"
        crs_note = f" · {_crs_to_projection_name(epsg)} ({epsg})"
    elif detected_crs:
        crs_note = f" · {detected_crs.name}"

    fname_display = html.Span(
        f"Loaded: {display_name}{crs_note}",
        className="text-success small",
    )

    return (
        fname_display,
        cols, cols, cols, cols,
        id_val, ts_val, lon_val, lat_val,
        preview_table,
        source_path,
        # CSV CRS warning + UTM toggle
        is_csv,
        {"display": "block"} if is_csv else {"display": "none"},
        is_projected,
        cols, cols,
        utm_e_val, utm_n_val,
        # Coordinate group visibility
        {"display": "none"} if is_projected else {"display": "block"},
        {"display": "block"} if is_projected else {"display": "none"},
        # DOP / Satellites column mapping
        cols, cols,
        dop_val, sat_val,
        # Age class column mapping
        cols, age_val,
    )


@app.callback(
    Output("upload-filename", "children"),
    Output("col-animal-id", "options"),
    Output("col-timestamp", "options"),
    Output("col-lon", "options"),
    Output("col-lat", "options"),
    Output("col-animal-id", "value"),
    Output("col-timestamp", "value"),
    Output("col-lon", "value"),
    Output("col-lat", "value"),
    Output("tab1-preview", "children"),
    Output("store-upload-path", "data"),
    Output("csv-crs-warning", "is_open"),
    Output("utm-toggle-wrapper", "style"),
    Output("utm-input-toggle", "value"),
    Output("col-utm-easting", "options"),
    Output("col-utm-northing", "options"),
    Output("col-utm-easting", "value"),
    Output("col-utm-northing", "value"),
    Output("coord-lonlat-group", "style"),
    Output("coord-utm-group", "style"),
    Output("col-dop", "options"),
    Output("col-sats", "options"),
    Output("col-dop", "value"),
    Output("col-sats", "value"),
    Output("col-age-class", "options"),
    Output("col-age-class", "value"),
    Input("upload-data", "contents"),
    State("upload-data", "filename"),
    State("store-workdir", "data"),
    prevent_initial_call=True,
)
def handle_upload(contents, filename, workdir_path):
    """Save uploaded file to ModelInputs/ (if workdir set) or temp, then
    preview + auto-detect columns via the shared helper."""
    if not contents or not filename:
        raise PreventUpdate

    _content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)

    suffix = Path(filename).suffix.lower()

    # Browser drag-and-drop only transmits the single dropped file. A lone
    # .shp has no .shx/.dbf/.prj sidecars with it, so GDAL fails with
    # 'Unable to open .shx … Set SHAPE_RESTORE_SHX=YES …'. Short-circuit
    # here with a message the user can actually act on.
    _UTM_DEFAULTS = (
        False, {"display": "none"}, False,
        [], [], None, None,
        {"display": "block"}, {"display": "none"},
    )
    _DOP_SAT_DEFAULTS = ([], [], None, None)

    if suffix == ".shp":
        return (
            f"Cannot upload bare .shp: {filename}",
            [], [], [], [],
            None, None, None, None,
            _err_alert(
                "Shapefiles must be uploaded as a ZIP. Drag-and-drop in the browser "
                "only sends the .shp file — its .shx, .dbf, and .prj sidecars never "
                "leave your machine. Zip the full shapefile set in Windows Explorer "
                "(right-click the parts → Send to → Compressed (zipped) folder) and "
                "drag the .zip here instead, or copy all sidecars into "
                "<workdir>/ModelInputs/ and pick the file from the dropdown."
            ),
            None,
            *_UTM_DEFAULTS,
            *_DOP_SAT_DEFAULTS,
        )

    try:
        # Decide the on-disk destination. With a workdir set, files live in
        # ModelInputs/ (permanent); without one, fall back to a temp file.
        if workdir_path and Path(workdir_path).is_dir():
            inputs_dir = _workdir_inputs(Path(workdir_path))
            if suffix == ".zip":
                import zipfile as _zf
                tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                tmp_zip.write(decoded)
                tmp_zip.close()
                with _zf.ZipFile(tmp_zip.name) as z:
                    z.extractall(str(inputs_dir))
                Path(tmp_zip.name).unlink(missing_ok=True)
                shp_hits = list(inputs_dir.rglob("*.shp"))
                if shp_hits:
                    saved_path = shp_hits[0]
                    _create_companion_file(saved_path)
                    _log_action("UPLOAD_SHP_ZIP", filename=filename, extracted=saved_path.name)
                else:
                    saved_path = inputs_dir / Path(filename).name
                    saved_path.write_bytes(decoded)
            else:
                dest = inputs_dir / Path(filename).name
                dest.write_bytes(decoded)
                _log_action("UPLOAD_CSV", filename=Path(filename).name, bytes=len(decoded))
                saved_path = dest
                _create_companion_file(dest)
        else:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(decoded)
            tmp.close()
            saved_path = Path(tmp.name)

        return _preview_input_file(saved_path, display_name=filename)

    except Exception as exc:
        return (
            f"Error reading {filename}",
            [], [], [], [],
            None, None, None, None,
            _err_alert(f"Upload error: {exc}"),
            None,
            *_UTM_DEFAULTS,
            *_DOP_SAT_DEFAULTS,
        )


# Populate the "Select or Upload Data" dropdown from whatever's in
# <workdir>/ModelInputs/ right now. Re-runs whenever the workdir changes
# or a fresh upload lands (store-upload-path bumps), so newly added files
# appear immediately.
@app.callback(
    Output("modelinputs-select", "options"),
    Output("modelinputs-select", "value"),
    Output("modelinputs-select", "placeholder"),
    Input("store-workdir", "data"),
    Input("store-upload-path", "data"),
    State("modelinputs-select", "value"),
    prevent_initial_call=False,
)
def populate_modelinputs_dropdown(workdir_path, current_upload_path, current_selection):
    """List the .csv / .shp files currently in <workdir>/ModelInputs/.

    Only auto-selects a value when a fresh upload just landed in
    ModelInputs/ (the upload widget should immediately become the active
    selection). On app boot or workdir change, the dropdown lists what's
    available but leaves the value alone — the user explicitly picks the
    file they want to process, so we don't silently re-load data from a
    prior session.
    """
    if not workdir_path:
        return [], None, "(set a working directory to populate)"
    workdir = Path(workdir_path)
    inputs_dir = workdir / "ModelInputs"
    if not inputs_dir.is_dir():
        return [], None, "(ModelInputs/ folder missing)"

    files = sorted(
        [p for p in inputs_dir.iterdir()
         if p.is_file() and p.suffix.lower() in {".csv", ".shp"}],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not files:
        return [], None, "(no .csv or .shp files in ModelInputs/ yet)"

    options = [{"label": p.name, "value": str(p)} for p in files]

    # Auto-select ONLY when the trigger is a fresh upload landing in
    # ModelInputs/. Workdir restore / app boot leaves the value alone.
    selected = current_selection
    if ctx.triggered_id == "store-upload-path":
        try:
            upload_p = Path(current_upload_path) if current_upload_path else None
            if upload_p is not None and upload_p.exists() and upload_p.parent == inputs_dir:
                selected = str(upload_p)
        except Exception:
            pass

    return options, selected, "Select a file..."


# When the user picks a file from the dropdown, run the same preview /
# column-auto-detect path that handle_upload uses. This replaces the prior
# "auto-load most-recent file" callback.
@app.callback(
    Output("upload-filename", "children", allow_duplicate=True),
    Output("col-animal-id", "options", allow_duplicate=True),
    Output("col-timestamp", "options", allow_duplicate=True),
    Output("col-lon", "options", allow_duplicate=True),
    Output("col-lat", "options", allow_duplicate=True),
    Output("col-animal-id", "value", allow_duplicate=True),
    Output("col-timestamp", "value", allow_duplicate=True),
    Output("col-lon", "value", allow_duplicate=True),
    Output("col-lat", "value", allow_duplicate=True),
    Output("tab1-preview", "children", allow_duplicate=True),
    Output("store-upload-path", "data", allow_duplicate=True),
    Output("csv-crs-warning", "is_open", allow_duplicate=True),
    Output("utm-toggle-wrapper", "style", allow_duplicate=True),
    Output("utm-input-toggle", "value", allow_duplicate=True),
    Output("col-utm-easting", "options", allow_duplicate=True),
    Output("col-utm-northing", "options", allow_duplicate=True),
    Output("col-utm-easting", "value", allow_duplicate=True),
    Output("col-utm-northing", "value", allow_duplicate=True),
    Output("coord-lonlat-group", "style", allow_duplicate=True),
    Output("coord-utm-group", "style", allow_duplicate=True),
    Output("col-dop", "options", allow_duplicate=True),
    Output("col-sats", "options", allow_duplicate=True),
    Output("col-dop", "value", allow_duplicate=True),
    Output("col-sats", "value", allow_duplicate=True),
    Output("col-age-class", "options", allow_duplicate=True),
    Output("col-age-class", "value", allow_duplicate=True),
    Input("modelinputs-select", "value"),
    prevent_initial_call=True,
)
def select_modelinputs_file(selected_path):
    # Bail out cleanly if there's nothing valid to preview — this callback
    # gets triggered by populate_modelinputs_dropdown writing a default value
    # on page load, which can land on a stale path from a previous session.
    if not selected_path:
        raise PreventUpdate
    try:
        p = Path(selected_path)
    except Exception:
        raise PreventUpdate
    _UTM_DEFAULTS = (
        False, {"display": "none"}, False,
        [], [], None, None,
        {"display": "block"}, {"display": "none"},
    )
    _DOP_SAT_DEFAULTS = ([], [], None, None)

    if not p.is_file():
        return (
            html.Span(f"File no longer exists: {p.name}", className="text-warning small"),
            [], [], [], [], None, None, None, None,
            _err_alert(f"Selected file no longer exists on disk: {selected_path}"),
            None,
            *_UTM_DEFAULTS,
            *_DOP_SAT_DEFAULTS,
        )
    try:
        _log_action("SELECT_INPUT", file=p.name)
        _create_companion_file(p)
        return _preview_input_file(p, display_name=p.name)
    except Exception as exc:
        return (
            html.Span(f"Error reading {p.name}", className="text-danger small"),
            [], [], [], [], None, None, None, None,
            _err_alert(f"Could not read {p.name}: {exc}"),
            None,
            *_UTM_DEFAULTS,
            *_DOP_SAT_DEFAULTS,
        )


# ---------------------------------------------------------------------------
# CSV UTM checkbox toggle — swap lon/lat ↔ easting/northing when user clicks
# ---------------------------------------------------------------------------

@app.callback(
    Output("coord-lonlat-group", "style", allow_duplicate=True),
    Output("coord-utm-group", "style", allow_duplicate=True),
    Input("utm-input-toggle", "value"),
    prevent_initial_call=True,
)
def toggle_coord_inputs(use_utm):
    if use_utm:
        return {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}


# ---------------------------------------------------------------------------
# WLD upload: save to temp file, read header metadata for status display
# ---------------------------------------------------------------------------

@app.callback(
    Output("wld-upload-status", "children"),
    Output("store-wld-upload-path", "data"),
    Input("upload-wld", "contents"),
    State("upload-wld", "filename"),
    State("store-workdir", "data"),
    prevent_initial_call=True,
)
def handle_wld_upload(contents, filename, workdir_path):
    # WLD ingest is intentionally a two-step write: (1) always write to a
    # temp file so the downstream reader has a stable absolute path even
    # without a workdir, then (2) mirror to <workdir>/ModelInputs/ if a
    # workdir is set so the file is preserved across sessions. The temp
    # file is the source of truth for this session; the ModelInputs copy
    # is the archival copy.
    if not contents or not filename:
        raise PreventUpdate

    _, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)

    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wld")
        tmp.write(decoded)
        tmp.close()
        # Mirror to ModelInputs/ if workdir set
        wld_source = tmp.name
        if workdir_path and Path(workdir_path).is_dir():
            try:
                inputs_dir = _workdir_inputs(Path(workdir_path))
                dest = inputs_dir / Path(filename).name
                dest.write_bytes(decoded)
                _log_action("UPLOAD_WLD", filename=Path(filename).name, bytes=len(decoded))
                wld_source = str(dest)
            except Exception:
                pass
        meta = read_wld_metadata(wld_source)
        status = html.Span(
            f"Loaded: {filename} — {meta['population']} "
            f"({meta['n_collars']} collars, {meta['n_fixes']:,} fixes)",
            className="text-success small",
        )
        return status, wld_source
    except Exception as exc:
        return html.Span(f"WLD error: {exc}", className="text-danger small"), None


# ---------------------------------------------------------------------------
# Show/hide the whole WLD section when the user toggles the header checkbox
# ---------------------------------------------------------------------------

@app.callback(
    Output("wld-section-collapse", "is_open"),
    Input("wld-section-toggle", "value"),
)
def toggle_wld_section(checked):
    return bool(checked)


# ---------------------------------------------------------------------------
# Toggle the "all 36 variables" advanced picker
# ---------------------------------------------------------------------------

@app.callback(
    Output("wld-advanced-collapse", "is_open"),
    Output("btn-toggle-wld-advanced", "children"),
    Input("btn-toggle-wld-advanced", "n_clicks"),
    State("wld-advanced-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_wld_advanced(n_clicks, is_open):
    new_open = not is_open
    label = "Hide advanced variables ▴" if new_open else "Show all 36 variables ▾"
    return new_open, label


# Show the stopover-density input only when "Calculate stopovers" is ticked.
@app.callback(
    Output("pop-stopover-collapse", "is_open"),
    Input("pop-stopover-toggle", "value"),
)
def toggle_stopover_pct(checked):
    return bool(checked)


@app.callback(
    Output("age-class-include", "options"),
    Output("age-class-include", "value"),
    Output("age-class-checklist-wrapper", "style"),
    Output("age-class-hint", "children"),
    Input("col-age-class", "value"),
    State("store-upload-path", "data"),
    prevent_initial_call=True,
)
def populate_age_class_checklist(age_col, tmp_path):
    """Read unique age-class values from the uploaded data and populate the
    inclusion checklist. Pre-checks all classes except calf/fawn."""
    hidden = {"display": "none"}
    if not age_col or not tmp_path:
        return [], [], hidden, ""
    try:
        p = Path(tmp_path)
        if p.suffix.lower() == ".csv":
            df = pd.read_csv(str(p), low_memory=False, usecols=[age_col])
        else:
            import geopandas as _gpd
            df = _gpd.read_file(str(p))[[age_col]]
        vals = sorted(df[age_col].dropna().astype(str).str.strip().unique(), key=str.lower)
        if not vals:
            return [], [], hidden, ""
        options = [{"label": f" {v}", "value": v} for v in vals]
        _EXCLUDE_DEFAULT = {"calf", "fawn"}
        included = [v for v in vals if v.lower() not in _EXCLUDE_DEFAULT]
        excluded = [v for v in vals if v.lower() in _EXCLUDE_DEFAULT]
        hint = f"{len(excluded)} class(es) unchecked by default" if excluded else ""
        return options, included, {"display": "block"}, hint
    except Exception:
        return [], [], hidden, ""


@app.callback(
    Output("pop-minimumx-collapse", "is_open"),
    Output("pop-minimumx-label", "children"),
    Output("pop-minimumx-value", "max"),
    Input("pop-minimumx-toggle", "value"),
)
def toggle_minimumx(checked):
    n_animals = 999
    seq_animal = _MODEL_CACHE.get("seq_animal", {})
    if seq_animal:
        n_animals = len(set(seq_animal.values()))
    label = f"Minimum number of animals (1–{n_animals})"
    return bool(checked), label, n_animals


@app.callback(
    Output("tab1-status", "children"),
    Output("tab1-summary", "children"),
    Output("store-processed-data", "data"),
    Output("store-config", "data"),
    Output("store-road-crossings", "data", allow_duplicate=True),
    Output("store-wld-env-labels", "data"),
    Output("process-loading-indicator", "children"),
    Input("btn-process", "n_clicks"),
    State("store-upload-path", "data"),
    State("col-animal-id", "value"),
    State("col-timestamp", "value"),
    State("col-lon", "value"),
    State("col-lat", "value"),
    State("param-max-speed", "value"),
    State("param-mort-dist", "value"),
    State("param-mort-time", "value"),
    State("param-bio-month", "value"),
    State("param-bio-day", "value"),
    State("param-dop-cutoff", "value"),
    State("param-sat-cutoff", "value"),
    State("raster-var-checklist", "value"),
    State("project-name", "value"),
    State("store-wld-upload-path", "data"),
    State("wld-var-checklist", "value"),
    State("wld-var-advanced-checklist", "value"),
    State("store-processed-data", "data"),
    State("store-workdir", "data"),
    State("detect-road-crossings", "value"),
    State("param-herd-id-override", "value"),
    State("utm-input-toggle", "value"),
    State("col-utm-easting", "value"),
    State("col-utm-northing", "value"),
    State("col-dop", "value"),
    State("col-sats", "value"),
    State("age-class-include", "value"),
    State("col-age-class", "value"),
    State("auto-flagging-toggle", "value"),
    prevent_initial_call=True,
)
def process_uploaded_data(
    n_clicks, tmp_path, animal_col, ts_col, lon_col, lat_col,
    max_speed, mort_dist, mort_time, bio_month, bio_day,
    dop_cutoff, sat_cutoff, raster_vars, project_name,
    wld_path, wld_vars_default, wld_vars_advanced,
    existing_processed_json, workdir_path, detect_roads,
    herd_id_override, use_utm, utm_easting_col, utm_northing_col,
    dop_col, sat_col, age_class_include, age_class_col,
    auto_flagging_enabled,
):
    """Run the full data processing pipeline.

    Stages, in order:
      1. Re-rendering shortcut when no upload but a project is already loaded.
      2. Cache reset + config dict assembly from UI parameters.
      3. process_data() — the heavy core: clean / burst / NSD / flag / mortality.
      4. Herd ID override (manual stamp on top of auto-derivation).
      5. Raster sampling (DEM / SNODAS) at each GPS fix — optional.
      6. WLD column merge — optional.
      7. Summary card + colour-coded processing log build.
      8. Persistence: parquet + project_meta + workdir mirror + FlagsRemoved
         shapefile.
      9. Road / highway crossing detection — optional, off by default
         because it dominates runtime on big datasets.
     10. Datetime → ISO string conversion before returning to the dcc.Store.
    """
    global _ACTIVE_PROJECT
    proj = (project_name or "").strip().replace(" ", "_") or "default"
    _ACTIVE_PROJECT = proj

    # ---- Stage 1: re-render shortcut ----
    # If no new upload but a project is already loaded in the store, just
    # rebuild the summary card from the existing data instead of erroring.
    # This is what makes the "Load Project → Process Data" flow work — the
    # user loaded a previously-processed project, sees an empty summary, and
    # clicks Process Data expecting it to "do something".
    if not tmp_path:
        if existing_processed_json:
            try:
                existing_df = _json_to_df(existing_processed_json, "processed")
                summary = _build_loaded_project_summary(
                    existing_df,
                    project_name or _ACTIVE_PROJECT,
                    _load_project_meta(project_name or _ACTIVE_PROJECT),
                )
                msg = _ok_alert(
                    f"Project '{(project_name or _ACTIVE_PROJECT).replace('_', ' ')}' "
                    f"is already loaded ({len(existing_df):,} points). Re-upload a file to reprocess."
                )
                return msg, summary, dash.no_update, dash.no_update, dash.no_update, dash.no_update, ""
            except Exception as exc:
                return _err_alert(f"Loaded project found but could not be summarised: {exc}"), "", dash.no_update, dash.no_update, dash.no_update, dash.no_update, ""
        return _err_alert("Please upload a file first."), "", None, None, dash.no_update, dash.no_update, ""

    # ---- Stage 2: cache reset + config assembly ----
    # Wipe both caches so the new dataset can't see stale entries from a
    # previous project.
    _DF_CACHE.clear()
    _MAP_CACHE.clear()

    # Filter thresholds honour the user EXACTLY: a blank box → None → that
    # filter/flag is disabled; an explicit value (including 0) is respected.
    # NOTE: `float(x or default)` is deliberately NOT used here — it would both
    # re-impose a default on blank AND silently turn a user-entered 0 into the
    # default (0 is falsy). _num_or_none avoids both.
    def _num_or_none(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    if use_utm:
        _lon_col = utm_easting_col or "UTME"
        _lat_col = utm_northing_col or "UTMN"
        _input_crs = "EPSG:32613"
    else:
        _lon_col = lon_col or "Long"
        _lat_col = lat_col or "Lat"
        _input_crs = "EPSG:4326"

    _flagging = bool(auto_flagging_enabled)
    config = {
        "animal_id_col": animal_col or "LoclAID",
        "timestamp_col": ts_col if ts_col else "DT_MST",
        "lon_col": _lon_col,
        "lat_col": _lat_col,
        "input_crs": _input_crs,
        "max_speed_kmh": _num_or_none(max_speed) if _flagging else None,
        "mort_distance_m": _num_or_none(mort_dist) if _flagging else None,
        "mort_time_hours": _num_or_none(mort_time) if _flagging else None,
        # Bio-year start is structural (drives year grouping, not a filter), so
        # it keeps a sensible default when blank rather than being disabled.
        "bio_year_start_month": int(bio_month) if bio_month not in (None, "") else 2,
        "bio_year_start_day": int(bio_day) if bio_day not in (None, "") else 1,
        "dop_cutoff": _num_or_none(dop_cutoff) if _flagging else None,
        "sat_cutoff": _num_or_none(sat_cutoff) if _flagging else None,
        "dop_col": dop_col or "DOP",
        "sat_col": sat_col or "NumSats",
    }

    # ---- Stage 3: heavy core ----
    # process_data does the full clean → burst → movement params → NSD →
    # problem-flag → mortality-flag pipeline. `final_config` is the input
    # config dict with any derived fields filled in (herd_id, project_name,
    # detected fix rate). `processing_log` is a list of human-readable lines
    # that gets colour-coded below.
    try:
        gdf, final_config, processing_log = process_data(tmp_path, config=config)
    except Exception as exc:
        return _err_alert(f"Processing failed: {exc}\n{traceback.format_exc()}"), "", None, None, dash.no_update, dash.no_update, ""

    # ---- Stage 3b: filter by age class ----
    _age_col = age_class_col or "captureAgeClass"
    _included = set(age_class_include or [])
    if _included and _age_col in gdf.columns:
        actual_vals = set(gdf[_age_col].astype(str).str.strip().unique())
        excluded_vals = actual_vals - _included
        if excluded_vals:
            exclude_mask = gdf[_age_col].astype(str).str.strip().isin(excluded_vals)
            excluded_df = gdf[exclude_mask].copy()
            n_excluded = len(excluded_df)
            if n_excluded:
                gdf = gdf[~exclude_mask].copy()
                _aid = "animal_id" if "animal_id" in excluded_df.columns else config["animal_id_col"]
                processing_log.append(
                    f"Age-class filter: {n_excluded:,} fixes removed ({excluded_df[_aid].nunique()} animals) "
                    f"— excluded classes: {', '.join(sorted(excluded_vals))}"
                )
                excluded_out = excluded_df.drop(columns=["geometry"], errors="ignore").copy()
                excluded_out["removal_reason"] = "Age class excluded: " + excluded_df[_age_col].astype(str).str.strip()
                if workdir_path:
                    try:
                        removed_dir = _workdir_version(Path(workdir_path)) / "RemovedPoints"
                        removed_dir.mkdir(parents=True, exist_ok=True)
                        excluded_out.to_csv(
                            removed_dir / "AgeClassRemoved.csv", index=False,
                        )
                    except Exception:
                        pass
            else:
                processing_log.append("Age-class filter: no fixes matched excluded classes")
        else:
            processing_log.append("Age-class filter: all classes included, none removed")
    elif _age_col not in (gdf.columns if hasattr(gdf, 'columns') else []):
        processing_log.append(f"Age-class filter: column '{_age_col}' not found, skipped")

    # Manual Herd ID override from the Tab 1 input field. Stripped + sanitised
    # to the same character set the auto-derivation uses (alnum + _ + -).
    override = (herd_id_override or "").strip()
    if override:
        import re as _re
        sanitised = _re.sub(r"\s+", "_", override)
        sanitised = _re.sub(r"[^\w\-]", "", sanitised)
        if sanitised:
            previous = final_config.get("herd_id", "")
            final_config["herd_id"] = sanitised
            final_config["herd_id_source_col"] = "user override"
            processing_log.append(
                f"Herd ID overridden by user: '{previous}' -> '{sanitised}'"
            )

    # ---- Stage 5: optional raster sampling (DEM, SNODAS, etc.) ----
    # sample_rasters works on a plain DataFrame (it doesn't need the geometry
    # column), so we drop geometry, sample, and copy the resulting columns
    # back into the GeoDataFrame by .values to preserve the index. Each
    # variable is logged with its PASS/FAIL line so the user can see in the
    # processing log which raster pulls succeeded.
    if raster_vars:
        try:
            processing_log.append("")
            processing_log.append(f"Sampling {len(raster_vars)} raster variable(s) at {len(gdf):,} GPS fixes...")
            gdf_flat = pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore"))
            gdf_flat = sample_rasters(gdf_flat, raster_vars, lat_col="lat", lon_col="lon", ts_col="timestamp")
            for vc in raster_vars:
                if vc in gdf_flat.columns:
                    gdf[vc] = gdf_flat[vc].values
            for vc in raster_vars:
                if vc in gdf.columns:
                    n_valid = int(gdf[vc].notna().sum() if gdf[vc].dtype == float else (gdf[vc] != 0).sum())
                    processing_log.append(f"PASS: {AVAILABLE_VARIABLES.get(vc, vc)} — {n_valid:,} values sampled")
            # Surface corrupt/truncated DEM tiles: a bad tile only NaNs its own
            # points now (it no longer aborts the whole elevation pull), but the
            # user should know some fixes couldn't be sampled and which tile to
            # re-download from USGS 3DEP.
            bad_tiles = gdf_flat.attrs.get("dem_tile_errors") if hasattr(gdf_flat, "attrs") else None
            if bad_tiles:
                n_missing = int(gdf["elevation_m"].isna().sum()) if "elevation_m" in gdf.columns else 0
                processing_log.append(
                    f"WARNING: {n_missing:,} fix(es) could not be sampled from corrupt/truncated "
                    f"DEM tile(s): {', '.join(bad_tiles)}. Re-download from USGS 3DEP to fill these in."
                )
        except Exception as raster_exc:
            processing_log.append(f"WARNING: Raster sampling failed: {raster_exc}")

    # ---- Stage 6: optional WLD merge ----
    # WLD files are MigrationAnalyzer's per-animal environmental rollups.
    # selected_wld_idx is the union of the two checklists (default + advanced)
    # — so a variable that's ticked in EITHER list gets merged. The merge is
    # left-joined onto the GPS DataFrame on (animal_id, timestamp), and the
    # resulting human labels (e.g. "snow_depth_24h" → "Snow Depth (24h)") are
    # stored in wld_env_labels so Tab 2 popups can show readable names.
    wld_env_labels: dict[str, str] = {}
    if wld_path:
        selected_wld_idx = sorted(set((wld_vars_default or []) + (wld_vars_advanced or [])))
        try:
            processing_log.append("")
            processing_log.append(
                f"Merging {len(selected_wld_idx)} .wld variable(s) onto GPS fixes..."
            )
            wld_df = read_wld_fast(wld_path, selected_columns=selected_wld_idx)
            gdf_flat = pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore"))
            merged = merge_wld_to_gps(gdf_flat, wld_df, gps_id_col="animal_id", gps_ts_col="timestamp")
            # Pull in any new columns from the merge
            new_cols = [c for c in merged.columns if c not in gdf.columns]
            for c in new_cols:
                gdf[c] = merged[c].values
            # Build the human-label dict for downstream popups
            for idx in selected_wld_idx:
                if idx in WLD_COLUMNS:
                    col_name, human_label, _grp = WLD_COLUMNS[idx]
                    if col_name in gdf.columns:
                        wld_env_labels[col_name] = human_label
            # Per-variable status lines
            for col_name, label in wld_env_labels.items():
                n_valid = int(gdf[col_name].notna().sum())
                processing_log.append(f"PASS: {label} ({col_name}) — {n_valid:,} values merged")
            if not wld_env_labels:
                processing_log.append("WARNING: WLD merge produced no new columns (animal-ID match failed?)")
        except Exception as wld_exc:
            processing_log.append(f"WARNING: WLD merge failed: {wld_exc}")

    # Summary stats
    n_animals = gdf["animal_id"].nunique() if "animal_id" in gdf.columns else "?"
    n_points = len(gdf)
    date_min = gdf["timestamp"].min() if "timestamp" in gdf.columns else "?"
    date_max = gdf["timestamp"].max() if "timestamp" in gdf.columns else "?"
    n_flagged = int(gdf["problem"].sum()) if "problem" in gdf.columns else 0
    n_mort = int(gdf["mortality_flag"].sum()) if "mortality_flag" in gdf.columns else 0

    # ---- Stage 7: colour-coded log ----
    # Colour palette is colourblind-safe (Wong's CB-safe set):
    #   FAIL/WARNING → light vermillion, PASS → light teal,
    #   INFO → light sky, "===" separators → mid-gray.
    # The classification is done by line prefix because process_data and
    # the optional raster/wld stages all build the log as plain strings;
    # there's no structured event log to recolour.
    log_lines = []
    for line in processing_log:
        if line.startswith("FAIL:") or line.startswith("WARNING:"):
            log_lines.append(html.Div(line, style={"color": "#FCA5A5"}))  # CB-safe light vermillion
        elif line.startswith("PASS:"):
            log_lines.append(html.Div(line, style={"color": "#6EE7B7"}))  # CB-safe light teal/green
        elif line.startswith("INFO:"):
            log_lines.append(html.Div(line, style={"color": "#8FCFFF"}))  # CB-safe light sky blue
        elif line.startswith("="):
            log_lines.append(html.Div(line, style={"color": "#B0B0B0"}))  # readable mid-gray
        elif line == "":
            log_lines.append(html.Br())
        else:
            log_lines.append(html.Div(line))

    summary = html.Div([
        dbc.Card(
            dbc.CardBody(
                [
                    html.H6("Processing Summary", className="card-title text-success"),
                    dbc.Row(
                        [
                            dbc.Col(html.Div([html.Strong("Animals: "), str(n_animals)]), width=3),
                            dbc.Col(html.Div([html.Strong("Points: "), f"{n_points:,}"]), width=3),
                            dbc.Col(html.Div([html.Strong("Flagged: "), f"{n_flagged:,}"]), width=3),
                            dbc.Col(html.Div([html.Strong("Mortality Flags: "), f"{n_mort:,}"]), width=3),
                        ],
                        className="mb-2",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(html.Div([html.Strong("Date Range: "), f"{date_min} → {date_max}"]), width=8),
                            dbc.Col(html.Div([
                                html.Strong("Herd ID: "),
                                html.Code(str(final_config.get("herd_id", "Herd"))),
                                html.Small(
                                    f" (from {final_config.get('herd_id_source_col', '?')})"
                                    if final_config.get("herd_id_source_col") else "",
                                    className="text-muted ms-1",
                                ),
                            ]), width=4),
                        ]
                    ),
                    dbc.Row(
                        [
                            dbc.Col(html.Div([
                                html.Strong("Projection: "),
                                _crs_to_projection_name(final_config.get("input_crs", "EPSG:4326")),
                                html.Small(
                                    f" ({final_config.get('input_crs', 'EPSG:4326')})"
                                    + (" → reprojected to WGS84"
                                       if final_config.get("input_crs", "EPSG:4326") != "EPSG:4326"
                                       else ""),
                                    className="text-muted ms-1",
                                ),
                            ]), width=8),
                        ],
                        className="mt-1",
                    ),
                ]
            ),
            className="border-success mb-3",
        ),
        dbc.Card(
            [
                dbc.CardHeader("Processing Log", style={"fontSize": "0.85rem"}),
                dbc.CardBody(
                    html.Pre(
                        log_lines,
                        style={
                            "fontSize": "0.8rem",
                            "fontFamily": "Consolas, monospace",
                            "maxHeight": "400px",
                            "overflowY": "auto",
                            "backgroundColor": "#1a1a1a",
                            "padding": "12px",
                            "borderRadius": "4px",
                            "whiteSpace": "pre-wrap",
                            "margin": 0,
                        },
                    ),
                ),
            ],
        ),
    ])

    # ---- Stage 8: persistence ----
    # Convert to a plain DataFrame for downstream JSON-serialisable use.
    # geometry can't survive JSON; lon/lat columns already carry the coords.
    df_out = pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore"))

    # Don't eagerly build the per-animal map cache here — for large herds
    # that loop was the dominant remaining cost of Tab 1 and was pushing
    # the response past the browser's HTTP timeout. Clear what was there
    # so Tab 2 builds entries lazily from the freshly-saved data instead.
    _MAP_CACHE.clear()

    # Save to disk for persistence across restarts (legacy session_data path).
    _save_processed_to_disk(df_out.copy(), proj)

    # Record the input source path (and a few extras) so a future "Load Project"
    # can show the user exactly which file produced this project's data.
    import datetime as _dt
    _save_project_meta(
        {
            "input_source_path": str(tmp_path) if tmp_path else "",
            "wld_source_path": str(wld_path) if wld_path else "",
            "input_crs": final_config.get("input_crs", "EPSG:4326"),
            "processed_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "workdir": str(workdir_path) if workdir_path else "",
            "config": final_config,
        },
        proj,
    )

    # Detect road/highway crossings for all animals — opt-in via the
    # "Detect road crossings" checkbox in Tab 1. Runs in a background thread
    # so the UI returns immediately; results are written to disk and picked
    # up by Tab 2 lazily.
    road_results: dict = {}
    if detect_roads:
        import threading as _th_roads

        def _road_worker():
            try:
                res = detect_crossings_batch(df_out)
                rc_path = _project_dir(proj) / "road_crossings.json"
                rc_path.write_text(json.dumps(res, default=str))
                if workdir_path and Path(workdir_path).is_dir():
                    (_workdir_outputs(Path(workdir_path)) / "road_crossings.json").write_text(
                        json.dumps(res, default=str)
                    )
            except Exception:
                pass

        _th_roads.Thread(target=_road_worker, daemon=True).start()
        processing_log.append("Road-crossing detection running in background...")
    else:
        processing_log.append("Road-crossing detection skipped (checkbox off).")

    # If a working directory is set, also mirror outputs under ModelOutputs/
    # and append the processing log to session_log.txt.
    if workdir_path and Path(workdir_path).is_dir():
        try:
            outputs_dir = _workdir_outputs(Path(workdir_path))
            df_out.to_parquet(str(outputs_dir / "processed_data.parquet"), index=False)
            (outputs_dir / "road_crossings.json").write_text(json.dumps(road_results, default=str))
            import datetime as _dt_proc
            _proc_ts = _dt_proc.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _header = [f"DATA PROCESSED   [{_proc_ts}]", "=" * 60, ""]
            (outputs_dir / "processing_log.txt").write_text(
                "\n".join(_header + processing_log), encoding="utf-8"
            )
            _log_action(
                "PROCESS_DATA",
                animals=int(n_animals) if isinstance(n_animals, int) or (hasattr(n_animals, '__int__')) else n_animals,
                points=n_points,
                flagged=n_flagged,
                mortality=n_mort,
                wld_vars=len(wld_env_labels),
            )
            # Write the cleaned GeoPackage in background — it's the slowest
            # disk operation and not needed until export.
            import threading as _th_gpkg
            _gpkg_df = df_out.copy()
            _gpkg_dir = outputs_dir

            def _gpkg_worker():
                try:
                    herd_id = str(final_config.get("herd_id", "Herd"))
                    project_name_token = str(final_config.get("project_name", "Project"))
                    fr_path = write_flags_removed_shapefile(
                        processed_df=_gpkg_df,
                        out_dir=_gpkg_dir,
                        herd_id=herd_id,
                        project_name=project_name_token,
                    )
                    if fr_path is not None:
                        _log_action(
                            "FLAGS_REMOVED_EXPORT",
                            path=str(fr_path.relative_to(_gpkg_dir)),
                            kept=int(((_gpkg_df.get("problem", 0) == 0) & (_gpkg_df.get("mortality_flag", 0) == 0)).sum()),
                        )
                except Exception:
                    pass

            _th_gpkg.Thread(target=_gpkg_worker, daemon=True).start()
        except Exception as wd_exc:
            processing_log.append(f"WARNING: Failed to write to ModelOutputs/: {wd_exc}")

    # Convert datetime columns to ISO strings
    for col in df_out.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        df_out[col] = df_out[col].astype(str)

    return (
        _ok_alert(
            f"Processing complete. {n_points:,} points across {n_animals} animals. "
            "Next step: import a previous migtime table, or move to Tab 2 to set migration sequences."
        ),
        summary,
        _df_to_json(df_out, "processed"),
        json.dumps(final_config),
        road_results,
        wld_env_labels,
        "",
    )


# ===========================================================================
# Callbacks — Tab 2: Migration Sequencing
# ===========================================================================

@app.callback(
    Output("seq-animal-dropdown", "options"),
    Output("seq-animal-dropdown", "value"),
    Input("store-processed-data", "data"),
    Input("seq-bio-year-month", "value"),
    Input("seq-bio-year-day", "value"),
    State("seq-animal-dropdown", "value"),
    prevent_initial_call=True,
)
def populate_animal_dropdown(processed_json, bio_month, bio_day, current_value):
    if not processed_json:
        raise PreventUpdate
    df = _json_to_df(processed_json, "processed")
    if "animal_id" not in df.columns or "timestamp" not in df.columns:
        raise PreventUpdate
    bio_month = int(bio_month or 2)
    bio_day = int(bio_day or 1)
    # Re-derive id_bio_year from the UI's current bio-year start so the
    # dropdown options always match what the rest of Tab 2 will compute.
    ts_ = pd.to_datetime(df["timestamp"], errors="coerce")
    month_ = ts_.dt.month.to_numpy(dtype=int)
    day_ = ts_.dt.day.to_numpy(dtype=int)
    year_ = ts_.dt.year.to_numpy(dtype=int)
    before_start = (month_ < bio_month) | ((month_ == bio_month) & (day_ < bio_day))
    bio_year_arr = np.where(before_start, year_ - 1, year_)
    ids = df["animal_id"].astype(str).to_numpy() + "_" + bio_year_arr.astype(str)
    uniques = sorted(set(ids))
    options = [{"label": v, "value": v} for v in uniques]
    # Preserve selection if still valid, otherwise default to first option.
    value = current_value if current_value in uniques else (options[0]["value"] if options else None)
    return options, value


@app.callback(
    Output("seq-name-inputs", "children"),
    Input("seq-num-sequences", "value"),
    Input("store-seq-names", "data"),
    prevent_initial_call=False,
)
def render_seq_name_inputs(n, seq_names):
    # Seed each box from store-seq-names when available so labels restored by
    # Load Previous Table (or carried across a num-sequences change) reappear in
    # the inputs; otherwise fall back to the mig{n} default. store-seq-names is
    # also an Input so a load repopulates the boxes — sync_seq_names then mirrors
    # them straight back unchanged, so this converges in one extra render rather
    # than looping. debounce=True means the round-trip only happens on blur.
    n = int(n or 4)
    defaults = ["mig1", "mig2", "mig3", "mig4", "mig5", "mig6", "mig7", "mig8"]
    seq_names = seq_names or []

    def _val(i):
        if i < len(seq_names) and str(seq_names[i]).strip():
            return str(seq_names[i]).strip()
        return defaults[i] if i < len(defaults) else f"Migration{i+1}"

    rows = []
    for i in range(n):
        rows.append(
            dbc.InputGroup(
                [
                    dbc.InputGroupText(f"Seq {i+1}", style={"fontSize": "0.8rem", "width": "55px"}),
                    dbc.Input(
                        id={"type": "seq-name", "index": i},
                        value=_val(i),
                        # debounce so the rename commits on blur/Enter rather than
                        # on every keystroke — otherwise sync_seq_names would fire
                        # (and re-label the chart/cards) mid-word.
                        debounce=True,
                        style={"fontSize": "0.85rem"},
                    ),
                ],
                size="sm",
                className="mb-1",
            )
        )
    return rows


@app.callback(
    Output("store-seq-names", "data"),
    Input({"type": "seq-name", "index": dash.ALL}, "value"),
    prevent_initial_call=False,
)
def sync_seq_names(values):
    """Mirror the Sequence Names inputs into store-seq-names so every consumer
    (NSD bands, slider-card headers, migtime export, modeling) reads one
    authoritative, ordered list of labels. dash.ALL preserves the slot order
    (index 0 → Seq 1). Blank entries stay blank; consumers fall back to
    "mig{n}" for any empty slot."""
    return [str(v).strip() if v else "" for v in (values or [])]


def _seq_working_df(processed_json, bio_month, bio_day):
    """Load the processed DataFrame from cache and re-derive bio_year /
    id_bio_year from the UI's current bio-year start. Shared by the Tab-2
    migtime writer and renderer so both key off identical animal-year windows.
    Returns (df, nsd_col)."""
    df = _json_to_df(processed_json, "processed")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if "timestamp" in df.columns and "animal_id" in df.columns:
        ts_ = df["timestamp"]
        month_ = ts_.dt.month.to_numpy(dtype=int)
        day_ = ts_.dt.day.to_numpy(dtype=int)
        year_ = ts_.dt.year.to_numpy(dtype=int)
        before_start = (month_ < bio_month) | ((month_ == bio_month) & (day_ < bio_day))
        bio_year_arr = np.where(before_start, year_ - 1, year_)
        df["bio_year"] = bio_year_arr
        df["id_bio_year"] = df["animal_id"].astype(str) + "_" + bio_year_arr.astype(str)
    nsd_col = "nsd_id_bio_year" if "nsd_id_bio_year" in df.columns else None
    if nsd_col is None:
        nsd_cols = [c for c in df.columns if c.startswith("nsd_")]
        nsd_col = nsd_cols[0] if nsd_cols else None
    return df, nsd_col


# Shared sequence-band palette — one entry per slot (mig1..mig8). The NSD chart
# bands, the slider-card headers, and the map points (_build_point_geojson) all
# index into the SAME list so a sequence's colour is identical everywhere.
SEQ_COLORS = ["#FF6B6B", "#2ECC71", "#FFD93D", "#4D96FF", "#4ECDC4", "#FFA94D", "#A5F3FC", "#B5E550"]


@app.callback(
    Output("store-migtime-table", "data", allow_duplicate=True),
    Input("seq-animal-dropdown", "value"),
    Input("btn-autodetect-all", "n_clicks"),
    Input("seq-num-sequences", "value"),
    State("store-processed-data", "data"),
    State("seq-bio-year-month", "value"),
    State("seq-bio-year-day", "value"),
    State("store-migtime-table", "data"),
    prevent_initial_call=True,
)
def build_migtime_store(selected_animal, autodetect_clicks, n_seqs, processed_json, bio_month, bio_day, current_migtime_json):
    """Tab-2 migtime WRITER (split out from the old monolithic callback so the
    renderer below can take store-migtime-table as an Input without creating a
    circular dependency).

    Writes the migtime store in exactly two situations:
      - First-ever render for this project (store empty) → build an EMPTY
        scaffold so downstream consumers have rows to fill. No detection: the
        map stays all-black until the user opts in.
      - "Auto-detect All" click → build scaffold + run a full-DF NSD detection
        pass and populate every animal's slots.

    The scaffold always carries all 8 mig slot columns, so a sequence-count
    change needs no rebuild — the renderer simply shows more/fewer cards.
    Plain animal navigation and num-sequences changes leave the table untouched
    (PreventUpdate) so user edits, Clear Sequences, and Load Previous Table all
    survive. The renderer reads whatever is in the table; it never writes it.
    """
    if not processed_json or not selected_animal:
        raise PreventUpdate

    bio_month = int(bio_month or 2)
    bio_day = int(bio_day or 1)
    n_seqs_int = int(n_seqs or 4)

    triggered = ctx.triggered_id
    should_auto_populate = (triggered == "btn-autodetect-all")
    should_build_scaffold = should_auto_populate or (not current_migtime_json)
    if not should_build_scaffold:
        raise PreventUpdate

    df, nsd_col = _seq_working_df(processed_json, bio_month, bio_day)
    nsd_detect_col = nsd_col or "nsd_id_bio_year"

    try:
        migtime = build_migtime_table(df, num_sequences=n_seqs_int)
        if should_auto_populate:
            if nsd_detect_col not in df.columns:
                raise ValueError(f"NSD column '{nsd_detect_col}' not found.")
            all_detections = detect_migrations_nsd(
                df,
                id_col="animal_id",
                bio_year_col="id_bio_year",
                nsd_col=nsd_detect_col,
                date_col="timestamp",
                max_sequences=n_seqs_int,
            )
            migtime = apply_auto_detections(migtime, all_detections)
        for col in migtime.columns:
            if pd.api.types.is_datetime64_any_dtype(migtime[col]):
                migtime[col] = migtime[col].astype(str)
        return _df_to_json(migtime, "migtime")
    except Exception:
        # Never wipe an existing table on a detection error.
        raise PreventUpdate


@app.callback(
    Output("nsd-plot", "figure"),
    Output("displacement-plot", "figure"),
    Output("speed-plot", "figure"),
    Output("elevation-plot", "figure"),
    Output("seq-date-ranges", "children"),
    Output("seq-confidence", "children"),
    Output("store-slider-date-min", "data"),
    Input("seq-animal-dropdown", "value"),
    Input("store-migtime-table", "data"),
    Input("store-seq-names", "data"),
    Input("seq-num-sequences", "value"),
    Input("nsd-overlay-toggles", "value"),
    State("store-processed-data", "data"),
    State("seq-bio-year-month", "value"),
    State("seq-bio-year-day", "value"),
    prevent_initial_call=True,
)
def render_seq_panels(selected_animal, migtime_json, seq_names, n_seqs, nsd_overlays, processed_json, bio_month, bio_day):
    """Tab-2 RENDERER: rebuild the four plots + the slider cards from the
    migtime table, which is the single source of truth for which sequences
    exist for this animal.

    Crucially this does NOT re-run auto-detection — it only paints what the
    migtime table already holds. That's what fixes the "cleared bands won't go
    away" bug: clearing (the Clear Sequences button or a per-slot clear) blanks
    the row, this callback re-fires on the resulting store change, finds no
    windows, and draws no bands. Sequence labels come from store-seq-names so a
    rename (mig1 → Spring) shows up on the bands and card headers immediately.
    """
    if not processed_json or not selected_animal:
        raise PreventUpdate

    bio_month = int(bio_month or 2)
    bio_day = int(bio_day or 1)

    df, nsd_col = _seq_working_df(processed_json, bio_month, bio_day)

    disp_col = "displacement_id_bio_year" if "displacement_id_bio_year" in df.columns else None
    if disp_col is None:
        disp_cols = [c for c in df.columns if c.startswith("displacement_")]
        disp_col = disp_cols[0] if disp_cols else None

    # Extract bio_year from selected id_bio_year (format: "ANIMAL_YEAR")
    # and compute the bio-year date window
    animal_id_part = "_".join(selected_animal.rsplit("_", 1)[:-1]) if "_" in selected_animal else selected_animal
    bio_year_str = selected_animal.rsplit("_", 1)[-1] if "_" in selected_animal else ""
    try:
        bio_year_int = int(bio_year_str)
        if bio_year_int < 100:
            bio_year_int += 2000
        bio_start = pd.Timestamp(year=bio_year_int, month=bio_month, day=bio_day)
        bio_end = pd.Timestamp(year=bio_year_int + 1, month=bio_month, day=bio_day) - pd.Timedelta(days=1)
    except (ValueError, TypeError):
        bio_start = None
        bio_end = None

    # Filter to selected animal-year using the *id_bio_year column itself* —
    # the same key build_migtime_store groups on, so the renderer and the
    # writer always agree on which rows belong to this animal-year.
    if "id_bio_year" in df.columns:
        mask = df["id_bio_year"] == selected_animal
    else:
        animal_id_col = "animal_id" if "animal_id" in df.columns else None
        if animal_id_col and bio_start is not None:
            mask = (df[animal_id_col] == animal_id_part) & (df["timestamp"] >= bio_start) & (df["timestamp"] <= bio_end)
        else:
            mask = pd.Series(True, index=df.index)
    animal_df = df[mask].sort_values("timestamp") if "timestamp" in df.columns else df[mask]

    # ---- Shared overlay data for all charts ----
    _overlays = nsd_overlays or []
    has_prob = "problem" in animal_df.columns
    has_mort = "mortality_flag" in animal_df.columns
    marker_colors = pd.Series("#FFFFFF", index=animal_df.index)
    if has_prob and "problem" in _overlays:
        marker_colors[animal_df["problem"].astype(bool)] = "#FFB000"
    if has_mort and "mortality" in _overlays:
        marker_colors[animal_df["mortality_flag"].astype(bool)] = "#DC3220"
    marker_colors_list = marker_colors.tolist()

    gap_traces = []
    if "gaps" in _overlays and "timestamp" in animal_df.columns and len(animal_df) > 1:
        ts = animal_df["timestamp"].reset_index(drop=True)
        dt_hours = ts.diff().dt.total_seconds() / 3600
        gap_mask = dt_hours > 26
        gap_idxs = gap_mask[gap_mask].index
        if len(gap_idxs):
            gap_x, gap_text = [], []
            for idx in gap_idxs:
                t0, t1 = ts.iloc[idx - 1], ts.iloc[idx]
                gap_x.append(t0 + (t1 - t0) / 2)
                gap_text.append(
                    f"⚠ {dt_hours.iloc[idx]:.0f}h gap<br>"
                    f"{t0.strftime('%b %d %H:%M')} → {t1.strftime('%b %d %H:%M')}"
                )
            gap_traces = (gap_x, gap_text)

    def _add_overlays(fig, y_series):
        """Add flag markers and gap diamonds to any chart figure."""
        if "problem" in _overlays and has_prob and animal_df["problem"].any():
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers", name="Problem",
                marker={"color": "#FFB000", "size": 7}, showlegend=True,
            ))
        if "mortality" in _overlays and has_mort and animal_df["mortality_flag"].any():
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers", name="Mortality",
                marker={"color": "#DC3220", "size": 7}, showlegend=True,
            ))
        if gap_traces and y_series is not None:
            gap_x, gap_text = gap_traces
            ts_reset = animal_df["timestamp"].reset_index(drop=True)
            y_reset = y_series.reset_index(drop=True)
            dt_hours_l = ts_reset.diff().dt.total_seconds() / 3600
            gap_idxs_l = (dt_hours_l > 26)
            gap_idxs_l = gap_idxs_l[gap_idxs_l].index
            gap_y = []
            for idx in gap_idxs_l:
                gap_y.append(max(y_reset.iloc[idx - 1], y_reset.iloc[idx]))
            fig.add_trace(go.Scatter(
                x=gap_x, y=gap_y, mode="markers", name="Fix gap (>26h)",
                marker={"symbol": "diamond", "color": "#785EF0", "size": 10,
                        "line": {"color": "#5A3FD4", "width": 1}},
                hovertext=gap_text, hoverinfo="text",
            ))

    # ---- NSD plot ----
    nsd_fig = go.Figure()
    nsd_y = None
    if nsd_col and nsd_col in animal_df.columns:
        nsd_y = animal_df[nsd_col]
        nsd_fig.add_trace(go.Scatter(
            x=animal_df["timestamp"], y=nsd_y,
            mode="lines+markers", name="NSD",
            line={"color": "#cfcfcf", "width": 1.2},
            marker={"color": marker_colors_list, "size": 3.5},
        ))
        _add_overlays(nsd_fig, nsd_y)
    nsd_fig.update_layout(
        template="plotly_dark",
        uirevision=selected_animal,
        title=f"NSD — {selected_animal}",
        xaxis_title="", yaxis_title="NSD (km²)",
        yaxis={"rangemode": "nonnegative"},
        dragmode="pan",
        margin={"l": 50, "r": 20, "t": 40, "b": 40},
        legend={"orientation": "h"},
    )

    # ---- Displacement plot ----
    disp_fig = go.Figure()
    disp_y = None
    if disp_col and disp_col in animal_df.columns:
        disp_y = animal_df[disp_col]
        disp_fig.add_trace(go.Scatter(
            x=animal_df["timestamp"], y=disp_y,
            mode="lines+markers", name="Displacement",
            line={"color": "#cfcfcf", "width": 1.2},
            marker={"color": marker_colors_list, "size": 3.5},
        ))
        _add_overlays(disp_fig, disp_y)
    disp_fig.update_layout(
        template="plotly_dark",
        uirevision=selected_animal,
        title="Displacement (km)",
        xaxis_title="", yaxis_title="km",
        dragmode="pan",
        margin={"l": 50, "r": 20, "t": 30, "b": 30},
        legend={"orientation": "h"},
    )

    # ---- Speed plot ----
    speed_fig = go.Figure()
    speed_y = None
    if "speed" in animal_df.columns:
        speed_y = animal_df["speed"] * 3.6
        speed_fig.add_trace(go.Scatter(
            x=animal_df["timestamp"], y=speed_y,
            mode="lines+markers", name="Speed",
            line={"color": "#cfcfcf", "width": 1},
            marker={"color": marker_colors_list, "size": 3.5},
        ))
        _add_overlays(speed_fig, speed_y)
    speed_fig.update_layout(
        template="plotly_dark",
        uirevision=selected_animal,
        title="Speed (km/h)",
        xaxis_title="", yaxis_title="km/h",
        dragmode="pan",
        margin={"l": 50, "r": 20, "t": 30, "b": 30},
        legend={"orientation": "h"},
    )

    # ---- Elevation plot ----
    elev_fig = go.Figure()
    elev_y = None
    if "elevation_m" in animal_df.columns and animal_df["elevation_m"].notna().any():
        elev_y = animal_df["elevation_m"]
        elev_fig.add_trace(go.Scatter(
            x=animal_df["timestamp"], y=elev_y,
            mode="lines+markers", name="Elevation",
            line={"color": "#cfcfcf", "width": 1},
            marker={"color": marker_colors_list, "size": 3.5},
        ))
        _add_overlays(elev_fig, elev_y)
        elev_title = "Elevation (m)"
    else:
        elev_title = "Elevation — not sampled (enable in Tab 1 raster variables)"
    elev_fig.update_layout(
        template="plotly_dark",
        uirevision=selected_animal,
        title=elev_title,
        xaxis_title="", yaxis_title="m",
        dragmode="pan",
        margin={"l": 50, "r": 20, "t": 30, "b": 30},
        legend={"orientation": "h"},
    )

    # Set x-axis range to bio-year window on all charts. Also stash the exact
    # bio-year range in layout.meta so the double-click toggle in
    # map_functions.js has an authoritative value to snap back to, instead of
    # guessing the bio window from the live range (which broke when Plotly's
    # autorange padding made a zoomed-in data extent look ~1 year wide).
    if bio_start is not None and bio_end is not None:
        x_range = [bio_start.isoformat(), bio_end.isoformat()]
        for _fig in (nsd_fig, disp_fig, speed_fig, elev_fig):
            _fig.update_layout(xaxis_range=x_range, meta={"bioRange": x_range})

    # ---- Sequences to draw — read straight from the migtime table ----
    # The migtime row for this animal IS the source of truth: whichever
    # mig{i}_start/_end slots are populated become bands + filled slider cards;
    # everything else is an empty slot. No auto-detection runs here, so a clear
    # (Clear Sequences button → blanks the row, or a per-slot clear → blanks one
    # slot) makes the corresponding band simply not get drawn on the next
    # render. detection only happens in build_migtime_store (Auto-detect All).
    date_range_children = []
    confidence_text = ""
    date_min = bio_start if bio_start is not None else pd.Timestamp("2020-01-01")
    date_max = bio_end if bio_end is not None else pd.Timestamp("2021-01-01")

    n_seqs_int = int(n_seqs or 4)
    total_days = (date_max - date_min).days or 1
    slider_marks = {}
    for tick in range(0, total_days + 1, max(1, total_days // 5)):
        d = date_min + pd.Timedelta(days=tick)
        slider_marks[tick] = {
            "label": d.strftime("%b %d"),
            "style": {"fontSize": "0.65rem", "color": "#FFFFFF", "whiteSpace": "nowrap"},
        }

    # Sequence labels — store-seq-names is the authoritative, ordered list set
    # by the Sequence Names inputs. A blank slot falls back to "mig{n}". The
    # slider/clear component ids stay keyed on the stable "mig{n}" slot key
    # (slider_to_migtime / clear_single_sequence parse the slot number out of
    # it) — only the *displayed* header text uses the friendly label.
    seq_names = seq_names or []

    def _label(slot0: int) -> str:
        if slot0 < len(seq_names) and str(seq_names[slot0]).strip():
            return str(seq_names[slot0]).strip()
        return f"mig{slot0 + 1}"

    # Pull this animal's defined windows out of the migtime row.
    active_by_slot: dict[int, dict] = {}
    seq_cleared = False
    try:
        if migtime_json:
            mt = _json_to_df(migtime_json, "migtime")
            if "id_bio_year" in mt.columns:
                rm = mt.loc[mt["id_bio_year"] == selected_animal]
                if not rm.empty:
                    r = rm.iloc[0]
                    seq_cleared = bool(r.get("seq_cleared", False))
                    _blank = ("", "NaT", "nan", "None")
                    for i in range(1, n_seqs_int + 1):
                        sk, ek = f"mig{i}_start", f"mig{i}_end"
                        if sk in r and pd.notna(r[sk]) and str(r[sk]) not in _blank:
                            s = pd.Timestamp(r[sk])
                            if ek in r and pd.notna(r[ek]) and str(r[ek]) not in _blank:
                                e = pd.Timestamp(r[ek])
                            else:
                                e = s
                            active_by_slot[i - 1] = {"start": s, "end": e}
    except Exception:
        # Defensive — never let a malformed migtime row break the render path.
        active_by_slot = {}

    # Shade the bands from the migtime windows on ALL charts.
    for slot0, win in sorted(active_by_slot.items()):
        for _fig in (nsd_fig, disp_fig, speed_fig, elev_fig):
            _fig.add_vrect(
                x0=win["start"],
                x1=win["end"],
                fillcolor=SEQ_COLORS[slot0 % len(SEQ_COLORS)],
                opacity=0.45,
                layer="below",
                line_width=0,
                annotation_text=_label(slot0),
                annotation_position="top left",
            )

    if active_by_slot and "timestamp" in animal_df.columns:
        for slot0, win in active_by_slot.items():
            ts_mask = (animal_df["timestamp"] >= win["start"]) & (animal_df["timestamp"] <= win["end"])
            marker_colors[ts_mask] = SEQ_COLORS[slot0 % len(SEQ_COLORS)]
        updated_colors = marker_colors.tolist()
        for _fig in (nsd_fig, disp_fig, speed_fig, elev_fig):
            if _fig.data:
                _fig.data[0].marker.color = updated_colors

    if seq_cleared:
        confidence_text = (
            f"Sequences cleared for {selected_animal}. Drag any slider to start "
            f"defining a window manually, or click Auto-detect All to re-run detection."
        )
    elif active_by_slot:
        n_filled = len(active_by_slot)
        empty = n_seqs_int - n_filled
        confidence_text = (
            f"{n_filled} sequence(s) defined for {selected_animal}."
            + (f" {empty} empty slot(s) open for manual definition." if empty > 0 else "")
        )
    else:
        confidence_text = (
            f"No sequences defined for {selected_animal}. Click Auto-detect All to "
            f"detect migrations, or drag a slider to define one manually."
        )

    n_problem = int(animal_df["problem"].sum()) if "problem" in animal_df.columns else 0
    n_mortality = int(animal_df["mortality_flag"].sum()) if "mortality_flag" in animal_df.columns else 0
    if n_problem or n_mortality:
        parts = []
        if n_problem:
            parts.append(f"{n_problem:,} problem")
        if n_mortality:
            parts.append(f"{n_mortality:,} mortality")
        confidence_text += f"  Excluded from sequencing: {', '.join(parts)}."

    # ---- Render the slider cards ----
    # Always render n_seqs slider cards — filled from active_by_slot if the slot
    # has a window, otherwise an empty [0, 0] slot. Each card uses
    # pattern-matching ids keyed on the stable slot key "mig{n}".
    for slot_idx in range(n_seqs_int):
        color = SEQ_COLORS[slot_idx % len(SEQ_COLORS)]
        slot_key = f"mig{slot_idx + 1}"          # stable id for slider_to_migtime / clear
        display_name = _label(slot_idx)          # friendly header (e.g. "Spring")
        if slot_idx in active_by_slot:
            win = active_by_slot[slot_idx]
            s_date = pd.Timestamp(win["start"]) if pd.notna(win["start"]) else date_min
            e_date = pd.Timestamp(win["end"]) if pd.notna(win["end"]) else date_min
            start_day = max(0, (s_date.normalize() - date_min).days)
            end_day = max(start_day + 1, (e_date.normalize() - date_min).days)
            s_date_str = str(s_date)[:10]
            e_date_str = str(e_date)[:10]
            meta_html = html.Small("  Defined", className="text-muted ms-2")
        else:
            start_day = 0
            end_day = 0
            s_date_str = ""
            e_date_str = ""
            meta_html = html.Small(
                "  Empty — drag the slider or enter dates",
                className="text-muted ms-2",
                style={"fontStyle": "italic"},
            )

        date_range_children.append(
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.Strong(display_name, style={"fontSize": "0.85rem", "color": color}),
                                meta_html,
                                dbc.Button(
                                    "Clear sequence",
                                    id={"type": "btn-clear-seq", "index": slot_key},
                                    color="secondary",
                                    outline=True,
                                    size="sm",
                                    className="float-end py-0",
                                    style={"fontSize": "0.7rem"},
                                ),
                            ],
                        ),
                        html.Div(
                            dcc.RangeSlider(
                                id={"type": "seq-range-slider", "index": slot_key},
                                min=0,
                                max=total_days,
                                step=1,
                                value=[start_day, end_day],
                                marks=slider_marks,
                                tooltip={
                                    "placement": "top",
                                    "always_visible": True,
                                    "transform": "dayToDate",
                                    "style": {
                                        "fontSize": "0.6rem",
                                        "padding": "0px 3px",
                                        "color": "#000",
                                        "backgroundColor": "#fff",
                                    },
                                },
                                allowCross=False,
                                pushable=1,
                                className=f"seq-range-slider seq-slider-{slot_idx}",
                            ),
                            style={"padding": "5px 0 0 0"},
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        dbc.Label("Start", style={"fontSize": "0.7rem"}),
                                        dbc.Input(
                                            id={"type": "seq-start", "index": slot_key},
                                            type="date",
                                            value=s_date_str,
                                            size="sm",
                                            style={"fontSize": "0.75rem"},
                                        ),
                                    ],
                                    width=6,
                                ),
                                dbc.Col(
                                    [
                                        dbc.Label("End", style={"fontSize": "0.7rem"}),
                                        dbc.Input(
                                            id={"type": "seq-end", "index": slot_key},
                                            type="date",
                                            value=e_date_str,
                                            size="sm",
                                            style={"fontSize": "0.75rem"},
                                        ),
                                    ],
                                    width=6,
                                ),
                            ],
                            className="g-1 mt-1",
                        ),
                    ],
                    className="p-2",
                ),
                className="mb-2",
            )
        )

    return nsd_fig, disp_fig, speed_fig, elev_fig, date_range_children, confidence_text, date_min.isoformat()


# ---------------------------------------------------------------------------
# Import an externally-created migtime CSV (e.g. the WMI Migration Mapper
# export format: id_bioYear, newUid, bioYear, bioYearFull, tempStartMonth/Day,
# mig1start..mig8end, notes). Mapped onto our internal schema so Tab 2 and the
# modeling pipeline can consume it directly.
# ---------------------------------------------------------------------------

def _norm_hdr(h) -> str:
    """Normalise a column header for fuzzy matching: lower-case, keep only
    alphanumerics. So 'mig1start', 'mig1_start', 'Mig1 Start' all collapse to
    'mig1start', and 'bioYearFull' -> 'bioyearfull'."""
    return "".join(ch for ch in str(h).lower() if ch.isalnum())


def _norm_animal(s) -> str:
    """Normalise an animal id for cross-source matching: collapse any run of
    non-alphanumeric characters into a single underscore, preserving case.
    This makes the WMI-style ``E18-SP-14-2022-010823`` (hyphens) line up with
    our processed ``E18_SP_14_2022_010823`` (underscores). Used to snap an
    imported migtime's animal ids onto the ids actually present in the loaded
    GPS data."""
    out = []
    prev_us = True  # leading True so we don't start with '_'
    for ch in str(s):
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        elif not prev_us:
            out.append("_")
            prev_us = True
    return "".join(out).rstrip("_")


def _sniff_migtime_columns(raw_text: str):
    """Peek at an uploaded migtime CSV. Returns
    (headers, guessed_animal_id_col, detected_bio_month, detected_bio_day).
    Used to pre-populate the import UI before the user commits."""
    df = pd.read_csv(io.StringIO(raw_text), nrows=5)
    headers = [str(c) for c in df.columns]
    norm = {_norm_hdr(h): h for h in headers}

    # Guess the animal-id column. Prefer the WMI 'newUid'; otherwise the first
    # header that looks like a uid/id but isn't the bio-year compound key.
    guess = None
    for cand in ("newuid", "animalid", "uid", "aid", "id"):
        if cand in norm:
            guess = norm[cand]
            break
    if guess is None:
        for h in headers:
            nh = _norm_hdr(h)
            if "uid" in nh or (nh.endswith("id") and "bio" not in nh and nh != "idbioyear"):
                guess = h
                break

    # Detect the bio-year start month/day if the file carries it.
    def _first_int(colkey):
        col = norm.get(colkey)
        if not col:
            return None
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        return int(s.iloc[0]) if len(s) else None

    month = _first_int("tempstartmonth") or _first_int("startmonth") or _first_int("biostartmonth")
    day = _first_int("tempstartday") or _first_int("startday") or _first_int("biostartday")
    return headers, guess, month, day


def _parse_external_migtime(
    raw_text: str,
    animal_id_col: str,
    bio_month: int,
    bio_day: int,
    processed_animal_ids=None,
):
    """Map an external migtime CSV onto our internal schema.

    Returns (migtime_df, notes_dict, n_rows, n_rows_with_sequences,
    n_animals_matched, n_animals_total).

    Key reconstruction: our app keys everything on
    ``id_bio_year = <animal_id>_<4-digit bio-year>`` (the bio-year recomputed
    from the GPS timestamps + the bio-year start). External files often store a
    2-digit suffix (e.g. ``..._22``) and a separate full-year column
    (``bioYearFull``), and may format the animal name differently (hyphens vs
    underscores). We therefore (a) snap each file animal id onto the matching id
    in the loaded GPS data via `_norm_animal`, and (b) rebuild the key as
    ``animal_id + '_' + bioYearFull`` so it lines up with the processed data
    once the Tab-2 bio-year start is set to the same month/day.
    """
    df = pd.read_csv(io.StringIO(raw_text))
    norm = {_norm_hdr(h): h for h in df.columns}

    if animal_id_col not in df.columns:
        raise ValueError(f"Animal-ID column '{animal_id_col}' not found in the file.")

    raw_animal = df[animal_id_col].astype(str).str.strip()

    # Snap file animal ids onto the actual GPS animal ids (handles hyphen vs
    # underscore and other separator differences). Falls back to the normalised
    # form when there's no processed-data match to compare against.
    norm_to_actual = {}
    for a in (processed_animal_ids or []):
        norm_to_actual.setdefault(_norm_animal(a), str(a))
    animal = raw_animal.map(lambda a: norm_to_actual.get(_norm_animal(a), _norm_animal(a)))

    uniq_raw = set(raw_animal)
    n_animals_total = len(uniq_raw)
    n_animals_matched = (
        sum(1 for a in uniq_raw if _norm_animal(a) in norm_to_actual)
        if norm_to_actual else 0
    )

    # Full (4-digit) bio-year. Prefer an explicit full-year column; else take a
    # bio-year/year column and widen 2-digit values (22 -> 2022).
    fy_col = None
    for cand in ("bioyearfull", "bioyrfull", "fullbioyear", "bioyearfullyear"):
        if cand in norm:
            fy_col = norm[cand]
            break
    if fy_col is None:
        for cand in ("bioyear", "bioyr", "year"):
            if cand in norm:
                fy_col = norm[cand]
                break

    def _widen(v):
        if pd.isna(v):
            return None
        v = int(v)
        return v + 2000 if v < 100 else v

    if fy_col is not None:
        full_year = [_widen(v) for v in pd.to_numeric(df[fy_col], errors="coerce")]
    else:
        # Fall back to the suffix of an id_bioYear-style key.
        id_col = norm.get("idbioyear")
        if id_col is not None:
            full_year = [
                _widen(pd.to_numeric(str(k).rsplit("_", 1)[-1], errors="coerce"))
                for k in df[id_col]
            ]
        else:
            full_year = [None] * len(df)

    out = pd.DataFrame()
    out["animal_id"] = animal
    out["bio_year_full"] = ["" if y is None else str(y) for y in full_year]
    out["bio_year"] = out["bio_year_full"]
    out["id_bio_year"] = out["animal_id"] + "_" + out["bio_year_full"]

    # Reverse-map friendly column names (Spring_start → mig1_start) using the
    # seq_map legend written at export time, so re-imported exports round-trip.
    if "seq_map" in df.columns:
        legend = str(df["seq_map"].iloc[0]) if len(df) else ""
        for pair in legend.split(";"):
            if "=" not in pair:
                continue
            slot, nm = pair.split("=", 1)
            slot, nm = slot.strip(), nm.strip()
            if not (slot.startswith("mig") and nm and nm != slot):
                continue
            for suffix in ("_start", "_end"):
                friendly = f"{nm}{suffix}"
                if friendly in df.columns:
                    df = df.rename(columns={friendly: f"{slot}{suffix}"})
        df = df.drop(columns=["seq_map"], errors="ignore")
        norm = {_norm_hdr(h): h for h in df.columns}

    # If no seq_map was present, try to match any <Name>_start/<Name>_end pairs
    # to sequential mig slots so exports from older versions still import.
    has_any_mig = any(norm.get(f"mig{i}start") for i in range(1, 9))
    if not has_any_mig:
        used_cols = set()
        slot_i = 1
        for col in df.columns:
            if col.endswith("_start") and col not in used_cols:
                base = col[:-6]
                end_col = f"{base}_end"
                if end_col in df.columns:
                    df = df.rename(columns={col: f"mig{slot_i}_start", end_col: f"mig{slot_i}_end"})
                    used_cols.update({col, end_col})
                    slot_i += 1
                    if slot_i > 8:
                        break
        norm = {_norm_hdr(h): h for h in df.columns}

    start_cols = []
    for i in range(1, 9):
        for suf in ("start", "end"):
            src = norm.get(f"mig{i}{suf}")
            colname = f"mig{i}_{suf}"
            if src is not None:
                out[colname] = (
                    pd.to_datetime(df[src], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
                )
            else:
                out[colname] = ""
            if suf == "start":
                start_cols.append(colname)

    notes_col = norm.get("notes")
    out["notes"] = df[notes_col].fillna("").astype(str) if notes_col is not None else ""
    out["auto_detected"] = False
    out["reviewed"] = True

    # Count rows that actually carry at least one sequence window.
    has_seq = out[start_cols].apply(lambda r: any(bool(str(x)) for x in r), axis=1)
    n_with_seq = int(has_seq.sum())

    notes_dict = {
        k: v for k, v in zip(out["id_bio_year"], out["notes"]) if v and not k.endswith("_")
    }
    return out, notes_dict, len(out), n_with_seq, n_animals_matched, n_animals_total


# ---------------------------------------------------------------------------
# Migtime table: export / load-previous / overwrite. Files live in
# <workdir>/ModelOutputs/Migtime_Exports/migtime_<YYYYMMDD_HHMMSS>.csv.
# ---------------------------------------------------------------------------

def _friendly_migtime_for_export(migtime: "pd.DataFrame", seq_names) -> "pd.DataFrame":
    """Return a copy of the migtime table with the per-slot date columns renamed
    to the user's sequence labels (mig1_start → Spring_start, …) for the
    human-facing CSV, plus a `seq_map` legend column recording the slot→label
    mapping ("mig1=Spring;mig2=Summer;…").

    The mapping is what lets load_previous_migtime restore the canonical mig{n}
    column names on re-import, so the in-memory schema the pipeline relies on
    (extract_sequences keys off mig{n}_start/_end) round-trips losslessly. Slots
    left at the default "mig{n}" are not renamed and not added to the legend.
    """
    names = list(seq_names or [])
    out = migtime.copy()
    rename_map: dict[str, str] = {}
    legend: list[str] = []
    for i in range(1, 9):
        nm = names[i - 1].strip() if i - 1 < len(names) and str(names[i - 1]).strip() else ""
        if not nm or nm == f"mig{i}":
            continue
        for suffix in ("start", "end"):
            src = f"mig{i}_{suffix}"
            if src in out.columns:
                rename_map[src] = f"{nm}_{suffix}"
        legend.append(f"mig{i}={nm}")
    if rename_map:
        out = out.rename(columns=rename_map)
        out["seq_map"] = ";".join(legend)
    return out


def _migtime_exports_dir(workdir_path: str | None) -> Path | None:
    if not workdir_path:
        return None
    p = Path(workdir_path)
    if not p.is_dir():
        return None
    out = _workdir_outputs(p) / "Migtime_Exports"
    return out


@app.callback(
    Output("store-migtime-table", "data", allow_duplicate=True),
    Output("migtime-status", "children", allow_duplicate=True),
    Input("btn-clear-sequences", "n_clicks"),
    State("store-migtime-table", "data"),
    State("seq-animal-dropdown", "value"),
    prevent_initial_call=True,
)
def clear_current_animal_sequences(n_clicks, migtime_json, selected_animal):
    """Reset every sequence slider for the *currently selected* animal-year
    back to [0, 0]. Blanks mig{1..8}_start/_end on that row and stamps
    `seq_cleared=True`. Other animals' rows are untouched, as are the user's
    free-text notes / road-crossing flags.

    Blanking the dates is what makes render_seq_panels draw no bands (it reads
    the migtime row as the source of truth); the sticky `seq_cleared` flag just
    drives the "Sequences cleared…" status message and survives animal
    navigation. The flag is flipped back to False the moment the user drags a
    slider (see slider_to_migtime) — that's the signal they're actively
    defining sequences again. Writing the store (with a fresh rev token) re-
    fires render_seq_panels and update_seq_map, so the chart bands and the map
    point colours both drop immediately.
    """
    if not migtime_json:
        return dash.no_update, _err_alert("No migtime table yet — pick an animal first.")
    if not selected_animal:
        return dash.no_update, _err_alert("Pick an animal-year first.")

    migtime = _json_to_df(migtime_json, "migtime")
    if "id_bio_year" not in migtime.columns:
        return dash.no_update, _err_alert("Migtime table missing id_bio_year column.")

    mask = migtime["id_bio_year"] == selected_animal
    if not mask.any():
        return dash.no_update, _err_alert(f"No migtime row for {selected_animal}.")

    cleared = 0
    for i in range(1, 9):
        for suffix in ("start", "end"):
            col = f"mig{i}_{suffix}"
            if col in migtime.columns:
                cleared += int((migtime.loc[mask, col].astype(str).str.len() > 0).sum())
                migtime.loc[mask, col] = ""
    if "auto_detected" in migtime.columns:
        migtime.loc[mask, "auto_detected"] = False
    # New per-row sticky flag — survives animal navigation, gets flipped off
    # by slider drag or the next Auto-detect All click (scaffold rebuild).
    if "seq_cleared" not in migtime.columns:
        migtime["seq_cleared"] = False
    migtime.loc[mask, "seq_cleared"] = True

    return _df_to_json(migtime, "migtime"), _ok_alert(
        f"Cleared {cleared} date entries for {selected_animal}. Sliders reset to 0."
    )


@app.callback(
    Output({"type": "seq-range-slider", "index": dash.MATCH}, "value"),
    Input({"type": "btn-clear-seq", "index": dash.MATCH}, "n_clicks"),
    prevent_initial_call=True,
)
def clear_single_sequence(n_clicks):
    """Per-slot clear: snap the same-index slider to [0, 0]. The existing
    `slider_to_migtime` callback then writes blank mig{N}_start/_end into
    the current animal's migtime row, so we don't need to touch the store
    directly here — keeping this callback Output-MATCH-only is what lets
    Dash accept the pattern-matching wildcard."""
    if not n_clicks:
        raise PreventUpdate
    return [0, 0]


def _crossing_phrase(crosses_road: bool, crosses_highway: bool) -> str:
    """Single canonical statement about road/highway crossings for a notes
    cell. Highway supersedes road — at most one phrase is ever returned."""
    if crosses_highway:
        return "Crosses highway."
    if crosses_road:
        return "Crosses road."
    return ""


def _populate_migtime_notes(
    migtime: "pd.DataFrame",
    notes_store: dict | None,
    road_store: dict | None,
) -> None:
    """Fill migtime['notes'] in place from the per-animal notes + crossings
    stores. Keyed by id_bio_year. Highway crossing supersedes road; only one
    canonical crossing phrase is appended per row."""
    notes_store = notes_store or {}
    road_store = road_store or {}
    if "notes" not in migtime.columns:
        migtime["notes"] = ""
    if "id_bio_year" not in migtime.columns:
        return
    def _row_note(key: object) -> str:
        user_note = notes_store.get(str(key), "")
        rc = road_store.get(str(key), {}) or {}
        return _compose_notes(
            user_note,
            bool(rc.get("crosses_road", False)),
            bool(rc.get("crosses_highway", False)),
        )
    migtime["notes"] = migtime["id_bio_year"].map(_row_note)


def _compose_notes(user_note: str, crosses_road: bool, crosses_highway: bool) -> str:
    """Join the user's free-text note with the canonical crossing phrase.

    Strips trailing whitespace from the user note before appending so the
    result reads as one sentence followed by another. Idempotent: if the
    user already typed the crossing phrase into the note, we still re-emit
    exactly one canonical phrase (we strip any prior copy).
    """
    note = (user_note or "").strip()
    # Remove any previously-appended crossing phrase so re-exports don't double up.
    for phrase in ("Crosses highway.", "Crosses road."):
        if note.endswith(phrase):
            note = note[: -len(phrase)].rstrip()
    phrase = _crossing_phrase(crosses_road, crosses_highway)
    if not phrase:
        return note
    return f"{note} {phrase}".strip()


@app.callback(
    Output("migtime-status", "children", allow_duplicate=True),
    Input("btn-export-migtime", "n_clicks"),
    State("store-migtime-table", "data"),
    State("store-workdir", "data"),
    State("store-animal-notes", "data"),
    State("store-road-crossings", "data"),
    State("store-processed-data", "data"),
    State("store-config", "data"),
    State("store-animal-classification", "data"),
    State("store-seq-names", "data"),
    prevent_initial_call=True,
)
def export_migtime(n_clicks, migtime_json, workdir_path, notes_store, road_store, processed_json, config_json, class_store, seq_names):
    """Export Updated Table — writes the migtime CSV AND persists the
    in-memory processed-data flag state to disk. Flag clicks themselves are
    now in-memory-only so they stay snappy; this button is the single point
    where flag edits are flushed to the project parquet + workdir parquet +
    FlagsRemoved.gpkg.
    """
    if not migtime_json:
        return _err_alert("No migtime table to export. Visit Tab 2 and run auto-detection first.")
    exports_dir = _migtime_exports_dir(workdir_path)
    if exports_dir is None:
        return _err_alert("Set a working directory in Tab 1 first.")
    exports_dir.mkdir(parents=True, exist_ok=True)

    migtime = _json_to_df(migtime_json, "migtime")
    _populate_migtime_notes(migtime, notes_store, road_store)

    # Animal-years classified Resident or Nomadic are kept out of the analysis:
    # excluded from the exported migtime table (so no migration sequences are
    # built for them), flagged in-place in the processed data via a
    # `classification` column, and archived to ResidentsNomadsRemoved.{csv,shp}
    # alongside FlagsRemoved.gpkg.
    class_store = class_store or {}
    removed_keys = {
        str(k) for k, v in class_store.items() if v in _REMOVED_CLASSIFICATIONS
    }
    n_removed_years = 0
    if removed_keys and "id_bio_year" in migtime.columns:
        before = len(migtime)
        migtime = migtime[~migtime["id_bio_year"].astype(str).isin(removed_keys)].copy()
        n_removed_years = before - len(migtime)

    import datetime as _dt
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = exports_dir / f"migtime_{stamp}.csv"
    # Friendly column names (Spring_start, …) for the CSV + a seq_map legend so
    # the labels follow the project into the export and round-trip back on load.
    export_df = _friendly_migtime_for_export(migtime, seq_names)
    try:
        export_df.to_csv(out_path, index=False)
    except Exception as exc:
        return _err_alert(f"Export failed: {exc}")
    _log_action("MIGTIME_EXPORT", path=str(out_path), rows=len(migtime))
    _append_processing_log(
        [
            f"File: Migtime_Exports/{out_path.name}",
            f"Rows (animal-years): {len(migtime)}",
        ],
        header="MIGTIME TABLE EXPORTED",
    )

    # Flush processed-data flag edits to disk in a background thread so the
    # user can move on to Tab 3 immediately — the migtime CSV (the important
    # part) is already written above.
    rn_msg = ""
    if processed_json:
        def _bg_persist():
            try:
                df = _json_to_df(processed_json, "processed")

                removed_df = pd.DataFrame()
                if removed_keys and "id_bio_year" in df.columns:
                    key_str = df["id_bio_year"].astype(str)
                    mask = key_str.isin(removed_keys)
                    if "classification" not in df.columns:
                        df["classification"] = ""
                    df.loc[mask, "classification"] = key_str[mask].map(class_store)
                    removed_df = df[mask].copy()

                _save_processed_to_disk(df.copy())
                if _ACTIVE_WORKDIR is not None:
                    outputs = _workdir_outputs()
                    removed_dir = outputs / "RemovedPoints"
                    removed_dir.mkdir(parents=True, exist_ok=True)
                    if not removed_df.empty:
                        removed_df["classification"] = (
                            removed_df["id_bio_year"].astype(str).map(class_store)
                        )
                        removed_df.to_csv(removed_dir / "ResidentsNomadsRemoved.csv", index=False)
                        try:
                            import geopandas as gpd
                            if {"lon", "lat"}.issubset(removed_df.columns):
                                grn = gpd.GeoDataFrame(
                                    removed_df,
                                    geometry=gpd.points_from_xy(removed_df["lon"], removed_df["lat"]),
                                    crs="EPSG:4326",
                                )
                                grn.to_file(removed_dir / "ResidentsNomadsRemoved.shp")
                        except Exception as shp_exc:
                            print(f"WARNING: ResidentsNomadsRemoved.shp write failed: {shp_exc}")
                        _log_action(
                            "RESIDENTS_NOMADS_REMOVED",
                            animal_years=n_removed_years,
                            fixes=len(removed_df),
                        )
                    df.to_parquet(str(outputs / "processed_data.parquet"), index=False)
                    herd_id = "Herd"
                    project_name_token = "Project"
                    if config_json:
                        cfg_obj = json.loads(config_json) if isinstance(config_json, str) else config_json
                        if isinstance(cfg_obj, dict):
                            herd_id = str(cfg_obj.get("herd_id", "Herd"))
                            project_name_token = str(cfg_obj.get("project_name", "Project"))
                    try:
                        fr_path = write_flags_removed_shapefile(
                            processed_df=df,
                            out_dir=outputs,
                            herd_id=herd_id,
                            project_name=project_name_token,
                        )
                        if fr_path is not None:
                            _log_action(
                                "FLAGS_REMOVED_EXPORT",
                                trigger="export_button",
                                path=str(fr_path.name),
                            )
                    except Exception as fr_exc:
                        print(f"WARNING: FlagsRemoved refresh failed: {fr_exc}")
            except Exception as exc:
                print(f"WARNING: background flag persist failed: {exc}")
            print("Background flag persistence complete.")

        threading.Thread(target=_bg_persist, daemon=True, name="migtime-flag-persist").start()
        if n_removed_years:
            rn_msg = (
                f" Flagged {n_removed_years} resident/nomadic animal-year(s), "
                f"excluded from analysis."
            )

    return _ok_alert(
        f"Saved to Migtime_Exports/{out_path.name} ({len(migtime)} rows).{rn_msg}"
        f" Flags saving in background."
    )


@app.callback(
    Output("store-migtime-table", "data", allow_duplicate=True),
    Output("migtime-status", "children", allow_duplicate=True),
    Output("store-seq-names", "data", allow_duplicate=True),
    Input("btn-load-migtime", "n_clicks"),
    State("store-workdir", "data"),
    prevent_initial_call=True,
)
def load_previous_migtime(n_clicks, workdir_path):
    exports_dir = _migtime_exports_dir(workdir_path)
    if exports_dir is None:
        return dash.no_update, _err_alert("Set a working directory in Tab 1 first."), dash.no_update
    if not exports_dir.exists():
        return dash.no_update, _err_alert("No migtime tables have been created for this project yet."), dash.no_update

    csvs = sorted(exports_dir.glob("migtime_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not csvs:
        return dash.no_update, _err_alert("No migtime tables have been created for this project yet."), dash.no_update

    latest = csvs[0]
    try:
        migtime = pd.read_csv(latest)
    except Exception as exc:
        return dash.no_update, _err_alert(f"Could not read {latest.name}: {exc}"), dash.no_update

    # Restore friendly-named exports (Spring_start, …) back to the canonical
    # mig{n}_start/_end schema the pipeline relies on, using the seq_map legend
    # written at export time. Also recover the labels so they repopulate the
    # Sequence Names inputs (and thus the chart/cards/export) on load.
    seq_names_out: Any = dash.no_update
    if "seq_map" in migtime.columns:
        legend = str(migtime["seq_map"].iloc[0]) if len(migtime) else ""
        names_by_slot: dict[int, str] = {}
        rename_back: dict[str, str] = {}
        for pair in legend.split(";"):
            if "=" not in pair:
                continue
            slot, nm = pair.split("=", 1)
            slot, nm = slot.strip(), nm.strip()
            if not (slot.startswith("mig") and nm and nm != slot):
                continue
            try:
                slot_i = int(slot[3:])
            except ValueError:
                continue
            names_by_slot[slot_i] = nm
            for suffix in ("start", "end"):
                if f"{nm}_{suffix}" in migtime.columns:
                    rename_back[f"{nm}_{suffix}"] = f"mig{slot_i}_{suffix}"
        if rename_back:
            migtime = migtime.rename(columns=rename_back)
        migtime = migtime.drop(columns=["seq_map"])
        if names_by_slot:
            n_slots = max(names_by_slot)
            seq_names_out = [names_by_slot.get(i + 1, f"mig{i + 1}") for i in range(n_slots)]

    # Keep the mig* date columns as ISO strings (downstream consumers parse on use).
    for col in migtime.columns:
        if col.endswith("_start") or col.endswith("_end"):
            migtime[col] = pd.to_datetime(migtime[col], errors="coerce").astype(str)
    _log_action("MIGTIME_LOAD", path=str(latest), rows=len(migtime))
    return _df_to_json(migtime, "migtime"), _ok_alert(
        f"Loaded {latest.name} ({len(migtime)} rows)."
    ), seq_names_out


@app.callback(
    Output("migtime-status", "children", allow_duplicate=True),
    Input("btn-overwrite-migtime", "n_clicks"),
    State("store-migtime-table", "data"),
    State("store-workdir", "data"),
    State("store-animal-notes", "data"),
    State("store-road-crossings", "data"),
    State("store-seq-names", "data"),
    prevent_initial_call=True,
)
def overwrite_migtime(n_clicks, migtime_json, workdir_path, notes_store, road_store, seq_names):
    if not migtime_json:
        return _err_alert("No migtime table in memory to save.")
    exports_dir = _migtime_exports_dir(workdir_path)
    if exports_dir is None:
        return _err_alert("Set a working directory in Tab 1 first.")
    if not exports_dir.exists():
        return _err_alert(
            "No prior migtime tables exist. Click Export Updated Table to create the first one."
        )
    csvs = sorted(exports_dir.glob("migtime_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not csvs:
        return _err_alert(
            "No prior migtime tables exist. Click Export Updated Table to create the first one."
        )

    target = csvs[0]
    migtime = _json_to_df(migtime_json, "migtime")
    _populate_migtime_notes(migtime, notes_store, road_store)
    export_df = _friendly_migtime_for_export(migtime, seq_names)
    try:
        export_df.to_csv(target, index=False)
    except Exception as exc:
        return _err_alert(f"Overwrite failed: {exc}")
    _log_action("MIGTIME_OVERWRITE", path=str(target), rows=len(migtime))
    return _ok_alert(f"Overwrote {target.name} with current table ({len(migtime)} rows).")


# ---------------------------------------------------------------------------
# Import an external migtime CSV (Tab 1). Two callbacks:
#   handle_migtime_upload — stash the raw text, sniff headers, pre-fill the
#                           Animal-ID column guess + bio-year start.
#   import_migtime        — map it onto our schema, load it into the migtime
#                           store, sync the Tab-2 bio-year start, merge notes.
# ---------------------------------------------------------------------------

@app.callback(
    Output("store-migtime-import-raw", "data"),
    Output("migtime-import-filename", "children"),
    Output("migtime-import-animalid-col", "options"),
    Output("migtime-import-animalid-col", "value"),
    Output("migtime-import-bio-month", "value"),
    Output("migtime-import-bio-day", "value"),
    Output("migtime-import-status", "children"),
    Input("upload-migtime", "contents"),
    State("upload-migtime", "filename"),
    State("migtime-import-bio-month", "value"),
    State("migtime-import-bio-day", "value"),
    prevent_initial_call=True,
)
def handle_migtime_upload(contents, filename, cur_month, cur_day):
    """Read an uploaded migtime CSV into a store + pre-fill the import controls
    (Animal-ID column guess and the bio-year start, if the file carries it).
    No mapping happens yet — that waits for the Import button."""
    if not contents or not filename:
        raise PreventUpdate
    try:
        _ct, b64 = contents.split(",")
        # utf-8-sig strips a BOM if Excel added one.
        raw = base64.b64decode(b64).decode("utf-8-sig", errors="replace")
    except Exception as exc:
        return None, "", [], None, dash.no_update, dash.no_update, _err_alert(f"Could not read file: {exc}")
    try:
        headers, guess, month, day = _sniff_migtime_columns(raw)
    except Exception as exc:
        return None, str(filename), [], None, dash.no_update, dash.no_update, _err_alert(f"Could not parse CSV: {exc}")

    opts = [{"label": h, "value": h} for h in headers]
    fname = html.Span([html.Strong("Loaded: "), str(filename)])
    msg = _ok_alert(
        f"Read {len(headers)} columns. Confirm the Animal-ID column and bio-year start, then click Import Migtime."
    )
    return (
        raw,
        fname,
        opts,
        guess,
        month if month else (cur_month or 2),
        day if day else (cur_day or 1),
        msg,
    )


@app.callback(
    Output("store-migtime-table", "data", allow_duplicate=True),
    Output("store-animal-notes", "data", allow_duplicate=True),
    Output("seq-bio-year-month", "value", allow_duplicate=True),
    Output("seq-bio-year-day", "value", allow_duplicate=True),
    Output("migtime-import-status", "children", allow_duplicate=True),
    Input("btn-import-migtime", "n_clicks"),
    State("store-migtime-import-raw", "data"),
    State("migtime-import-animalid-col", "value"),
    State("migtime-import-bio-month", "value"),
    State("migtime-import-bio-day", "value"),
    State("store-animal-notes", "data"),
    State("store-processed-data", "data"),
    prevent_initial_call=True,
)
def import_migtime(n_clicks, raw, animal_col, bio_month, bio_day, notes_store, processed_json):
    """Map the uploaded migtime CSV onto our internal schema and load it into
    store-migtime-table. Snaps the file's animal ids onto the loaded GPS data's
    ids (so hyphen/underscore differences don't break the join), syncs the
    Tab-2 bio-year start, and merges the file's notes into store-animal-notes."""
    nu = dash.no_update
    if not raw:
        return nu, nu, nu, nu, _err_alert("Upload a migtime CSV first.")
    if not animal_col:
        return nu, nu, nu, nu, _err_alert("Choose which column holds the Animal ID.")

    # Pull the actual animal ids out of the loaded GPS data so we can snap the
    # file's ids onto them (handles hyphen-vs-underscore, etc.).
    processed_animal_ids = None
    if processed_json:
        try:
            pdf = _json_to_df(processed_json, "processed")
            if "animal_id" in pdf.columns:
                processed_animal_ids = pdf["animal_id"].astype(str).unique().tolist()
        except Exception:
            processed_animal_ids = None

    try:
        bio_month = int(bio_month or 2)
        bio_day = int(bio_day or 1)
        migtime, notes_dict, n_rows, n_seq, n_match, n_total = _parse_external_migtime(
            raw, animal_col, bio_month, bio_day, processed_animal_ids
        )
    except Exception as exc:
        return nu, nu, nu, nu, _err_alert(f"Import failed: {exc}")

    if migtime.empty:
        return nu, nu, nu, nu, _err_alert("No rows found in the file.")

    # Merge the file's notes into the per-animal notes store (keyed by the
    # reconstructed id_bio_year) so they surface in Tab 2 and on export.
    notes_store = dict(notes_store or {})
    notes_store.update(notes_dict)
    _save_notes(notes_store)

    _log_action(
        "MIGTIME_IMPORT", rows=n_rows, with_sequences=n_seq,
        animal_col=str(animal_col), animals_matched=n_match, animals_total=n_total,
    )

    if processed_animal_ids is None:
        match_note = (
            " No GPS data loaded yet, so animal ids could not be verified — process your data "
            "in Tab 1 first, then re-import if the sequences don't appear."
        )
    elif n_match == 0:
        match_note = (
            f" ⚠ None of the {n_total} animal ids matched your loaded GPS data — the sequences "
            f"won't appear in Tab 2. Check that you picked the right Animal-ID column."
        )
    elif n_match < n_total:
        match_note = f" Matched {n_match} of {n_total} animal ids to your GPS data."
    else:
        match_note = f" All {n_total} animal ids matched your GPS data."

    msg_fn = _ok_alert if (processed_animal_ids is None or n_match > 0) else _err_alert
    msg = msg_fn(
        f"Imported {n_rows} animal-year row(s) — {n_seq} with migration sequences. "
        f"Bio-year start set to {bio_month}/{bio_day}.{match_note} Open Tab 2 to review."
    )
    return _df_to_json(migtime, "migtime"), notes_store, bio_month, bio_day, msg


@app.callback(
    Output("seq-animal-dropdown", "value", allow_duplicate=True),
    Output("store-animal-index", "data"),
    Output("seq-progress", "children"),
    Input("btn-prev-animal", "n_clicks"),
    Input("btn-next-animal", "n_clicks"),
    State("seq-animal-dropdown", "options"),
    State("seq-animal-dropdown", "value"),
    prevent_initial_call=True,
)
def navigate_animals(prev_clicks, next_clicks, options, current_value):
    if not options:
        raise PreventUpdate

    values = [o["value"] for o in options]
    try:
        idx = values.index(current_value)
    except ValueError:
        idx = 0

    triggered = ctx.triggered_id
    if triggered == "btn-prev-animal":
        idx = max(0, idx - 1)
    elif triggered == "btn-next-animal":
        idx = min(len(values) - 1, idx + 1)

    value = values[idx]
    if idx + 1 == len(values):
        progress_text = (
            f"Reviewed {idx + 1} of {len(values)} animals — all animals reviewed. "
            "Export the updated migtime table, then move to Tab 3 to run models."
        )
    else:
        progress_text = f"Reviewed {idx + 1} of {len(values)} animals"
    return value, idx, progress_text


# ---------------------------------------------------------------------------
# Sync range sliders ↔ date inputs (slider drag updates date fields)
#
# Two related callbacks here use Dash's pattern-matching ids:
#   - slider_to_dates  uses MATCH — one slider's value → THAT slider's
#     start/end date inputs. Pure 1:1 per-card sync.
#   - slider_to_migtime uses ALL — receives EVERY slider's value/id; uses
#     ctx.triggered_id to figure out which one fired and writes only that
#     slot into the singleton migtime store.
# ---------------------------------------------------------------------------

@app.callback(
    Output({"type": "seq-start", "index": dash.MATCH}, "value"),
    Output({"type": "seq-end", "index": dash.MATCH}, "value"),
    Input({"type": "seq-range-slider", "index": dash.MATCH}, "value"),
    State("store-slider-date-min", "data"),
    prevent_initial_call=True,
)
def slider_to_dates(slider_val, date_min_iso):
    if not slider_val or not date_min_iso:
        raise PreventUpdate
    date_min = pd.Timestamp(date_min_iso)
    start = (date_min + pd.Timedelta(days=slider_val[0])).strftime("%Y-%m-%d")
    end = (date_min + pd.Timedelta(days=slider_val[1])).strftime("%Y-%m-%d")
    return start, end


@app.callback(
    Output("store-migtime-table", "data", allow_duplicate=True),
    Input({"type": "seq-range-slider", "index": dash.ALL}, "value"),
    State({"type": "seq-range-slider", "index": dash.ALL}, "id"),
    State("seq-animal-dropdown", "value"),
    State("store-migtime-table", "data"),
    State("store-slider-date-min", "data"),
    prevent_initial_call=True,
)
def slider_to_migtime(slider_values, slider_ids, selected_animal, migtime_json, date_min_iso):
    """Push slider value changes for the current animal into the migtime store
    so the map repaints live as the user drags either handle — or the middle —
    of any sequence slider. Empty slots (start == end) write blank dates.

    Dash forbids per-slider MATCH wildcards on Inputs/State when the Output is
    a singleton store, so this callback receives every slider's value and id
    and uses ctx.triggered_id to figure out which one actually changed.
    """
    if not selected_animal or not date_min_iso or not migtime_json:
        raise PreventUpdate
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        raise PreventUpdate
    seq_name = triggered.get("index", "")
    if not seq_name or not seq_name.startswith("mig"):
        raise PreventUpdate
    # Find the value list entry that corresponds to the slider that fired.
    slider_val = None
    for sid, sval in zip(slider_ids, slider_values):
        if isinstance(sid, dict) and sid.get("index") == seq_name:
            slider_val = sval
            break
    if not slider_val:
        raise PreventUpdate
    try:
        slot = int(seq_name[3:])
    except ValueError:
        raise PreventUpdate
    if not (1 <= slot <= 8):
        raise PreventUpdate

    date_min = pd.Timestamp(date_min_iso)
    if int(slider_val[0]) == int(slider_val[1]):
        start, end = "", ""
    else:
        start = (date_min + pd.Timedelta(days=int(slider_val[0]))).strftime("%Y-%m-%d")
        end = (date_min + pd.Timedelta(days=int(slider_val[1]))).strftime("%Y-%m-%d")

    migtime = _json_to_df(migtime_json, "migtime")
    if "id_bio_year" not in migtime.columns:
        raise PreventUpdate
    mask = migtime["id_bio_year"] == selected_animal
    sk, ek = f"mig{slot}_start", f"mig{slot}_end"
    if sk not in migtime.columns:
        migtime[sk] = ""
    if ek not in migtime.columns:
        migtime[ek] = ""
    if not mask.any():
        animal_id_part = "_".join(selected_animal.rsplit("_", 1)[:-1]) if "_" in selected_animal else selected_animal
        bio_year_part = selected_animal.rsplit("_", 1)[-1] if "_" in selected_animal else ""
        new_row = {c: "" for c in migtime.columns}
        new_row["id_bio_year"] = selected_animal
        new_row["animal_id"] = animal_id_part
        new_row["bio_year"] = bio_year_part
        new_row["bio_year_full"] = bio_year_part
        migtime = pd.concat([migtime, pd.DataFrame([new_row])], ignore_index=True)
        mask = migtime["id_bio_year"] == selected_animal
    # No-op short-circuit: avoid an unnecessary repaint when the slider value
    # already matches what's in the migtime (e.g. on initial render).
    current_start = str(migtime.loc[mask, sk].iloc[0])
    current_end = str(migtime.loc[mask, ek].iloc[0])
    if current_start == start and current_end == end:
        raise PreventUpdate
    migtime.loc[mask, sk] = start
    migtime.loc[mask, ek] = end
    # Dragging a slider counts as the user opting back in to defining
    # sequences for this animal, so flip the sticky "Clear Sequences" flag
    # off if it was on. No-op when the flag was already False / absent.
    if "seq_cleared" in migtime.columns:
        migtime.loc[mask, "seq_cleared"] = False
    return _df_to_json(migtime, "migtime")


# ---------------------------------------------------------------------------
# Basemap toggle — swap tile URL without re-rendering map
# ---------------------------------------------------------------------------
# Basemap toggle is now handled by clientside callback → postMessage to iframe


# ---------------------------------------------------------------------------
# Pre-compute per-animal map data at process time and cache it.
# The map callback just looks up the cache — instant.
# ---------------------------------------------------------------------------

def _build_animal_map_entry(grp: pd.DataFrame) -> dict | None:
    """Build the cached map data for a single animal-year (`grp` is the
    per-(id_bio_year) slice of the processed DataFrame). Returns ``None`` if
    the slice has no usable lon/lat rows. Pure function — caller owns the
    decision of where to stash the result."""
    grp = grp.dropna(subset=["lon", "lat"])
    if "timestamp" in grp.columns:
        if not pd.api.types.is_datetime64_any_dtype(grp["timestamp"]):
            grp = grp.assign(timestamp=pd.to_datetime(grp["timestamp"], errors="coerce"))
        grp = grp.sort_values("timestamp")
    if grp.empty:
        return None

    lon = np.round(grp["lon"].values, 5)
    lat = np.round(grp["lat"].values, 5)
    n = len(grp)

    ts_iso = grp["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S").values if "timestamp" in grp.columns else np.full(n, "")
    ts_ns = grp["timestamp"].values if "timestamp" in grp.columns else None

    # Subsample the track line to ~3000 vertices max. At ~5-arcsec rounded
    # coords the visual difference is invisible on the browser canvas but the
    # payload size drops by 10-100x for high-fix-rate herds (12 fixes/day
    # animals can have 50k+ points/year).
    #
    # Skip flagged fixes in the line geometry so the track reads A→C when B
    # has been excised — matching the analysis-side filter in
    # sequencing.extract_sequences. Flagged points still render as ghost dots
    # via the points layer.
    line_problem = (
        grp["problem"].fillna(0).astype(int).to_numpy()
        if "problem" in grp.columns else np.zeros(n, dtype=int)
    )
    line_mortality = (
        grp["mortality_flag"].fillna(0).astype(int).to_numpy()
        if "mortality_flag" in grp.columns else np.zeros(n, dtype=int)
    )
    keep_line = (line_problem == 0) & (line_mortality == 0)
    lon_line = lon[keep_line]
    lat_line = lat[keep_line]
    step_line = max(1, len(lon_line) // 3000)
    line_coords = np.column_stack([lon_line[::step_line], lat_line[::step_line]]).tolist()
    line_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": line_coords},
            "properties": {},
        }] if len(line_coords) > 1 else [],
    }

    # Auto-zoom heuristic: degrees-of-span → MapLibre zoom level. Empirical
    # values picked so a herd's full range fits with a small margin at zoom
    # N. Tighter spans get more zoom; >3° defaults to 6 (statewide).
    ctr = [float(np.mean(lat)), float(np.mean(lon))]
    span = max(float(np.ptp(lat)), float(np.ptp(lon)))
    zoom = 12 if span < 0.05 else 11 if span < 0.2 else 9 if span < 0.5 else 8 if span < 1 else 7 if span < 3 else 6

    env_vars = {}
    for vc in AVAILABLE_VARIABLES:
        if vc in grp.columns:
            env_vars[vc] = np.round(grp[vc].values.astype(float), 4)
    wld_col_names = {name for (name, _label, _grp) in WLD_COLUMNS.values()}
    for vc in wld_col_names:
        if vc in grp.columns and vc not in env_vars:
            try:
                env_vars[vc] = np.round(grp[vc].values.astype(float), 4)
            except (TypeError, ValueError):
                pass

    problem_arr = (
        grp["problem"].fillna(0).astype(int).to_numpy()
        if "problem" in grp.columns else np.zeros(n, dtype=int)
    )
    mortality_arr = (
        grp["mortality_flag"].fillna(0).astype(int).to_numpy()
        if "mortality_flag" in grp.columns else np.zeros(n, dtype=int)
    )
    problem_reason_arr = (
        grp["problem_reason"].fillna("").astype(str).tolist()
        if "problem_reason" in grp.columns else [""] * n
    )
    mortality_reason_arr = (
        grp["mortality_reason"].fillna("").astype(str).tolist()
        if "mortality_reason" in grp.columns else [""] * n
    )

    return {
        "center": ctr,
        "zoom": zoom,
        "lon": lon,
        "lat": lat,
        "ts_iso": ts_iso,
        "ts_ns": ts_ns,
        "line_geojson": line_geojson,
        "env_vars": env_vars,
        "problem": problem_arr,
        "mortality": mortality_arr,
        "problem_reason": problem_reason_arr,
        "mortality_reason": mortality_reason_arr,
    }


def _precompute_animal_maps(df: pd.DataFrame):
    """Build and cache GeoJSON for *every* animal-year. Kept for callers who
    really want it (e.g. a future "warm cache" admin button), but the Tab 1
    and Load-Project paths now build entries lazily on demand via
    :func:`_ensure_animal_map_entry`."""
    _MAP_CACHE.clear()
    if "id_bio_year" not in df.columns or "lon" not in df.columns:
        return
    if "timestamp" in df.columns:
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for animal_key, grp in df.groupby("id_bio_year"):
        entry = _build_animal_map_entry(grp)
        if entry is not None:
            _MAP_CACHE[animal_key] = entry


def _ensure_animal_map_entry(df: pd.DataFrame, animal_key: str) -> bool:
    """Build the map cache entry for *one* animal-year if it isn't already
    cached. Returns True if an entry now exists for ``animal_key``.

    This is the hot path for Tab 2 navigation — building one animal's
    arrays is O(seq length) and fast; building all of them up front is the
    chunk that was pushing Tab 1's HTTP request past the browser timeout.
    """
    if animal_key in _MAP_CACHE:
        return True
    if "id_bio_year" not in df.columns or "lon" not in df.columns:
        return False
    grp = df[df["id_bio_year"] == animal_key]
    if grp.empty:
        return False
    entry = _build_animal_map_entry(grp)
    if entry is None:
        return False
    _MAP_CACHE[animal_key] = entry
    return True


def _build_point_geojson(cache_entry, migtime_json=None, animal_key=None):
    """Build colored point GeoJSON from cached arrays. Fast — no DataFrame ops."""
    lon = cache_entry["lon"]
    lat = cache_entry["lat"]
    ts_ns = cache_entry["ts_ns"]
    ts_iso = cache_entry["ts_iso"]
    n = len(lon)

    # Default: black for unassigned points (only points falling inside a
    # migration window in the migtime table get a per-sequence color below).
    colors = np.full(n, "#000000", dtype=object)
    # Shared with the NSD chart bands + slider cards so a sequence's colour is
    # identical on the map and in the chart.
    seq_palette = SEQ_COLORS

    if migtime_json and ts_ns is not None and animal_key:
        try:
            mt = _json_to_df(migtime_json, "migtime")
            rows = mt.loc[mt["id_bio_year"] == animal_key]
            if not rows.empty:
                r = rows.iloc[0]
                ts_compare = ts_ns.astype("datetime64[ns]")
                for i in range(1, 9):
                    sk, ek = f"mig{i}_start", f"mig{i}_end"
                    if sk in r and ek in r and pd.notna(r[sk]) and str(r[sk]) not in ("", "NaT", "nan", "None"):
                        s = pd.Timestamp(r[sk])
                        e = pd.Timestamp(r[ek]) if pd.notna(r[ek]) and str(r[ek]) not in ("", "NaT", "nan", "None") else s
                        if s != e:
                            s_ns = np.datetime64(s, "ns")
                            e_ns = np.datetime64(e, "ns")
                            mask = (ts_compare >= s_ns) & (ts_compare <= e_ns)
                            colors[mask] = seq_palette[(i - 1) % len(seq_palette)]
        except Exception:
            import traceback
            print(f"[map-color] Error coloring points for {animal_key}: {traceback.format_exc()}")

    env_vars = cache_entry.get("env_vars", {})
    problem_arr = cache_entry.get("problem", np.zeros(n, dtype=int))
    mortality_arr = cache_entry.get("mortality", np.zeros(n, dtype=int))
    problem_reason = cache_entry.get("problem_reason", [""] * n)
    mortality_reason = cache_entry.get("mortality_reason", [""] * n)

    # Subsample points for the browser
    step = max(1, n // 3000)
    idx = np.arange(0, n, step)

    features = []
    for i in idx:
        if int(mortality_arr[i]) == 1:
            flag = "mortality"
        elif int(problem_arr[i]) == 1:
            flag = "problem"
        else:
            flag = ""
        props = {"c": colors[i], "d": ts_iso[i], "f": flag}
        if problem_reason[i]:
            props["pr"] = problem_reason[i]
        if mortality_reason[i]:
            props["mr"] = mortality_reason[i]
        for vk, varr in env_vars.items():
            v = varr[i]
            if np.isfinite(v):
                props[vk] = float(v)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon[i]), float(lat[i])]},
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Update map — build payload, push to iframe via clientside callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("store-map-payload", "data"),
    Output("crosses-road-badge", "children"),
    Output("crosses-road-badge", "style"),
    Output("crosses-highway-badge", "children"),
    Output("crosses-highway-badge", "style"),
    Output("animal-notes", "value"),
    Output("animal-classification", "value"),
    Input("seq-animal-dropdown", "value"),
    Input("store-migtime-table", "data"),
    State("store-processed-data", "data"),
    State("store-animal-notes", "data"),
    State("store-animal-classification", "data"),
    State("store-road-crossings", "data"),
    State("store-wld-env-labels", "data"),
    State("seq-bio-year-month", "value"),
    State("seq-bio-year-day", "value"),
    prevent_initial_call=True,
)
def update_seq_map(selected_animal, migtime_json, processed_json, notes_store, class_store, road_store, wld_labels, bio_month, bio_day):
    if not selected_animal:
        raise PreventUpdate

    global _MAP_CACHE_BIO_KEY
    bio_month = int(bio_month or 2)
    bio_day = int(bio_day or 1)
    bio_key = (bio_month, bio_day)

    # If the bio-year start changed since the cache was built, wipe it — the
    # cache keys are id_bio_year strings that depend on bio_month/day, so
    # they're stale now.
    if _MAP_CACHE_BIO_KEY is not None and _MAP_CACHE_BIO_KEY != bio_key:
        _MAP_CACHE.clear()
    _MAP_CACHE_BIO_KEY = bio_key

    # Lazily ensure a cache entry for the selected animal exists, with
    # id_bio_year recomputed from the current UI bio_month/day.
    if selected_animal not in _MAP_CACHE:
        if not processed_json:
            raise PreventUpdate
        df = _json_to_df(processed_json, "processed")
        if "timestamp" in df.columns and "animal_id" in df.columns:
            df = df.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            month_ = df["timestamp"].dt.month.to_numpy(dtype=int)
            day_ = df["timestamp"].dt.day.to_numpy(dtype=int)
            year_ = df["timestamp"].dt.year.to_numpy(dtype=int)
            before_start = (month_ < bio_month) | ((month_ == bio_month) & (day_ < bio_day))
            bio_year_arr = np.where(before_start, year_ - 1, year_)
            df["id_bio_year"] = df["animal_id"].astype(str) + "_" + bio_year_arr.astype(str)
        if not _ensure_animal_map_entry(df, selected_animal):
            raise PreventUpdate

    entry = _MAP_CACHE[selected_animal]
    points_geojson = _build_point_geojson(entry, migtime_json, selected_animal)

    # Build combined label dict for the popup: raster vars + any merged WLD vars
    env_labels = dict(AVAILABLE_VARIABLES)
    if wld_labels:
        env_labels.update(wld_labels)

    map_payload = {
        "type": "update-data",
        "center": entry["center"],
        "zoom": entry["zoom"],
        "points": points_geojson,
        "line": entry["line_geojson"],
        "env_labels": env_labels,
    }

    # Road crossings — use cached results or compute
    road_store = road_store or {}
    if selected_animal in road_store:
        rc = road_store[selected_animal]
    else:
        rc = {"crosses_road": False, "crosses_highway": False}

    road_yes = {"fontSize": "0.8rem", "backgroundColor": "#e63946", "color": "#fff"}
    road_no = {"fontSize": "0.8rem", "backgroundColor": "#2a9d8f", "color": "#fff"}

    road_text = "Yes" if rc.get("crosses_road") else "No"
    road_style = road_yes if rc.get("crosses_road") else road_no
    hwy_text = "Yes" if rc.get("crosses_highway") else "No"
    hwy_style = road_yes if rc.get("crosses_highway") else road_no

    # Notes — load from store
    notes_store = notes_store or {}
    current_notes = notes_store.get(selected_animal, "")

    # Classification radio — reflect the stored value for this animal-year.
    class_store = class_store or {}
    current_class = class_store.get(selected_animal)

    return map_payload, road_text, road_style, hwy_text, hwy_style, current_notes, current_class


# Clientside callback: push map payload to iframe via postMessage.
# Server-side update_seq_map writes the payload into store-map-payload; this
# clientside listener picks it up in the browser and forwards it to the
# MapLibre iframe (which is same-origin but isolated by iframe scope). The
# Output is a throwaway — we don't actually want to update map-click-info,
# we just need a valid Output declaration to attach the side-effect to.
app.clientside_callback(
    """
    function(payload) {
        if (!payload) return window.dash_clientside.no_update;
        var iframe = document.getElementById('seq-map-iframe');
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage(payload, '*');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("map-click-info", "children"),
    Input("store-map-payload", "data"),
    prevent_initial_call=True,
)

# Basemap toggle → postMessage to iframe
app.clientside_callback(
    """
    function(basemap) {
        var iframe = document.getElementById('seq-map-iframe');
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage({type: 'set-basemap', basemap: basemap}, '*');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("seq-basemap-toggle", "value", allow_duplicate=True),
    Input("seq-basemap-toggle", "value"),
    prevent_initial_call=True,
)


# Click on a point in the NSD chart → flash the matching fix on the map.
# The plot's x-axis is timestamp, so clickData.points[0].x is the ISO string
# we send to the iframe. Iframe finds the GeoJSON feature whose properties.d
# matches and pulses a cyan halo for ~1.6 s.
app.clientside_callback(
    """
    function(clickData) {
        if (!clickData || !clickData.points || !clickData.points.length) {
            return window.dash_clientside.no_update;
        }
        var raw = clickData.points[0].x;
        if (raw === undefined || raw === null) return window.dash_clientside.no_update;
        // Plotly returns x as either an ISO string or a JS-Date-parseable form.
        // The map keys points by "YYYY-MM-DD HH:MM:SS" (built in
        // _build_animal_map_entry), so normalise to that.
        var d;
        try {
            var dt = new Date(raw);
            if (isNaN(dt.getTime())) {
                d = String(raw).replace('T', ' ').slice(0, 19);
            } else {
                var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
                d = dt.getUTCFullYear() + '-' + pad(dt.getUTCMonth() + 1) + '-' + pad(dt.getUTCDate())
                  + ' ' + pad(dt.getUTCHours()) + ':' + pad(dt.getUTCMinutes()) + ':' + pad(dt.getUTCSeconds());
            }
        } catch (e) {
            d = String(raw).replace('T', ' ').slice(0, 19);
        }
        var iframe = document.getElementById('seq-map-iframe');
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage({type: 'flash-point', d: d}, '*');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("nsd-plot", "clickData", allow_duplicate=True),
    Input("nsd-plot", "clickData"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Notes — save per animal
# ---------------------------------------------------------------------------

@app.callback(
    Output("store-animal-notes", "data"),
    Output("notes-save-status", "children"),
    Input("animal-notes", "value"),
    State("seq-animal-dropdown", "value"),
    State("store-animal-notes", "data"),
    prevent_initial_call=True,
)
def autosave_animal_notes(notes_text, animal_key, notes_store):
    """Auto-save the Notes box (there is no manual save button). The textarea
    has debounce=800, so this fires ~0.8 s after the user stops typing and
    immediately on blur / animal navigation — not on every keystroke. Keyed by
    the animal-year that was selected when the text was committed.

    The blur fires before the click that navigates away, so State here still
    holds the OLD animal when you type-then-navigate: the edit lands on the
    right row. The no-op guard skips the redundant write that update_seq_map's
    programmatic reload would otherwise trigger when you switch animals (and
    keeps us from touching disk when nothing actually changed)."""
    if not animal_key:
        raise PreventUpdate
    notes_store = notes_store or {}
    new_val = notes_text or ""
    if notes_store.get(animal_key, "") == new_val:
        raise PreventUpdate
    notes_store[animal_key] = new_val
    _save_notes(notes_store)
    return notes_store, html.Small("✓ Saved", className="text-success")


# ---------------------------------------------------------------------------
# Movement classification — Resident / Nomadic / Migratory radio. Picking one
# auto-populates the Notes textarea (canonical sentence + crossing phrase) and
# persists both the classification and the generated note. Resident/Nomadic
# animal-years are dropped from the analysis on "Export Updated Table".
# ---------------------------------------------------------------------------

@app.callback(
    Output("animal-notes", "value", allow_duplicate=True),
    Output("store-animal-notes", "data", allow_duplicate=True),
    Output("store-animal-classification", "data"),
    Output("notes-save-status", "children", allow_duplicate=True),
    Input("animal-classification", "value"),
    State("seq-animal-dropdown", "value"),
    State("store-animal-classification", "data"),
    State("store-animal-notes", "data"),
    State("store-road-crossings", "data"),
    prevent_initial_call=True,
)
def apply_classification(classification, animal_key, class_store, notes_store, road_store):
    if not animal_key:
        raise PreventUpdate
    class_store = class_store or {}
    # The radio is also set programmatically when navigating animals
    # (update_seq_map). Those round-trips re-fire this Input with the value
    # we just loaded — detect that (unchanged value) and do nothing so we
    # don't clobber the user's free-text notes on every animal switch.
    if classification == class_store.get(animal_key):
        raise PreventUpdate

    notes_store = notes_store or {}
    road_store = road_store or {}

    if classification:
        class_store[animal_key] = classification
    else:
        class_store.pop(animal_key, None)
    _save_classifications(class_store)

    rc = road_store.get(animal_key, {}) or {}
    note_text = _classification_note(
        classification,
        bool(rc.get("crosses_road", False)),
        bool(rc.get("crosses_highway", False)),
    )
    notes_store[animal_key] = note_text
    _save_notes(notes_store)

    label = (classification or "cleared").capitalize()
    return note_text, notes_store, class_store, _ok_alert(f"Classified as {label}.")


@app.callback(
    Output("animal-classification", "value", allow_duplicate=True),
    Output("store-animal-classification", "data", allow_duplicate=True),
    Output("animal-notes", "value", allow_duplicate=True),
    Output("store-animal-notes", "data", allow_duplicate=True),
    Output("notes-save-status", "children", allow_duplicate=True),
    Input("btn-unclassify", "n_clicks"),
    State("seq-animal-dropdown", "value"),
    State("store-animal-classification", "data"),
    State("store-animal-notes", "data"),
    prevent_initial_call=True,
)
def unclassify_animal(n_clicks, animal_key, class_store, notes_store):
    """Clear the classification for the selected animal-year: reset the radio,
    drop the stored classification, and wipe the auto-generated Notes text so
    it doesn't leave a stale 'Resident…' sentence behind."""
    if not animal_key:
        raise PreventUpdate
    class_store = class_store or {}
    notes_store = notes_store or {}
    class_store.pop(animal_key, None)
    _save_classifications(class_store)
    notes_store[animal_key] = ""
    _save_notes(notes_store)
    return None, class_store, "", notes_store, _ok_alert("Classification cleared.")


# ---------------------------------------------------------------------------
# Tab 2 selection bridge + flag actions
# ---------------------------------------------------------------------------

# Selection counter (driven by the JS bridge in assets/map_functions.js which
# writes selection-changed postMessages into store-tab2-selection).
@app.callback(
    Output("seq-selection-count", "children"),
    Input("store-tab2-selection", "data"),
)
def update_seq_selection_count(sel):
    n = len(sel or [])
    return f"{n} selected"


# Clear Selection button → tell the iframe to drop its local selection set.
# That triggers a selection-changed (empty) postMessage back to the parent,
# which clears store-tab2-selection through the same bridge.
app.clientside_callback(
    """
    function(n) {
        if (!n) return window.dash_clientside.no_update;
        var iframe = document.getElementById('seq-map-iframe');
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage({type: 'clear-selection'}, '*');
        }
        return '';
    }
    """,
    Output("seq-flag-status", "children", allow_duplicate=True),
    Input("btn-clear-selection", "n_clicks"),
    prevent_initial_call=True,
)


def _apply_flag_to_selection(
    selection: list,
    animal_key: str | None,
    processed_json: str | None,
    flag_kind: str,
    config_json: str | None = None,
) -> tuple[str | None, dict | None, dbc.Alert]:
    """Shared core of Flag-as-Problem / Flag-as-Mortality / Unflag callbacks.

    Returns ``(new_processed_json, new_map_payload, status_alert)``.

    `flag_kind` is one of:
      - "problem"    → set problem=1, mortality_flag=0 on selected rows
      - "mortality"  → set mortality_flag=1, problem=0
      - "clear"      → set both to 0
    """
    if not animal_key:
        return None, None, _err_alert("Pick an animal-year first.")
    if not selection:
        return None, None, _err_alert("No points selected. Click points on the map first.")
    if not processed_json:
        return None, None, _err_alert("No processed data loaded.")

    # Parse the (animal_id, bio_year) pair out of the dropdown key.
    parts = str(animal_key).rsplit("_", 1)
    if len(parts) != 2:
        return None, None, _err_alert(f"Could not parse animal_key '{animal_key}'.")
    animal_id_part, _bio_year_part = parts

    df = _json_to_df(processed_json, "processed")
    if "animal_id" not in df.columns or "timestamp" not in df.columns:
        return None, None, _err_alert("Processed data is missing animal_id / timestamp columns.")

    # Normalise the timestamp column to ensure consistent string matching.
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    ts_strings = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    selection_set = set(str(s) for s in selection)
    mask = (df["animal_id"].astype(str) == animal_id_part) & ts_strings.isin(selection_set)
    n_matched = int(mask.sum())
    if n_matched == 0:
        return None, None, _err_alert(
            f"None of the {len(selection)} selected timestamps matched fixes for {animal_id_part}."
        )

    if "problem" not in df.columns:
        df["problem"] = 0
    if "mortality_flag" not in df.columns:
        df["mortality_flag"] = 0

    if flag_kind == "problem":
        df.loc[mask, "problem"] = 1
        df.loc[mask, "mortality_flag"] = 0
        verb = "flagged as problem"
    elif flag_kind == "mortality":
        # Mortality is terminal: once the animal dies, every subsequent fix
        # for *this animal* (across all bio years) should be excluded from
        # analysis. Find the earliest timestamp the user selected on this
        # animal, then expand the mask forward in time.
        earliest_death = df.loc[mask, "timestamp"].min()
        terminal_mask = (
            (df["animal_id"].astype(str) == animal_id_part)
            & (df["timestamp"] >= earliest_death)
        )
        df.loc[terminal_mask, "mortality_flag"] = 1
        df.loc[terminal_mask, "problem"] = 0
        n_matched = int(terminal_mask.sum())
        verb = f"flagged as mortality (from {earliest_death.strftime('%Y-%m-%d %H:%M')} onward)"
    elif flag_kind == "clear":
        df.loc[mask, "problem"] = 0
        df.loc[mask, "mortality_flag"] = 0
        verb = "unflagged"
    else:
        return None, None, _err_alert(f"Unknown flag kind '{flag_kind}'.")

    # Push back to the in-process caches so downstream callbacks see fresh data.
    new_json = _df_to_json(df, "processed")
    # Only rebuild the map cache for the animal we actually edited — rebuilding
    # every animal on every flag toggle made the action feel like "nothing
    # happened" because of the multi-second hang on large herds.
    try:
        sub = df[df["id_bio_year"].astype(str) == str(animal_key)]
        entry = _build_animal_map_entry(sub)
        if entry is not None:
            _MAP_CACHE[animal_key] = entry
    except Exception as cache_exc:
        print(f"WARNING: per-animal map cache rebuild failed: {cache_exc}")

    # Disk persistence (project parquet + workdir parquet + FlagsRemoved.gpkg)
    # is now deferred to "Export Updated Table" so individual flag clicks stay
    # snappy. The in-memory `store-processed-data` payload returned below is
    # what every downstream callback reads, so the UI sees the new flag state
    # immediately even though nothing is written to disk yet.
    _log_action(
        "USER_FLAG",
        kind=flag_kind,
        animal=animal_key,
        n_matched=n_matched,
        n_selected=len(selection),
        persisted=False,
    )

    # Rebuild the map payload for this animal so the UI shows the new
    # outline colors immediately.
    map_payload = None
    if animal_key in _MAP_CACHE:
        entry = _MAP_CACHE[animal_key]
        env_labels = dict(AVAILABLE_VARIABLES)
        map_payload = {
            "type": "update-data",
            "center": entry["center"],
            "zoom": entry["zoom"],
            "points": _build_point_geojson(entry, None, animal_key),
            "line": entry["line_geojson"],
            "env_labels": env_labels,
        }

    return new_json, map_payload, _ok_alert(
        f"{n_matched} point(s) {verb} for {animal_id_part}."
    )


@app.callback(
    Output("store-processed-data", "data", allow_duplicate=True),
    Output("store-map-payload", "data", allow_duplicate=True),
    Output("seq-flag-status", "children", allow_duplicate=True),
    Input("btn-flag-problem", "n_clicks"),
    State("store-tab2-selection", "data"),
    State("seq-animal-dropdown", "value"),
    State("store-processed-data", "data"),
    State("store-config", "data"),
    prevent_initial_call=True,
)
def flag_selected_problem(n_clicks, selection, animal_key, processed_json, config_json):
    new_json, payload, alert = _apply_flag_to_selection(
        selection, animal_key, processed_json, "problem", config_json,
    )
    if new_json is None:
        return dash.no_update, dash.no_update, alert
    return new_json, payload, alert


@app.callback(
    Output("store-processed-data", "data", allow_duplicate=True),
    Output("store-map-payload", "data", allow_duplicate=True),
    Output("seq-flag-status", "children", allow_duplicate=True),
    Input("btn-flag-mortality", "n_clicks"),
    State("store-tab2-selection", "data"),
    State("seq-animal-dropdown", "value"),
    State("store-processed-data", "data"),
    State("store-config", "data"),
    prevent_initial_call=True,
)
def flag_selected_mortality(n_clicks, selection, animal_key, processed_json, config_json):
    new_json, payload, alert = _apply_flag_to_selection(
        selection, animal_key, processed_json, "mortality", config_json,
    )
    if new_json is None:
        return dash.no_update, dash.no_update, alert
    return new_json, payload, alert


@app.callback(
    Output("store-processed-data", "data", allow_duplicate=True),
    Output("store-map-payload", "data", allow_duplicate=True),
    Output("seq-flag-status", "children", allow_duplicate=True),
    Input("btn-unflag", "n_clicks"),
    State("store-tab2-selection", "data"),
    State("seq-animal-dropdown", "value"),
    State("store-processed-data", "data"),
    State("store-config", "data"),
    prevent_initial_call=True,
)
def unflag_selected(n_clicks, selection, animal_key, processed_json, config_json):
    new_json, payload, alert = _apply_flag_to_selection(
        selection, animal_key, processed_json, "clear", config_json,
    )
    if new_json is None:
        return dash.no_update, dash.no_update, alert
    return new_json, payload, alert


# ===========================================================================
# Callbacks — Tab 3: Modeling
# ===========================================================================

# Show the progress-bar wrapper only while a model run is in flight.
# Visibility is purely clientside (no server round-trip): button click shows
# it, and the value update that lands when run_modeling returns hides it.
app.clientside_callback(
    """
    function(date_min_iso) {
        window._sliderDateMin = date_min_iso || null;
        return window.dash_clientside.no_update;
    }
    """,
    Output("store-slider-date-min", "data", allow_duplicate=True),
    Input("store-slider-date-min", "data"),
    prevent_initial_call=True,
)


app.clientside_callback(
    """
    function(n_clicks, progress_value) {
        const ctx = window.dash_clientside.callback_context;
        if (!ctx || !ctx.triggered || ctx.triggered.length === 0) {
            return window.dash_clientside.no_update;
        }
        const id = ctx.triggered[0].prop_id.split('.')[0];
        if (id === 'btn-run-models') {
            return {'display': 'block'};
        }
        // The server callback fires with progress=100 (or 0 on early-exit)
        // when modelling completes. Either way, hide.
        return {'display': 'none'};
    }
    """,
    Output("model-progress-wrapper", "style"),
    Input("btn-run-models", "n_clicks"),
    Input("model-progress", "value"),
    prevent_initial_call=True,
)


@app.callback(
    Output("model-param-panel", "children"),
    Output("model-auto-logic", "children"),
    Input("model-select", "value"),
    State("store-processed-data", "data"),
    prevent_initial_call=False,
)
def render_model_params(model, processed_json):
    """Render dynamic parameter panel based on selected model."""
    auto_logic = ""

    # Check fix rate from data for auto-logic hints
    fix_rate_msg = ""
    if processed_json:
        try:
            df = _json_to_df(processed_json, "processed")
            if "fix_rate_hours" in df.columns:
                median_fr = df["fix_rate_hours"].median()
                if median_fr > 12:
                    fix_rate_msg = f"Fix rate > 12h detected ({median_fr:.1f}h median): BMVar auto-set to 1000"
        except Exception:
            pass

    if model == "BBMM":
        auto_logic = fix_rate_msg or "Fix rate ≤ 12h: BMVar will be estimated automatically"
        panel = [
            _info_label("Fixed Motion Variance (FMV, a.k.a. Brownian motion variance or BMVar)",
                       "When FMV is left blank, the app uses Maximum Likelihood Estimation following "
                       "Horne et al. (2007). This means that for each interior triplet of GPS fixes "
                       "(i, i+1, i+2) where both segments fall within the max lag, it computes the "
                       "residual of the middle point from the straight-line interpolation between the "
                       "outer two. Under the Brownian bridge model, that residual is the bivariate "
                       "normal with variance that depends on the motion variance, the time lags, and "
                       "the location error. The function optimizes the motion variance by minimizing "
                       "the negative log-likelihood across all valid triplets — this is the same "
                       "approach as R's BBMM::brownian.motion.variance().\n\n"
                       "For datasets with a median fix rate above 5–7 hours, estimated variance is "
                       "not recommended. For coarse fix-rate datasets, it is recommended to input a "
                       "FMV value of 1400 m² for elk and 1000 m² for deer.",
                       "1400 elk; 1000 deer"),
            dbc.InputGroup(
                [
                    dbc.Input(id={"type": "model-param", "key": "bbmm_bmvar"}, type="number", placeholder="Auto (estimate)", min=0),
                    dbc.InputGroupText("m²"),
                ],
                className="mb-1",
            ),
            html.Small(
                "Leave blank to estimate motion variance from the data. Enter a number to force a "
                "specific fixed motion variance across the data; the latter is the more common option "
                "among high fix-rate datasets (e.g., over 5 hours between fixes). "
                "Recommended: 1000 for deer/bighorn, 1400 for elk.",
                className="text-muted d-block mb-2", style={"fontSize": "0.7rem"},
            ),
            html.Div([
                dbc.Checkbox(
                    id={"type": "model-param", "key": "bbmm_bmvar_conditional"},
                    label="Conditional FMV by fix-rate threshold",
                    value=False,
                    style={"fontSize": "0.8rem", "display": "inline-block"},
                ),
                _info_label("",
                            "When this box is checked, the model will calculate the median time gap between "
                            "consecutive fixes in each sequence and will either use the fixed motion variance "
                            "entered above or estimate the variance for that sequence, based on whether the "
                            "median gap is above or below the threshold (hours between points).\n\n"
                            "For example, if a sequence has a median gap of 4 hours and the threshold is set "
                            "to 5, the variance for that sequence will be estimated using maximum likelihood "
                            "estimation. If a sequence has a median gap of 6 hours (above the threshold), it "
                            "will use the fixed motion variance value entered above for that sequence.",
                            "3 hours between points for elk, 5 hours between points for deer"),
            ], className="d-flex align-items-center mb-1"),
            dbc.InputGroup(
                [
                    dbc.Input(
                        id={"type": "model-param", "key": "bbmm_bmvar_threshold"},
                        type="number", value=5, min=0, step=0.5,
                        placeholder="Threshold",
                    ),
                    dbc.InputGroupText("hrs between points"),
                ],
                className="mb-1",
            ),
            _info_label("Location Error (m)",
                       "GPS measurement error in meters. Accounts for positional inaccuracy of the collar.",
                       "20 m"),
            dbc.Input(id={"type": "model-param", "key": "bbmm_loc_error"}, type="number", value=20, min=0, className="mb-2"),
            _info_label("Max Lag (hours)",
                       "Maximum time gap (in hours) between consecutive fixes before the segment is treated "
                       "as a break. Gaps larger than this are excluded from variance estimation.",
                       "27 hours"),
            dbc.Input(id={"type": "model-param", "key": "bbmm_max_lag"}, type="number", value=27, min=0, className="mb-2"),
            _info_label("Time Step (min)",
                       "Interval (in minutes) at which the movement path is interpolated between fixes. "
                       "Smaller values produce smoother UDs (Utilization Distributions; probability density) but increase computation time.",
                       "5 min"),
            dbc.Input(id={"type": "model-param", "key": "bbmm_timestep"}, type="number", value=5, min=1, className="mb-2"),
            _info_label("Contour (%)",
                       "Percentage of the UD (Utilization Distribution; probability density) volume to retain. Defines the boundary of the utilization "
                       "distribution — e.g., 99% captures nearly all estimated use.",
                       "99%"),
            dbc.Input(id={"type": "model-param", "key": "bbmm_contour"}, type="number", value=99, min=50, max=100, step=0.001, className="mb-2"),
            _info_label("Grid buffer — mult4buff",
                       "Fraction of the sequence's spatial extent added as a margin when carving the "
                       "analysis subgrid. Prevents edge effects by ensuring the UD (Utilization Distribution; probability density) grid extends beyond "
                       "the outermost fixes.\n\n"
                       "Simply, mult4buff is the amount of buffer added around each sequence during "
                       "modeling, so with a buffer of 0.2, the subgrid extends 20% of the sequence's "
                       "spatial range.",
                       "0.2"),
            dbc.Input(id={"type": "model-param", "key": "bbmm_mult4buff"}, type="number", value=0.2, min=0, max=2, step=0.05, className="mb-2"),
            html.Hr(className="my-2"),
            dbc.Label("Extra BBMM outputs", style={"fontSize": "0.85rem", "fontWeight": "bold"}),
            dbc.Checkbox(
                id={"type": "model-param", "key": "bbmm_individual"},
                label="Per-individual UDs (utilization distributions) (per season + combined)",
                value=True,
                style={"fontSize": "0.8rem"},
            ),
            dbc.Checkbox(
                id={"type": "model-param", "key": "bbmm_ranges"},
                label="Intermediate range UDs (mean-UD density, e.g., Summer and Winter range utilization distributions)",
                value=True,
                style={"fontSize": "0.8rem"},
            ),
            dbc.Checkbox(
                id={"type": "model-param", "key": "bbmm_year_summaries"},
                label="Per-year summaries (stacked outputs by migration year, e.g., 2/1/26-1/31/27 — extends processing time)",
                value=False,
                style={"fontSize": "0.8rem"},
            ),
            dbc.Label("Range min. days of data", style={"fontSize": "0.8rem", "marginTop": "4px"}),
            dbc.Input(
                id={"type": "model-param", "key": "bbmm_range_mindays"},
                type="number", value=30, min=1, step=1, size="sm",
            ),
            html.Small(
                "Ranges are the gaps between migrations (summer = spring→fall, winter = fall→next spring). "
                "An animal-year's range is skipped if it has fewer than this many distinct days of fixes "
                "(or is missing a bounding migration date); skips are noted in processing_log.txt.",
                className="text-muted d-block mb-2", style={"fontSize": "0.68rem"},
            ),
            dbc.Checkbox(
                id={"type": "model-param", "key": "bbmm_linebuffer"},
                label="Line buffer (buffered migration lines stacked per animal)",
                value=False,
                style={"fontSize": "0.8rem"},
            ),
            html.Div(
                id="bbmm-linebuffer-distance-wrapper",
                children=[
                    dbc.Label("Buffer distance (m, total width — applied as half on each side)", style={"fontSize": "0.8rem", "marginTop": "4px"}),
                    dbc.Input(
                        id={"type": "model-param", "key": "bbmm_linebuffer_distance"},
                        type="number", value=400, min=1, step=1, size="sm",
                    ),
                ],
                style={"display": "none"},
            ),
        ]
    elif model == "DBBMM":
        auto_logic = fix_rate_msg or "Dynamic BBMM: window size auto-scaled to fix rate"
        panel = [
            dbc.Alert(
                [
                    "To run dBBMM, ensure ",
                    html.Strong("R"),
                    " is installed, along with the packages: ",
                    html.Code("move"), ", ",
                    html.Code("sf"), ", ",
                    html.Code("terra"), ", ",
                    html.Code("R.utils"), ", ",
                    html.Code("jsonlite"), ".",
                    " If R or any package is missing, the model will fall back to regular BBMM.",
                ],
                color="info",
                className="mb-2 py-2 px-3",
                style={"fontSize": "0.8rem"},
            ),
            _info_label("How dBBMM differs from BBMM",
                       "BBMM (Brownian Bridge Movement Model) uses a single motion variance value "
                       "for the entire sequence — either a fixed value you provide (FMV) or one "
                       "estimated via maximum likelihood from all triplets in the sequence.\n\n"
                       "dBBMM (Dynamic BBMM) estimates motion variance locally using a sliding window "
                       "of consecutive fixes, so the variance changes along the path. This captures "
                       "behavioral shifts (e.g., fast directed travel vs. slow foraging) that a single "
                       "global variance cannot represent.\n\n"
                       "For coarse fix-rate datasets (median gap > 5–7 hours), BBMM with a forced FMV "
                       "is preferred. dBBMM requires enough fixes within each sliding window to estimate "
                       "variance reliably, and coarse data often cannot meet this requirement — the "
                       "window would span days or weeks of real time, washing out behavioral detail. "
                       "dBBMM is best suited for fine fix-rate data (≤ 3–5 hours between fixes).",
                       "BBMM for coarse data; dBBMM for fine data"),
            dbc.Label("Rscript Path (optional)", style={"fontSize": "0.85rem"}),
            dbc.Input(
                id={"type": "model-param", "key": "dbbmm_rscript_path"},
                type="text",
                placeholder=r"e.g. C:\Program Files\R\R-4.5.2\bin\Rscript.exe",
                className="mb-1",
                style={"fontSize": "0.8rem"},
            ),
            html.Small(
                [
                    "Leave blank to auto-detect. If dBBMM falls back unexpectedly, "
                    "open R or RStudio and run ",
                    html.Code('R.home("bin")'),
                    " to find the correct path, then paste it here with ",
                    html.Code("\\Rscript.exe"),
                    " appended.",
                ],
                className="text-muted d-block mb-2",
                style={"fontSize": "0.7rem"},
            ),
            _info_label("Window Size (fixes)",
                       "Number of consecutive fixes used in each sliding window to estimate local "
                       "Brownian motion variance. Must be odd. Larger windows smooth out short-term "
                       "variation; smaller windows capture behavioral changes more quickly.",
                       "31 fixes"),
            dbc.Input(id={"type": "model-param", "key": "dbbmm_window"}, type="number", value=31, min=3, step=2, className="mb-2"),
            _info_label("Margin (fixes)",
                       "Number of fixes on each side of the window center that are excluded from "
                       "the variance estimate but still used for interpolation. Helps avoid edge "
                       "effects within the sliding window.",
                       "11 fixes"),
            dbc.Input(id={"type": "model-param", "key": "dbbmm_margin"}, type="number", value=11, min=1, className="mb-2"),
            _info_label("Location Error (m)",
                       "GPS measurement error in meters. Accounts for positional inaccuracy of the collar.",
                       "20 m"),
            dbc.Input(id={"type": "model-param", "key": "dbbmm_loc_error"}, type="number", value=20, min=0, className="mb-2"),
            _info_label("Contour (%)",
                       "Percentage of the UD (Utilization Distribution; probability density) volume to retain. Defines the boundary of the utilization "
                       "distribution.",
                       "99%"),
            dbc.Input(id={"type": "model-param", "key": "dbbmm_contour"}, type="number", value=99, min=50, max=100, className="mb-2"),
        ]
    elif model == "Kernel":
        panel = [
            _info_label("Bandwidth (auto = Scott's rule)",
                       "Smoothing bandwidth for the kernel density estimate. Controls how spread out "
                       "each point's contribution is. When left blank, Scott's rule is used to choose "
                       "an optimal bandwidth from the data.",
                       "Auto (leave blank)"),
            dbc.Input(id={"type": "model-param", "key": "kernel_bw"}, type="number", placeholder="Auto", min=0, className="mb-2"),
            _info_label("Contour (%)",
                       "Percentage of the UD (Utilization Distribution; probability density) volume to retain. Defines the boundary of the utilization "
                       "distribution.",
                       "99%"),
            dbc.Input(id={"type": "model-param", "key": "kernel_contour"}, type="number", value=99, min=50, max=100, className="mb-2"),
        ]
    elif model == "CTMM":
        panel = [
            dbc.Alert(
                [
                    "To run CTMM, ensure ",
                    html.Strong("R"),
                    " is installed, along with the packages: ",
                    html.Code("ctmm"), ", ",
                    html.Code("move"), ", ",
                    html.Code("sf"), ", ",
                    html.Code("terra"), ", ",
                    html.Code("R.utils"), ", ",
                    html.Code("jsonlite"), ".",
                    " If R or any package is missing, the model will fall back to Kernel UD.",
                ],
                color="info",
                className="mb-2 py-2 px-3",
                style={"fontSize": "0.8rem"},
            ),
            dbc.Label("Rscript Path (optional)", style={"fontSize": "0.85rem"}),
            dbc.Input(
                id={"type": "model-param", "key": "ctmm_rscript_path"},
                type="text",
                placeholder=r"e.g. C:\Program Files\R\R-4.5.2\bin\Rscript.exe",
                className="mb-1",
                style={"fontSize": "0.8rem"},
            ),
            html.Small(
                [
                    "Leave blank to auto-detect. If CTMM falls back unexpectedly, "
                    "open R or RStudio and run ",
                    html.Code('R.home("bin")'),
                    " to find the correct path, then paste it here with ",
                    html.Code("\\Rscript.exe"),
                    " appended.",
                ],
                className="text-muted d-block mb-2",
                style={"fontSize": "0.7rem"},
            ),
            _info_label("Info Criterion",
                       "Information criterion used for model selection. CTMM fits multiple movement "
                       "models and picks the best one using this criterion. AICc is recommended for "
                       "smaller sample sizes; AIC and BIC are standard alternatives.",
                       "AIC"),
            dcc.Dropdown(
                id={"type": "model-param", "key": "ctmm_criterion"},
                options=[
                    {"label": "AIC", "value": "AIC"},
                    {"label": "BIC", "value": "BIC"},
                    {"label": "AICc", "value": "AICc"},
                ],
                value="AIC",
                clearable=False,
                className="mb-2",
            ),
            _info_label("Contour (%)",
                       "Percentage of the UD (Utilization Distribution; probability density) volume to retain. Defines the boundary of the utilization "
                       "distribution.",
                       "99%"),
            dbc.Input(id={"type": "model-param", "key": "ctmm_contour"}, type="number", value=99, min=50, max=100, className="mb-2"),
        ]
    elif model == "LineBuffer":
        panel = [
            _info_label("Buffer Distance (m)",
                       "Total width of the buffer applied around each migration line segment. "
                       "Half the distance is applied on each side of the line. Buffers are stacked "
                       "across individuals to create a corridor density surface.",
                       "300 m"),
            dbc.Input(id={"type": "model-param", "key": "linebuf_dist"}, type="number", value=300, min=10, className="mb-2"),
        ]
    else:
        panel = [html.Span("Select a model to see parameters.", className="text-muted small")]

    return panel, auto_logic


@app.callback(
    Output("auto-flagging-collapse", "is_open"),
    Input("auto-flagging-toggle", "value"),
    prevent_initial_call=True,
)
def toggle_auto_flagging(checked):
    return bool(checked)


@app.callback(
    Output("bbmm-linebuffer-distance-wrapper", "style"),
    Input({"type": "model-param", "key": "bbmm_linebuffer"}, "value"),
    prevent_initial_call=True,
)
def toggle_linebuffer_distance(checked):
    return {"display": "block"} if checked else {"display": "none"}


def _build_linebuffer_output(
    sequences_dict: dict,
    seq_animal: dict,
    buffer_distance: float,
    outputs: Path,
    utm_crs,
) -> None:
    """Buffer each sequence's migration line, union per animal, and write a
    stacked shapefile.  ``buffer_distance`` is the TOTAL width (applied as
    half on each side, cap_style=round)."""
    import geopandas as gpd
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    half = buffer_distance / 2.0
    animal_buffers: dict[str, list] = {}

    for mig_key, sub in sequences_dict.items():
        if sub is None or len(sub) < 2:
            continue
        work = sub.copy().sort_values("date")
        if utm_crs is not None and getattr(work, "crs", None) is not None and work.crs != utm_crs:
            work = work.to_crs(utm_crs)
        xs = work.geometry.x.to_numpy(dtype=float)
        ys = work.geometry.y.to_numpy(dtype=float)
        line = LineString(list(zip(xs, ys)))
        buffered = line.buffer(half, cap_style="round")
        animal_id = seq_animal.get(mig_key, str(mig_key).rsplit("_", 2)[0])
        animal_buffers.setdefault(animal_id, []).append(buffered)

    if not animal_buffers:
        _append_processing_log(
            ["No sequences with ≥2 points — nothing to buffer."], header="LINE BUFFER",
        )
        return

    rows = []
    for animal_id, polys in sorted(animal_buffers.items()):
        merged = unary_union(polys)
        rows.append({"animal_id": animal_id, "n_seqs": len(polys), "buff_m": buffer_distance, "geometry": merged})

    gdf = gpd.GeoDataFrame(rows, crs=utm_crs)
    lb_dir = outputs / "LineBuffer"
    lb_dir.mkdir(parents=True, exist_ok=True)

    # 1. Raw per-animal line buffers (one polygon per animal, union of its sequences)
    raw_path = lb_dir / "raw_linebuffer.shp"
    gdf.to_file(raw_path)

    # 2. Dissolved: collapse all animal buffers into a single polygon
    dissolved_geom = unary_union(gdf.geometry.tolist())
    dissolved_gdf = gpd.GeoDataFrame(
        [{"type": "dissolved", "n_animals": len(animal_buffers), "buff_m": buffer_distance, "geometry": dissolved_geom}],
        crs=utm_crs,
    )
    dissolved_path = lb_dir / "by_Animal_linebuffer_dissolved.shp"
    dissolved_gdf.to_file(dissolved_path)

    # 3. Heatmap raster: count of overlapping unique animal line buffers per cell
    try:
        from rasterio.features import rasterize as rio_rasterize
        from rasterio.transform import from_bounds
        import rasterio

        bounds = dissolved_geom.bounds  # (minx, miny, maxx, maxy)
        cell_size = 250.0  # metres, matching the population grid default
        width = max(1, int(np.ceil((bounds[2] - bounds[0]) / cell_size)))
        height = max(1, int(np.ceil((bounds[3] - bounds[1]) / cell_size)))
        transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], width, height)

        heatmap = np.zeros((height, width), dtype=np.uint16)
        for _poly in gdf.geometry:
            if _poly is None or _poly.is_empty:
                continue
            layer = rio_rasterize(
                [(_poly, 1)],
                out_shape=(height, width),
                transform=transform,
                fill=0,
                dtype="uint8",
            )
            heatmap += layer.astype(np.uint16)

        heatmap_path = lb_dir / "linebuffer_heatmap.tif"
        with rasterio.open(
            str(heatmap_path), "w", driver="GTiff",
            height=height, width=width, count=1,
            dtype="uint16", crs=utm_crs, transform=transform,
        ) as dst:
            dst.write(heatmap, 1)
    except Exception as exc:
        logger.warning("Line buffer heatmap failed: %s", exc)

    _append_processing_log(
        [f"Buffer distance: {buffer_distance} m ({half} m each side, round caps)",
         f"Animals: {len(animal_buffers)}, sequences buffered: {sum(len(v) for v in animal_buffers.values())}",
         f"Outputs: {raw_path.relative_to(outputs)}, {dissolved_path.relative_to(outputs)}, linebuffer_heatmap.tif"],
        header="LINE BUFFER",
    )
    _log_action("LINE_BUFFER", animals=len(animal_buffers), buffer_m=buffer_distance)


def _num_or_none(v):
    """Coerce a UI numeric-input value to float, or None if blank/invalid."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _apply_model_ui_params(config: dict, model: str, p: dict) -> None:
    """Override the get_model_config defaults with whatever the user typed into
    the dynamic model-param panel. Mutates ``config`` in place.

    Only non-blank values override, so leaving a field empty keeps the computed
    default — most importantly, a blank BMVar keeps the auto/estimated value
    (R's BMVar=NULL behaviour) rather than forcing 0.
    """
    m = (model or "").upper()
    if m == "BBMM":
        bmv = _num_or_none(p.get("bbmm_bmvar"))
        if bmv is not None:
            config["bm_var"] = bmv            # explicit number => forced motion variance
        # blank => leave config["bm_var"] (None to estimate, or 1000 auto at coarse fix rates)
        # Conditional BMVar by fix rate (Chloe-style): only meaningful alongside a
        # forced bm_var. Threshold is hours between points; coarse seqs use the FMV.
        if p.get("bbmm_bmvar_conditional"):
            thr = _num_or_none(p.get("bbmm_bmvar_threshold"))
            if thr is not None:
                config["bm_var_fix_rate_threshold_hours"] = thr
        for src, dst in (
            ("bbmm_loc_error", "location_error"),
            ("bbmm_max_lag", "max_lag"),
            ("bbmm_timestep", "time_step"),
            ("bbmm_contour", "contour"),
            ("bbmm_mult4buff", "mult4buff"),
        ):
            val = _num_or_none(p.get(src))
            if val is not None:
                config[dst] = val
    elif m == "KERNEL":
        # Blank bandwidth => Scott's rule (None); a number forces the bandwidth.
        config["smooth_param"] = _num_or_none(p.get("kernel_bw"))
        c = _num_or_none(p.get("kernel_contour"))
        if c is not None:
            config["contour"] = c
    elif m in ("LINEBUFFER", "LINEBUFF"):
        d = _num_or_none(p.get("linebuf_dist"))
        if d is not None:
            config["buff_distance"] = d
    elif m == "DBBMM":
        for src, dst in (
            ("dbbmm_window", "dbbmm_window"),
            ("dbbmm_margin", "dbbmm_margin"),
            ("dbbmm_loc_error", "location_error"),
            ("dbbmm_contour", "contour"),
        ):
            val = _num_or_none(p.get(src))
            if val is not None:
                config[dst] = val
        rpath = (p.get("dbbmm_rscript_path") or "").strip()
        if rpath:
            config["rscript_path"] = rpath
    elif m == "CTMM":
        if p.get("ctmm_criterion"):
            config["info_criteria"] = p["ctmm_criterion"]
        c = _num_or_none(p.get("ctmm_contour"))
        if c is not None:
            config["contour"] = c
        rpath = (p.get("ctmm_rscript_path") or "").strip()
        if rpath:
            config["rscript_path"] = rpath


@app.callback(
    Output("model-status", "children"),
    Output("model-progress", "value"),
    Output("model-results-table", "children"),
    Output("store-model-results", "data"),
    Output("store-model-run-id", "data"),
    Output("model-poll-interval", "disabled"),
    Input("btn-run-models", "n_clicks"),
    State("store-processed-data", "data"),
    State("store-migtime-table", "data"),
    State("model-select", "value"),
    State("model-cores", "value"),
    State({"type": "seq-name", "index": dash.ALL}, "value"),
    State("store-config", "data"),
    State({"type": "model-param", "key": dash.ALL}, "value"),
    State({"type": "model-param", "key": dash.ALL}, "id"),
    State("model-cell-size", "value"),
    prevent_initial_call=True,
)
def run_modeling(
    n_clicks, processed_json, migtime_json, model, n_cores, seq_name_inputs, config_json,
    model_param_values, model_param_ids, cell_size,
):
    """Launch the modelling pipeline in a background thread so it survives
    browser disconnects and computer sleep. Returns immediately with a
    'running' status; the polling callback picks up results."""
    import threading
    import uuid

    if not processed_json:
        return _err_alert("No processed data. Complete Tab 1 first."), 0, "", None, None, True
    if not migtime_json:
        return _err_alert("No migration sequences. Complete Tab 2 first."), 0, "", None, None, True

    run_id = str(uuid.uuid4())[:8]
    _MODEL_RUN["run_id"] = run_id
    _MODEL_RUN["status"] = "running"
    _MODEL_RUN["result"] = None
    _MODEL_RUN["progress_msg"] = f"Starting {model.upper()} model run..."

    args = (processed_json, migtime_json, model, n_cores, seq_name_inputs,
            config_json, model_param_values, model_param_ids, cell_size)
    t = threading.Thread(target=_run_modeling_impl, args=args, daemon=True)
    t.start()
    _MODEL_RUN["thread"] = t

    status_alert = dbc.Alert(
        f"Model run started ({model.upper()}). This will continue even if your computer sleeps.",
        color="info", className="py-2",
    )
    return status_alert, 10, "", None, run_id, False


@app.callback(
    Output("model-status", "children", allow_duplicate=True),
    Output("model-progress", "value", allow_duplicate=True),
    Output("model-results-table", "children", allow_duplicate=True),
    Output("store-model-results", "data", allow_duplicate=True),
    Output("store-model-run-id", "data", allow_duplicate=True),
    Output("model-poll-interval", "disabled", allow_duplicate=True),
    Input("model-poll-interval", "n_intervals"),
    State("store-model-run-id", "data"),
    prevent_initial_call=True,
)
def poll_model_run(n_intervals, run_id):
    """Poll for background model run completion."""
    if not run_id or _MODEL_RUN.get("run_id") != run_id:
        raise PreventUpdate
    if _MODEL_RUN["status"] == "running":
        thread = _MODEL_RUN.get("thread")
        if thread is not None and not thread.is_alive():
            _MODEL_RUN["status"] = "error"
            if _MODEL_RUN.get("result") is None:
                _MODEL_RUN["result"] = (_err_alert("Model run thread died unexpectedly."), 0, "", None)
        else:
            msg = _MODEL_RUN.get("progress_msg", "Running...")
            return dbc.Alert(msg, color="info", className="py-2"), 50, dash.no_update, dash.no_update, dash.no_update, False
    # Done or error — return the stored result and disable polling.
    result = _MODEL_RUN.get("result")
    _MODEL_RUN["status"] = "idle"
    _MODEL_RUN["thread"] = None
    if result is None:
        return _err_alert("Model run finished but produced no result."), 0, "", None, None, True
    status, progress, table, results_json = result
    return status, progress, table, results_json, None, True


def _run_modeling_impl(
    processed_json, migtime_json, model, n_cores, seq_name_inputs, config_json,
    model_param_values, model_param_ids, cell_size,
):
    """Background thread target — runs the full modelling pipeline and stores
    its result in _MODEL_RUN for the polling callback to pick up."""

    def _finish(result_tuple):
        _MODEL_RUN["result"] = result_tuple
        _MODEL_RUN["status"] = "done"

    def _fail(msg):
        _MODEL_RUN["result"] = (_err_alert(msg), 0, "", None)
        _MODEL_RUN["status"] = "error"

    import datetime as _dt_mdl
    _model_start = _dt_mdl.datetime.now()

    try:
        df = _json_to_df(processed_json, "processed")
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        migtime = _json_to_df(migtime_json, "migtime")

        # Build a GeoDataFrame in WGS-84 first (for extract_sequences), then
        # project to UTM for modelling (the R workflow requires metre units).
        import geopandas as gpd
        if "lon" not in df.columns or "lat" not in df.columns:
            return _fail("Processed data missing lon/lat. Re-run Tab 1.")
        gdf_wgs = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326",
        )
        utm_crs = gdf_wgs.estimate_utm_crs()
        gdf_utm = gdf_wgs.to_crs(utm_crs)

        # Build the population grid once across ALL data (matches R's code2run.R).
        # Cell size is user-controlled (Tab 3), default 250 m.
        try:
            cell_size_m = float(cell_size) if cell_size not in (None, "") else 250.0
            if cell_size_m <= 0:
                cell_size_m = 250.0
        except (TypeError, ValueError):
            cell_size_m = 250.0
        pop_grid = create_population_grid(gdf_utm, cell_size=cell_size_m, buffer_mult=0.3)

        # Build the per-sequence dict by extracting points from the migtime windows.
        # Sequence slots in migtime are columns mig1_start..mig8_end. The Tab 2
        # "Sequence Names" inputs give each slot a user-facing label (e.g.
        # "Spring", "Fall") — those labels are what the data carries forward
        # into Tab 4. Fall back to "mig{i}" if a slot has no user-supplied name.
        clean_names = [str(s).strip() for s in (seq_name_inputs or [])]
        seq_labels = [
            clean_names[i] if i < len(clean_names) and clean_names[i] else f"mig{i + 1}"
            for i in range(8)
        ]
        try:
            per_label_gdfs = extract_sequences(
                df=df, migtime_df=migtime, sequence_names=seq_labels,
            )
        except Exception as exc:
            return _fail(f"Sequence extraction failed: {exc}")

        # Flatten {label: gdf-with-all-animals} -> {mig_key: per-animal sub-gdf}
        # The `mig` column in each gdf is "<animal>_<bio_year>_<label>".
        # Also record key->animal and key->label so per-individual aggregation
        # can group reliably (animal ids contain underscores, so the mig_key
        # can't be split positionally).
        sequences_dict: dict[str, gpd.GeoDataFrame] = {}
        seq_animal: dict[str, str] = {}
        seq_label: dict[str, str] = {}
        for label, ld in per_label_gdfs.items():
            if ld.empty:
                continue
            ld = ld.set_crs("EPSG:4326").to_crs(utm_crs)
            for mig_key, sub in ld.groupby("mig"):
                # Force back to GeoDataFrame — older geopandas versions return
                # a plain DataFrame from groupby, which breaks downstream
                # geometry access in calc_kernel_ud / calc_bbmm.
                sub = gpd.GeoDataFrame(sub.copy(), geometry="geometry", crs=ld.crs)
                sub["x"] = sub.geometry.x
                sub["y"] = sub.geometry.y
                sequences_dict[str(mig_key)] = sub
                seq_animal[str(mig_key)] = str(sub["id"].iloc[0]) if "id" in sub.columns and len(sub) else str(mig_key)
                seq_label[str(mig_key)] = str(label)

        if not sequences_dict:
            return _fail(
                "No migration sequences could be extracted from the migtime table. "
                "Check that some animal-years have non-empty mig1..migN windows."
            )

        # Compose the modelling config — pulls in BBMM auto-logic for coarse fix rates.
        fix_rate_hours = float(df["fix_rate_hours"].median()) if "fix_rate_hours" in df.columns else None
        config = get_model_config(method=model, fix_rate_hours=fix_rate_hours)
        config["cell_size"] = pop_grid["cell_size"]
        # Apply the user's parameter edits from the dynamic model panel. Without
        # this the UI inputs (BMVar, location error, max lag, contour, …) were
        # collected but never used — the run always used get_model_config's
        # defaults. The ALL-matched value/id lists are zipped back into a
        # {key: value} dict keyed by each input's "key".
        ui_params = {
            pid.get("key"): val
            for pid, val in zip(model_param_ids or [], model_param_values or [])
            if isinstance(pid, dict)
        }
        _apply_model_ui_params(config, model, ui_params)

        # Extra BBMM output options (only present in the BBMM panel; absent →
        # None → off). Not model params, so _apply_model_ui_params ignores them.
        want_individual = bool(ui_params.get("bbmm_individual"))
        want_ranges = bool(ui_params.get("bbmm_ranges"))
        want_year_summaries = bool(ui_params.get("bbmm_year_summaries"))
        want_linebuffer = bool(ui_params.get("bbmm_linebuffer"))
        try:
            linebuffer_distance = float(ui_params.get("bbmm_linebuffer_distance") or 400)
        except (TypeError, ValueError):
            linebuffer_distance = 400.0
        try:
            range_mindays = int(ui_params.get("bbmm_range_mindays") or 30)
        except (TypeError, ValueError):
            range_mindays = 30

        # Keys relevant to the selected model — used for logging and the
        # version manifest (excludes other-model defaults and machine paths).
        _SHARED_KEYS = {
            "num_cores", "max_timeout", "mult4buff", "cell_size", "contour",
        }
        _MODEL_KEYS = {
            "BBMM": _SHARED_KEYS | {
                "time_step", "bm_var", "location_error", "max_lag",
                "bm_var_fix_rate_threshold_hours",
            },
            "DBBMM": _SHARED_KEYS | {
                "time_step", "bm_var", "location_error", "max_lag",
                "dbbmm_margin", "dbbmm_window",
            },
            "CTMM": _SHARED_KEYS | {"info_criteria"},
            "KERNEL": _SHARED_KEYS | {"smooth_param", "subsample"},
            "LINEBUFF": _SHARED_KEYS | {"buff_distance"},
            "LINEBUFFER": _SHARED_KEYS | {"buff_distance"},
        }
        relevant = _MODEL_KEYS.get(model.upper(), set())

        # If a working directory is set, start a NEW output version and drop
        # UDs/Footprints into ModelOutputs/V{n}/. Each model run gets its own
        # version folder; Tab 4/5 population outputs join the same version.
        if _ACTIVE_WORKDIR is not None:
            version_n = _start_new_version()
            _set_model_source(version_n)  # this version physically holds the UDs
            outputs = _workdir_version()
            (outputs / "UDs").mkdir(parents=True, exist_ok=True)
            (outputs / "Footprints").mkdir(parents=True, exist_ok=True)
            config["ud_dir"] = str(outputs / "UDs")
            config["footprint_dir"] = str(outputs / "Footprints")
            param_fields = {
                k: v for k, v in config.items()
                if k in relevant
            }
            # Provenance manifest for this version (params + diff vs parent +
            # shared-input references).
            _write_version_manifest(version_n, model.upper(), param_fields)
            _log_action(
                "RUN_MODELS",
                method=model.upper(),
                version=version_n,
                n_sequences=len(sequences_dict),
                cores=int(n_cores or 1),
                fix_rate_hours=("auto" if fix_rate_hours is None else round(fix_rate_hours, 3)),
                **param_fields,
            )

        param_fields = {
            k: v for k, v in config.items()
            if k in relevant
        }

        # Actually run the pipeline.
        _MODEL_RUN["progress_msg"] = f"Running {model.upper()} on {len(sequences_dict)} sequences..."
        try:
            results, meta_df = run_all_sequences(
                sequences_dict=sequences_dict,
                method=model,
                pop_grid=pop_grid,
                config=config,
                n_cores=int(n_cores or 1),
            )
        except Exception as exc:
            _runtime = (_dt_mdl.datetime.now() - _model_start).total_seconds()
            _append_processing_log(
                [
                    f"Model: {model.upper()}",
                    f"Grid cell size: {cell_size_m:g} m",
                    f"Sequences attempted: {len(sequences_dict)}",
                    "Parameters (defaults included):",
                    *[f"    {k} = {v}" for k, v in param_fields.items()],
                    f"Result: FAILED — {exc}",
                    f"Run time: {_runtime:.1f} s",
                ],
                header="MODEL RUN",
            )
            return _fail(f"Modeling failed: {exc}\n{traceback.format_exc()[:600]}")

        _MODEL_RUN["progress_msg"] = f"{model.upper()} complete — writing output files..."

        # Stash the live objects for Tab 4 (population merging needs the raw
        # UD rasters + footprint polygons + pop_grid, none of which survive
        # JSON serialisation through dcc.Store).
        _MODEL_CACHE.clear()
        _MODEL_CACHE["pop_grid"] = pop_grid
        _MODEL_CACHE["results"] = results
        _MODEL_CACHE["method"] = model
        _MODEL_CACHE["utm_crs"] = str(utm_crs)
        _MODEL_CACHE["seq_animal"] = seq_animal
        _MODEL_CACHE["seq_label"] = seq_label
        _MODEL_CACHE["sequences_dict"] = sequences_dict
        _MODEL_CACHE["seq_labels"] = seq_labels
        _MODEL_CACHE["want_year_summaries"] = want_year_summaries
        if want_linebuffer:
            _MODEL_CACHE["linebuffer_distance"] = linebuffer_distance
        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"], errors="coerce").dropna()
            if len(ts):
                _MODEL_CACHE["input_date_range"] = (ts.min().strftime("%m/%d/%Y"), ts.max().strftime("%m/%d/%Y"))

        # ---- Extra BBMM outputs: per-individual UDs + winter/summer ranges ----
        # Only for BBMM, only when the user ticked the boxes, only with a workdir.
        if model.upper() == "BBMM" and _ACTIVE_WORKDIR is not None:
            outputs = _workdir_version()
            if want_individual:
                try:
                    ind_dir = outputs / "IndividualUDs"
                    written_ind = write_individual_uds(
                        results, pop_grid, ind_dir, seq_animal, seq_label, mode="both",
                    )
                    _append_processing_log(
                        [f"Per-individual UDs (per-season + combined): {len(written_ind)} files -> ModelOutputs/IndividualUDs/"],
                        header="PER-INDIVIDUAL UDs",
                    )
                    _log_action("INDIVIDUAL_UDS", files=len(written_ind))
                except Exception as exc:
                    _append_processing_log([f"Per-individual UD output FAILED: {exc}"], header="PER-INDIVIDUAL UDs")
                try:
                    fp_dir = outputs / "IndividualFootprints"
                    written_fp = write_individual_footprints(
                        results, pop_grid, fp_dir, seq_animal, seq_label, mode="both",
                    )
                    _append_processing_log(
                        [f"Per-individual footprints (per-season + combined): {len(written_fp)} files -> ModelOutputs/IndividualFootprints/"],
                        header="PER-INDIVIDUAL FOOTPRINTS",
                    )
                    _log_action("INDIVIDUAL_FOOTPRINTS", files=len(written_fp))
                except Exception as exc:
                    _append_processing_log([f"Per-individual footprint output FAILED: {exc}"], header="PER-INDIVIDUAL FOOTPRINTS")

            if want_ranges:
                try:
                    range_seqs, range_key_animal, range_notes = build_range_sequences(
                        gdf_utm, migtime, seq_labels, mindays=range_mindays,
                    )
                    rdir = outputs / "RangeUDs"
                    rdir.mkdir(parents=True, exist_ok=True)
                    # Per-sequence range UDs are aggregated in-memory; don't write
                    # them into the migration UDs/ folder.
                    rconfig = {k: v for k, v in config.items() if k not in ("ud_dir", "footprint_dir")}
                    summary: list[str] = []
                    for season, seqs in range_seqs.items():
                        if not seqs:
                            summary.append(f"{season}: 0 range sequences built")
                            continue
                        r_results, _ = run_all_sequences(
                            sequences_dict=seqs, method="BBMM", pop_grid=pop_grid,
                            config=rconfig, n_cores=int(n_cores or 1),
                        )
                        n_ind, path = write_range_density(
                            r_results, pop_grid, rdir / f"averageUD_{season}.tif", range_key_animal,
                        )
                        summary.append(
                            f"{season}: {len(seqs)} sequences, {n_ind} individuals -> "
                            + (f"RangeUDs/averageUD_{season}.tif" if path else "no density written")
                        )
                        if want_individual:
                            # mode="season" only: each range call passes a single
                            # season's sequences, so a "combined" UD would just
                            # duplicate the per-season UD. Skip it.
                            write_individual_uds(
                                r_results, pop_grid, rdir / f"Individual_{season}",
                                range_key_animal, {k: season for k in r_results}, mode="season",
                            )
                    capped = range_notes[:40]
                    extra = [f"... +{len(range_notes) - 40} more skip notes"] if len(range_notes) > 40 else []
                    _append_processing_log(
                        [f"Range min. days of data: {range_mindays}",
                         "Season-by-season:", *[f"    {s}" for s in summary],
                         f"Animal-years skipped: {len(range_notes)}",
                         *[f"    {n}" for n in capped], *extra],
                        header="WINTER / SUMMER RANGE UDs",
                    )
                    _log_action("RANGE_UDS", mindays=range_mindays, skipped=len(range_notes))
                except Exception as exc:
                    _append_processing_log(
                        [f"Range UD output FAILED: {exc}"], header="WINTER / SUMMER RANGE UDs",
                    )

            if want_linebuffer:
                try:
                    _build_linebuffer_output(
                        sequences_dict, seq_animal, linebuffer_distance, outputs, utm_crs,
                    )
                except Exception as exc:
                    _append_processing_log(
                        [f"Line buffer output FAILED: {exc}"], header="LINE BUFFER",
                    )

        # MigLines / MigPoints / MigLines_Dist shapefiles — written next to
        # the BBMM tifs under {herd}_Primary_Outputs/. Schema mirrors the WMI canonical.
        if _ACTIVE_WORKDIR is not None:
            try:
                herd_id = "Herd"
                bio_month = 2
                bio_day = 1
                if config_json:
                    cfg_obj = json.loads(config_json) if isinstance(config_json, str) else config_json
                    if isinstance(cfg_obj, dict):
                        herd_id = str(cfg_obj.get("herd_id", "Herd")).strip() or "Herd"
                        bio_month = int(cfg_obj.get("bio_year_start_month", 2) or 2)
                        bio_day = int(cfg_obj.get("bio_year_start_day", 1) or 1)
                import datetime as _dt
                date_stamp = _dt.datetime.now().strftime("%m%d%y")
                prim_dir = _workdir_version() / f"{herd_id}_Primary_Outputs"
                prim_dir.mkdir(parents=True, exist_ok=True)
                mig_written = write_mig_outputs(
                    processed_df=df,
                    migtime_df=migtime,
                    sequences_dict=sequences_dict,
                    out_dir=prim_dir,
                    herd_id=herd_id,
                    date_stamp=date_stamp,
                    seq_labels=seq_labels,
                    bio_year_start_month=bio_month,
                    bio_year_start_day=bio_day,
                    target_crs=utm_crs,
                )
                _log_action(
                    "WRITE_MIG_OUTPUTS",
                    herd_id=herd_id,
                    files=";".join(p.name for p in mig_written.values()),
                )
            except Exception as exc:
                import traceback as _tb_mig
                logger_warn = f"MigLines/MigPoints write failed: {exc}\n{_tb_mig.format_exc()}"
                print(logger_warn)
                _append_processing_log(
                    [f"MigLines/MigPoints write FAILED: {exc}"],
                    header="MIG OUTPUT ERROR",
                )

            # Herd-level metadata CSV + XLSX (canonical WMI schema), and
            # the per-season migration_distance_info CSVs that R's code2run.R
            # also produces.
            try:
                meta_outputs_dir = _workdir_version()
                species = None
                if "Species" in df.columns:
                    sp_non_null = df["Species"].dropna()
                    if not sp_non_null.empty:
                        species = str(sp_non_null.iloc[0])
                if not species and herd_id:
                    _dau = herd_id.strip().upper().replace("-", "").replace("_", "")
                    if _dau.startswith("D"):
                        species = "Deer"
                    elif _dau.startswith("E"):
                        species = "Elk"
                    elif _dau.startswith(("A", "P")):
                        species = "Pronghorn"
                    elif _dau.startswith(("RBS", "S")):
                        species = "Sheep"
                    elif _dau.startswith(("MG", "G")):
                        species = "Goat"
                v_label = _resolve_version_dir(_ACTIVE_WORKDIR, _ACTIVE_VERSION).name if _ACTIVE_VERSION else None
                herd_meta = write_herd_metadata(
                    processed_df=df,
                    sequences_dict=sequences_dict,
                    out_dir=meta_outputs_dir,
                    herd_id=herd_id,
                    species=species,
                    date_stamp=date_stamp,
                    season_labels_order=seq_labels,
                    version=v_label,
                )
                _log_action(
                    "METADATA_EXPORT",
                    herd_id=herd_id,
                    herd_files=";".join(p.name for p in herd_meta.values()),
                )
            except Exception as meta_exc:
                print(f"WARNING: metadata export skipped: {meta_exc}")

        # Build the results table — one row per sequence.
        rows = []
        for mig_key, res in results.items():
            meta = res.get("metadata", {}) or {}
            err = meta.get("errors") or meta.get("error") or ""
            status = "Error" if err and err != "None" else "Complete"
            rows.append({
                "sequence": mig_key,
                "method": meta.get("method", model),
                "n_locs": meta.get("num_locs", meta.get("n_fixes", "")),
                "start_date": str(meta.get("start_date", ""))[:10],
                "end_date": str(meta.get("end_date", ""))[:10],
                "runtime_min": meta.get("execution_time_min", ""),
                "status": status,
                "notes": err if err and err != "None" else meta.get("method_note", ""),
            })
        results_df = pd.DataFrame(rows)

        # Persist results metadata next to the outputs if a workdir is set.
        if _ACTIVE_WORKDIR is not None:
            try:
                metadata_csv = _workdir_version() / "model_results.csv"
                results_df.to_csv(metadata_csv, index=False)
            except Exception:
                pass

        table = dash_table.DataTable(
            data=results_df.to_dict("records"),
            columns=[{"name": c, "id": c} for c in results_df.columns],
            style_table={"overflowX": "auto"},
            style_cell={
                "backgroundColor": "#2a2a2a",
                "color": "#f0f0f0",
                "border": "1px solid #444",
                "fontSize": "12px",
                "padding": "4px 8px",
            },
            style_header={"backgroundColor": "#1a1a1a", "fontWeight": "bold", "color": "#aef"},
            style_data_conditional=[
                {"if": {"filter_query": "{status} = 'Error'", "column_id": "status"}, "color": "#FCA5A5"},
                {"if": {"filter_query": "{status} = 'Complete'", "column_id": "status"}, "color": "#6EE7B7"},
            ],
        )

        n_ok = int((results_df["status"] == "Complete").sum()) if not results_df.empty else 0
        n_err = int((results_df["status"] == "Error").sum()) if not results_df.empty else 0
        msg = f"Modeling complete — {n_ok} sequences modelled with {model.upper()}, {n_err} errors. Proceed to Population Outputs (Tab 4)."

        # ---- processing_log.txt: model section ----
        _runtime = (_dt_mdl.datetime.now() - _model_start).total_seconds()
        err_rows = results_df[results_df["status"] == "Error"] if not results_df.empty else results_df.iloc[0:0]
        _input_dr = _MODEL_CACHE.get("input_date_range")
        log_lines = [
            f"Input data date range: {_input_dr[0]} — {_input_dr[1]}" if _input_dr else "Input data date range: unknown",
            f"Model: {model.upper()}",
            f"Grid cell size: {cell_size_m:g} m",
            f"Cores: {int(n_cores or 1)}",
            f"Median fix rate: {'auto/NA' if fix_rate_hours is None else f'{fix_rate_hours:.2f} h'}",
            f"Sequences: {len(sequences_dict)}  (modelled OK: {n_ok}, errors: {n_err})",
            "Parameters (defaults included):",
            *[f"    {k} = {v}" for k, v in param_fields.items()],
            f"Result: {'SUCCESS' if n_err == 0 else 'COMPLETED WITH ERRORS'}",
            f"Run time: {_runtime:.1f} s",
        ]
        if len(err_rows) > 0:
            log_lines.append("Sequences with errors:")
            for _, er in err_rows.head(25).iterrows():
                log_lines.append(f"    {er['sequence']}: {er.get('notes', '')}")
            if len(err_rows) > 25:
                log_lines.append(f"    … and {len(err_rows) - 25} more")
        if _ACTIVE_WORKDIR is not None:
            _vdir = _workdir_version()
            log_lines.append(
                f"Outputs: ModelOutputs/{_vdir.name}/UDs, /Footprints  "
                f"(+ {herd_id}_Primary_Outputs/ after population step)"
            )
        _append_processing_log(log_lines, header="MODEL RUN")

        _finish((_ok_alert(msg), 100, table, _df_to_json(results_df, "model_results")))

    except Exception as exc:
        _fail(f"Modeling error: {exc}\n{traceback.format_exc()[:600]}")


def _model_results_table_from_results(results: dict) -> "tuple":
    """Build the (results_df, DataTable) shown in Tab 3 from a results dict —
    shared shape with run_modeling's inline table so loaded results look the
    same as freshly-run ones."""
    rows = []
    for mig_key, res in results.items():
        meta = res.get("metadata", {}) or {}
        err = meta.get("errors") or meta.get("error") or ""
        status = "Error" if err and err != "None" else "Complete"
        rows.append({
            "sequence": mig_key,
            "method": meta.get("method", ""),
            "n_locs": meta.get("num_locs", meta.get("n_fixes", "")),
            "start_date": str(meta.get("start_date", ""))[:10],
            "end_date": str(meta.get("end_date", ""))[:10],
            "runtime_min": meta.get("execution_time_min", ""),
            "status": status,
            "notes": err if err and err != "None" else meta.get("method_note", ""),
        })
    results_df = pd.DataFrame(rows)
    table = dash_table.DataTable(
        data=results_df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in results_df.columns],
        style_table={"overflowX": "auto"},
        style_cell={
            "backgroundColor": "#2a2a2a", "color": "#f0f0f0",
            "border": "1px solid #444", "fontSize": "12px", "padding": "4px 8px",
        },
        style_header={"backgroundColor": "#1a1a1a", "fontWeight": "bold", "color": "#aef"},
        style_data_conditional=[
            {"if": {"filter_query": "{status} = 'Error'", "column_id": "status"}, "color": "#FCA5A5"},
            {"if": {"filter_query": "{status} = 'Complete'", "column_id": "status"}, "color": "#6EE7B7"},
        ],
    )
    return results_df, table


def _read_shp_cached(shp_path: Path):
    """Read a shapefile, reproject to EPSG:4326, and return a GeoJSON dict.
    Writes a .display.geojson companion on first read; subsequent calls load
    the companion directly (skipping GeoPandas)."""
    if not shp_path.exists():
        return None
    companion = shp_path.with_suffix(".display.geojson")
    mtime = shp_path.stat().st_mtime
    if companion.is_file() and companion.stat().st_mtime >= mtime:
        try:
            with open(companion, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    try:
        import geopandas as gpd
        gdf = gpd.read_file(str(shp_path))
        if gdf.crs is not None and not gdf.crs.equals("EPSG:4326"):
            gdf = gdf.to_crs(epsg=4326)
        json_str = gdf.to_json()
        result = json.loads(json_str)
        try:
            with open(companion, "w", encoding="utf-8") as fh:
                fh.write(json_str)
        except Exception:
            pass
        return result
    except Exception:
        return None


def _load_pop_outputs_from_disk(outputs: Path):
    """Read prior population/footprint contour shapefiles back into the
    store-pop-outputs JSON shape ({"use", "footprint", "config"}) in EPSG:4326,
    so Tab 5 can draw them without re-generating. Returns a JSON string or None
    if neither shapefile exists."""
    use_shp = outputs / "Contours" / "Pop_use_contours.shp"
    if not use_shp.exists():
        use_shp = outputs / "popUseMerged" / "Pop_use_contours.shp"
    foot_shp = outputs / "Contours" / "Footprint_contours.shp"
    if not foot_shp.exists():
        foot_shp = outputs / "footPrintsMerged" / "Footprint_contours.shp"
    use_fc = _read_shp_cached(use_shp)
    foot_fc = _read_shp_cached(foot_shp)
    if use_fc is None and foot_fc is None:
        return None
    return json.dumps({"use": use_fc, "footprint": foot_fc, "config": {}}, default=str)


@app.callback(
    Output("model-status", "children", allow_duplicate=True),
    Output("model-progress", "value", allow_duplicate=True),
    Output("model-results-table", "children", allow_duplicate=True),
    Output("store-model-results", "data", allow_duplicate=True),
    Output("store-pop-outputs", "data", allow_duplicate=True),
    Input("btn-load-model-results", "n_clicks"),
    prevent_initial_call=True,
)
def load_previous_model_results(n_clicks):
    """Rebuild the in-memory model cache from the GeoTIFFs in this working
    directory's ModelOutputs/UDs + Footprints, plus any saved population
    contours — so Tab 4 (population) and Tab 5 (map) work without re-running the
    models. Note: UD/footprint tifs are overwritten per-sequence on each run, so
    this loads the most recent run's results (any stale tifs from a prior run
    with different sequence names would also be picked up)."""
    nu = dash.no_update
    if _ACTIVE_WORKDIR is None:
        return _err_alert("Set a working directory in Tab 1 first."), nu, nu, nu, nu
    try:
        # Model UDs live in the latest version that actually holds them — a
        # population-only branch version references (doesn't copy) them.
        model_v = _latest_version_with_model()
        outputs = _workdir_version(version=model_v) if model_v else _workdir_version()
    except Exception as exc:
        return _err_alert(f"Could not resolve working directory: {exc}"), nu, nu, nu, nu

    loaded = load_model_outputs_from_disk(
        ud_dir=outputs / "UDs",
        footprint_dir=outputs / "Footprints",
        metadata_csv=outputs / "model_results.csv",
    )
    if loaded is None:
        return (
            _err_alert(
                f"No model outputs found in {outputs.name}/UDs/. Run the models first, "
                "or check that the working directory is the one that holds your results."
            ),
            nu, nu, nu, nu,
        )

    pop_grid, results, utm_crs, method = loaded
    _MODEL_CACHE.clear()
    _MODEL_CACHE["pop_grid"] = pop_grid
    _MODEL_CACHE["results"] = results
    _MODEL_CACHE["method"] = method
    _MODEL_CACHE["utm_crs"] = utm_crs

    results_df, table = _model_results_table_from_results(results)

    pop_store = _load_pop_outputs_from_disk(outputs)
    _log_action(
        "LOAD_MODEL_RESULTS",
        sequences=len(results),
        method=method,
        pop_outputs_loaded=bool(pop_store),
    )
    pop_note = (
        " Saved population outputs were loaded too — open Tab 5 to view them."
        if pop_store else
        " No saved population outputs found — generate them in Tab 4."
    )
    msg = _ok_alert(
        f"Loaded {len(results)} model result(s) from {outputs.name}/UDs/ (method: {method})."
        + pop_note
    )
    return msg, 100, table, _df_to_json(results_df, "model_results"), (pop_store if pop_store else nu)


def _pop_preview_from_store(pop_json) -> Any:
    """Build the Tab-4 contour-by-area preview (one small table per surface)
    from the store-pop-outputs JSON — used when loading saved population
    outputs (the fresh-generate path builds its own from the GeoDataFrames)."""
    try:
        obj = json.loads(pop_json) if isinstance(pop_json, str) else pop_json
    except Exception:
        return ""
    if not isinstance(obj, dict):
        return ""

    def _table(fc, title):
        feats = (fc or {}).get("features", []) if fc else []
        if not feats:
            return html.Div([html.Strong(title), html.Span(" — none", className="text-muted ms-2")])

        def _cnum(f):
            try:
                return float((f.get("properties") or {}).get("contour"))
            except (TypeError, ValueError):
                return -1.0

        rows = []
        for f in sorted(feats, key=_cnum, reverse=True):
            p = f.get("properties") or {}
            try:
                c = f"{float(p.get('contour')):g}%"
            except (TypeError, ValueError):
                c = str(p.get("contour", ""))
            try:
                a = f"{float(p.get('area_km2')):.2f} km²"
            except (TypeError, ValueError):
                a = str(p.get("area_km2", ""))
            rows.append(html.Tr([html.Td(c), html.Td(a)]))
        return dbc.Card(dbc.CardBody([
            html.H6(title, className="text-info"),
            dbc.Table(
                [html.Thead(html.Tr([html.Th("Contour"), html.Th("Area")])), html.Tbody(rows)],
                bordered=False, hover=True, size="sm", style={"color": "#E0E0E0"},
            ),
        ]), className="mb-2")

    return html.Div([_table(obj.get("use"), "Population Use"), _table(obj.get("footprint"), "Footprint")])


@app.callback(
    Output("pop-status", "children", allow_duplicate=True),
    Output("pop-map-preview", "children", allow_duplicate=True),
    Output("store-pop-outputs", "data", allow_duplicate=True),
    Input("btn-load-pop-outputs", "n_clicks"),
    prevent_initial_call=True,
)
def load_previous_pop_outputs(n_clicks):
    """Load saved population contours (Contours/) from the
    working directory into store-pop-outputs — so Tab 5 can draw them and Tab 4
    shows the contour-area preview — without re-running the population merge."""
    nu = dash.no_update
    if _ACTIVE_WORKDIR is None:
        return _err_alert("Set a working directory in Tab 1 first."), nu, nu
    try:
        outputs = _workdir_version()  # latest existing version
    except Exception as exc:
        return _err_alert(f"Could not resolve working directory: {exc}"), nu, nu

    pop_store = _load_pop_outputs_from_disk(outputs)
    if not pop_store:
        return (
            _err_alert(
                "No saved population outputs found in Contours/. "
                "Generate them first, or check that the working directory holds your results."
            ),
            nu, nu,
        )
    _log_action("LOAD_POP_OUTPUTS", source=outputs.name)
    return (
        _ok_alert("Loaded saved population outputs. Open Tab 5 to view them on the map."),
        _pop_preview_from_store(pop_store),
        pop_store,
    )


# ===========================================================================
# Callbacks — Tab 4: Population Outputs
# ===========================================================================

# After a model run completes, repopulate the "Seasons to Merge" checklist
# from the labels actually present in the results (so renames from Tab 2 flow
# through). store-model-results is touched whenever run_modeling returns, so
# we key off it as our trigger.
@app.callback(
    Output("pop-seasons", "options"),
    Output("pop-seasons", "value"),
    Input("store-model-results", "data"),
    Input("main-tabs", "active_tab"),
    prevent_initial_call=False,
)
def refresh_pop_seasons_checklist(_model_results_json, _active_tab):
    if not _MODEL_CACHE.get("results"):
        # Fallback: keep whatever the UI currently has — but ensure at least
        # the default Spring/Fall options exist so the page doesn't break.
        return [
            {"label": "Spring", "value": "Spring"},
            {"label": "Fall", "value": "Fall"},
        ], ["Spring", "Fall"]
    labels: set[str] = set()
    for mig_key in _MODEL_CACHE["results"].keys():
        parts = str(mig_key).rsplit("_", 1)
        if len(parts) == 2 and parts[1]:
            labels.add(parts[1])
    labels_sorted = sorted(labels)
    return (
        [{"label": lab, "value": lab} for lab in labels_sorted],
        labels_sorted,  # pre-select all by default
    )



@app.callback(
    Output("pop-status", "children"),
    Output("pop-map-preview", "children"),
    Output("store-pop-outputs", "data"),
    Input("btn-gen-pop", "n_clicks"),
    State("store-processed-data", "data"),
    State("store-model-results", "data"),
    State("pop-seasons", "value"),
    State("pop-merge-order", "value"),
    State("pop-contour-type", "value"),
    State("pop-contour-levels", "value"),
    State("pop-min-drop", "value"),
    State("pop-min-fill", "value"),
    State("pop-smooth-toggle", "value"),
    State("pop-smooth-bw", "value"),
    State("pop-stopover-toggle", "value"),
    State("pop-stopover-pct", "value"),
    State("pop-minimumx-toggle", "value"),
    State("pop-minimumx-value", "value"),
    State("store-config", "data"),
    prevent_initial_call=True,
)
def generate_pop_outputs(
    n_clicks, processed_json, model_results_json,
    seasons, merge_order, contour_type, contour_levels_str,
    min_drop, min_fill, smooth, smooth_bw, stopover_on, stopover_pct,
    minimumx_on, minimumx_value, config_json,
):
    if not processed_json:
        return _err_alert("No processed data. Complete Tab 1 first."), "", None

    if not _MODEL_CACHE.get("results") or not _MODEL_CACHE.get("pop_grid"):
        return (
            _err_alert(
                "No model results in memory. Run Tab 3 first. "
                "(Note: model results live in process memory and don't survive an app restart yet.)"
            ),
            "",
            None,
        )

    import datetime as _dt_pop
    _pop_start = _dt_pop.datetime.now()

    try:
        contour_levels = [float(x.strip()) for x in (contour_levels_str or "5,10,15,20,30,50").split(",")]
    except ValueError:
        return _err_alert("Invalid contour levels. Use comma-separated numbers like: 50, 75, 95, 99"), "", None

    try:
        # Normalise Tab 4 form values into what the population_outputs module wants.
        merge_order_tuple = ("id", "year") if (merge_order or "id_year") == "id_year" else ("year", "id")
        contour_type_norm = "Area" if (contour_type or "area").lower() == "area" else "Volume"

        # Pull the live model results from the in-process cache.
        results = _MODEL_CACHE["results"]
        pop_grid = _MODEL_CACHE["pop_grid"]

        # Collect per-sequence UDs, then stack by individual animal so each
        # animal contributes one UD surface (mean of its sequences). This way
        # population counts reflect the number of *animals* using each cell,
        # not the number of sequences (which inflates counts for animals
        # tracked across multiple bio-years).
        seq_animal_map = _MODEL_CACHE.get("seq_animal", {})
        seq_ud_by_season: dict[str, dict[str, list[np.ndarray]]] = {}
        # Also track per-sequence bio_year for year summaries.
        # Structure: {bio_year: {season: {animal_id: [ud_arrays]}}}
        seq_ud_by_year: dict[str, dict[str, dict[str, list[np.ndarray]]]] = {}
        footprint_dict: dict[str, Any] = {}
        n_skipped = 0
        n_sequences = 0
        for mig_key, res in results.items():
            ud = res.get("ud_raster")
            fp = res.get("footprint_polygon")
            meta = res.get("metadata") or {}
            err = meta.get("errors") or meta.get("error") or ""
            if ud is None or err and err != "None":
                n_skipped += 1
                continue

            parts = str(mig_key).rsplit("_", 1)
            label = parts[1] if len(parts) == 2 else ""

            if seasons and label not in seasons:
                continue

            n_sequences += 1
            animal_id = seq_animal_map.get(str(mig_key), str(mig_key))
            seq_ud_by_season.setdefault(label, {}).setdefault(animal_id, []).append(ud)
            if fp is not None:
                footprint_dict[str(mig_key)] = fp

            # Extract bio_year from mig_key: "<animal>_<bioYear>_<season>"
            # After rsplit("_", 1) stripped the season, remainder is "<animal>_<bioYear>".
            # Strip the known animal_id prefix to get the bio_year.
            remainder = parts[0] if len(parts) == 2 else str(mig_key)
            if remainder.startswith(animal_id + "_"):
                bio_year = remainder[len(animal_id) + 1:]
            else:
                bio_year = "all"
            seq_ud_by_year.setdefault(bio_year, {}).setdefault(label, {}).setdefault(animal_id, []).append(ud)

        if not seq_ud_by_season:
            return (
                _err_alert(
                    "No model results matched the selected seasons. "
                    f"Available sequence labels: {sorted({str(k).rsplit('_', 1)[-1] for k in results.keys()})}"
                ),
                "",
                None,
            )

        # Stack per individual: average each animal's sequences into one UD,
        # keyed by animal_id. ud_dict is animal-level, one entry per animal.
        ud_dict: dict[str, np.ndarray] = {}
        for season_label_tmp, animals in seq_ud_by_season.items():
            for animal_id, ud_list in animals.items():
                key = f"{animal_id}_{season_label_tmp}" if len(seq_ud_by_season) > 1 else animal_id
                if len(ud_list) == 1:
                    ud_dict[key] = ud_list[0]
                else:
                    ud_dict[key] = np.mean(np.stack(ud_list, axis=0), axis=0)

        # n_individuals = unique animals, not sequences.
        all_animals = set()
        for animals in seq_ud_by_season.values():
            all_animals.update(animals.keys())
        n_individuals = len(all_animals)
        user_levels = list(contour_levels)
        if n_individuals > 0:
            lvl_1animal = round(100.0 / n_individuals, 4)
            lvl_2animal = round(200.0 / n_individuals, 4)
            contour_levels = sorted(set([lvl_1animal, lvl_2animal] + user_levels))
        animal_band_levels = (
            {round(100.0 / n_individuals, 4): 1, round(200.0 / n_individuals, 4): 2}
            if n_individuals > 0 else {}
        )

        # Build min_individuals tuple: always include 2 and 3; optionally
        # add a user-defined X from the MinimumX UI.
        min_ind_list = [2, 3]
        if minimumx_on:
            try:
                x = int(minimumx_value or 4)
                x = max(1, min(x, n_individuals))
                if x not in min_ind_list:
                    min_ind_list.append(x)
            except (TypeError, ValueError):
                pass
        min_ind_tuple = tuple(sorted(min_ind_list))

        # ---- Diagnostics: how much overlap is actually there? ----
        # The "Area" contour level X means "cells where at least X% of sequences
        # had non-zero UD". For 232 sequences, 5% means ≥12 overlapping. If the
        # data is spatially scattered, even 5% may be unreachable; if smoothing
        # σ is large, the resulting peak can dip below the smallest contour
        # level. The numbers below let us tell the user exactly which is true.
        try:
            ud_stack_for_diag = np.stack(
                [arr.astype(np.float64) for arr in ud_dict.values()], axis=0
            )
            raw_presence_pct = (ud_stack_for_diag > 0).sum(axis=0) / len(ud_dict) * 100.0
            max_overlap_pct = float(raw_presence_pct.max())
            n_above = {
                level: int((raw_presence_pct >= level).sum())
                for level in contour_levels
            }
            del ud_stack_for_diag, raw_presence_pct
        except Exception:
            max_overlap_pct = float("nan")
            n_above = {}

        pop_config = {
            "seasons": seasons or [],
            "merge_order": list(merge_order_tuple),
            "contour_type": contour_type_norm,
            "contour_levels": contour_levels,
            "min_area_drop": float(min_drop) if min_drop not in (None, "") else 10000.0,
            "min_area_fill": float(min_fill) if min_fill not in (None, "") else 5000.0,
            "smooth": bool(smooth),
            # ksmooth smoothness (matches R's ksmooth_smoothness). Carried under
            # the legacy "smooth_bandwidth" key the population functions accept.
            "smooth_bandwidth": float(smooth_bw if smooth_bw not in (None, "") else 2),
            # 0 → skip stopover output entirely (checkbox unticked).
            "stopover_pct": (
                (float(stopover_pct) if stopover_pct not in (None, "") else 10.0)
                if stopover_on else 0.0
            ),
        }

        # Population USE (UD-based) and FOOTPRINT (overlap-based) contours.
        pop_use_gdf = calc_population_use(
            ud_dict=ud_dict,
            grid_meta=pop_grid,
            merge_order=merge_order_tuple,
            contour_type=contour_type_norm,
            contour_levels=contour_levels,
            min_area_drop=pop_config["min_area_drop"],
            min_area_fill=pop_config["min_area_fill"],
            simplify=pop_config["smooth"],
            smooth_bandwidth=pop_config["smooth_bandwidth"],
        )
        if footprint_dict:
            pop_foot_gdf = calc_population_footprint(
                footprint_dict=footprint_dict,
                grid_meta=pop_grid,
                contour_levels=contour_levels,
                min_area_drop=pop_config["min_area_drop"],
                min_area_fill=pop_config["min_area_fill"],
                simplify=pop_config["smooth"],
                smooth_bandwidth=pop_config["smooth_bandwidth"],
            )
        else:
            pop_foot_gdf = None

        # ----- Build every population product IN MEMORY (fully deferred) -------
        # Nothing is written to disk here. We compute the merged contours and the
        # per-season stacked set, stash them in _POP_OUTPUT_CACHE, and let Tab 5
        # flush the user-selected subset to ModelOutputs/ on demand. wrote_lines /
        # stacked_summary now describe what's READY to export, not what was saved.
        wrote_lines: list[str] = []
        stacked_summary: list[str] = []

        # Pull herd_id (DAU / Project) from the processing config so stacked
        # filenames follow <herd>_BBMM_<season>_<date>.<...>.
        herd_id = "Herd"
        try:
            if config_json:
                cfg_obj = json.loads(config_json) if isinstance(config_json, str) else config_json
                if isinstance(cfg_obj, dict) and cfg_obj.get("herd_id"):
                    herd_id = str(cfg_obj["herd_id"]).strip() or "Herd"
        except Exception:
            pass
        import datetime as _dt
        date_stamp = _dt.datetime.now().strftime("%m%d%y")

        # Build per-season animal-level UD dicts from the already-stacked data.
        ud_by_season: dict[str, dict[str, np.ndarray]] = {}
        for season_lbl, animals in seq_ud_by_season.items():
            season_key = season_lbl or "All"
            for animal_id, ud_list in animals.items():
                if len(ud_list) == 1:
                    stacked = ud_list[0]
                else:
                    stacked = np.mean(np.stack(ud_list, axis=0), axis=0)
                ud_by_season.setdefault(season_key, {})[animal_id] = stacked

        # cache_products: full descriptors WITH in-memory payloads (array/gdf).
        cache_products: list[dict] = []

        # Merged contour products.
        if pop_use_gdf is not None and len(pop_use_gdf) > 0:
            cache_products.append({
                "id": "contour::pop_use",
                "label": f"Population use contours ({len(pop_use_gdf)} polygons)",
                "category": "Merged contours", "rel_dir": "Contours",
                "filename": "Pop_use_contours.shp", "kind": "vector",
                "array": None, "gdf": pop_use_gdf,
            })
            wrote_lines.append(f"Contours/Pop_use_contours.shp  ({len(pop_use_gdf)} polygons)")
        if pop_foot_gdf is not None and len(pop_foot_gdf) > 0:
            cache_products.append({
                "id": "contour::footprint",
                "label": f"Population footprint contours ({len(pop_foot_gdf)} polygons)",
                "category": "Merged contours", "rel_dir": "Contours",
                "filename": "Footprint_contours.shp", "kind": "vector",
                "array": None, "gdf": pop_foot_gdf,
            })
            wrote_lines.append(f"Contours/Footprint_contours.shp  ({len(pop_foot_gdf)} polygons)")

        # Per-season stacked products + one combined "All" pass.
        def _collect_stacked(season_label: str, season_ud: dict[str, np.ndarray]) -> None:
            try:
                prods = compute_season_stacked_products(
                    ud_dict=season_ud, grid_meta=pop_grid,
                    herd_id=herd_id, season_label=season_label, date_stamp=date_stamp,
                    min_individuals=min_ind_tuple,
                    stopover_pct=pop_config["stopover_pct"],
                    min_area_drop=pop_config["min_area_drop"],
                    min_area_fill=pop_config["min_area_fill"],
                    simplify=pop_config["smooth"],
                    smooth_bandwidth=pop_config["smooth_bandwidth"],
                )
            except Exception as e:
                stacked_summary.append(f"⚠ {season_label} stacked compute failed: {e}")
                return
            for p in prods:
                cache_products.append({
                    "id": f"stacked::{season_label}::{p['key']}",
                    "label": p["label"],
                    "category": f"Stacked outputs — {season_label}",
                    "rel_dir": f"{herd_id}_Primary_Outputs", "filename": p["filename"],
                    "kind": p["kind"],
                    "array": p.get("array"), "gdf": p.get("gdf"),
                })
            stacked_summary.append(
                f"{season_label}: {len(prods)} products ({len(season_ud)} individuals)"
            )

        for season_label, season_ud_dict in ud_by_season.items():
            _collect_stacked(season_label, season_ud_dict)
        if len(ud_by_season) > 1:
            # Merge across seasons per individual: average each animal's
            # per-season UDs so the "All" raster has one layer per unique
            # animal, not one per animal-season.
            all_by_animal: dict[str, list[np.ndarray]] = {}
            for _season_ud in ud_by_season.values():
                for _aid, _arr in _season_ud.items():
                    all_by_animal.setdefault(_aid, []).append(_arr)
            ud_all: dict[str, np.ndarray] = {}
            for _aid, _arrs in all_by_animal.items():
                ud_all[_aid] = np.mean(np.stack(_arrs, axis=0), axis=0) if len(_arrs) > 1 else _arrs[0]
            _collect_stacked("All", ud_all)

        # ---- Year summaries (by bio-year) ----
        want_year_summaries = _MODEL_CACHE.get("want_year_summaries", False)
        year_summary_lines: list[str] = []
        if want_year_summaries:
            bio_years_sorted = sorted(
                [y for y in seq_ud_by_year if y != "all"],
                key=lambda v: (int(v) if v.isdigit() else 0, v),
            )
            for by in bio_years_sorted:
                yr_seasons = seq_ud_by_year[by]  # {season: {animal_id: [ud_arrays]}}
                yr_prefix = f"BioYear_{by}"

                for slbl, animals_in_season in yr_seasons.items():
                    season_yr_ud: dict[str, np.ndarray] = {}
                    for aid, ud_list in animals_in_season.items():
                        season_yr_ud[aid] = np.mean(np.stack(ud_list, axis=0), axis=0) if len(ud_list) > 1 else ud_list[0]
                    if season_yr_ud:
                        try:
                            prods = compute_season_stacked_products(
                                ud_dict=season_yr_ud, grid_meta=pop_grid,
                                herd_id=herd_id, season_label=slbl,
                                date_stamp=by,
                                min_individuals=min_ind_tuple,
                                stopover_pct=pop_config["stopover_pct"],
                                min_area_drop=pop_config["min_area_drop"],
                                min_area_fill=pop_config["min_area_fill"],
                                simplify=pop_config["smooth"],
                                smooth_bandwidth=pop_config["smooth_bandwidth"],
                            )
                            for p in prods:
                                cache_products.append({
                                    "id": f"yearsummary::{by}::{slbl}::{p['key']}",
                                    "label": f"{yr_prefix} {slbl}: {p['label']}",
                                    "category": f"Year summary — {by}",
                                    "rel_dir": f"YearSummaries/{by}",
                                    "filename": p["filename"], "kind": p["kind"],
                                    "array": p.get("array"), "gdf": p.get("gdf"),
                                })
                        except Exception:
                            pass

                all_season_yr_ud: dict[str, np.ndarray] = {}
                for slbl, animals_in_season in yr_seasons.items():
                    for aid, ud_list in animals_in_season.items():
                        mean_ud = np.mean(np.stack(ud_list, axis=0), axis=0) if len(ud_list) > 1 else ud_list[0]
                        if aid in all_season_yr_ud:
                            all_season_yr_ud[aid] = np.mean(
                                np.stack([all_season_yr_ud[aid], mean_ud], axis=0), axis=0
                            )
                        else:
                            all_season_yr_ud[aid] = mean_ud
                if all_season_yr_ud:
                    try:
                        prods = compute_season_stacked_products(
                            ud_dict=all_season_yr_ud, grid_meta=pop_grid,
                            herd_id=herd_id, season_label="All",
                            date_stamp=by,
                            min_individuals=min_ind_tuple,
                            stopover_pct=pop_config["stopover_pct"],
                            min_area_drop=pop_config["min_area_drop"],
                            min_area_fill=pop_config["min_area_fill"],
                            simplify=pop_config["smooth"],
                            smooth_bandwidth=pop_config["smooth_bandwidth"],
                        )
                        for p in prods:
                            cache_products.append({
                                "id": f"yearsummary::{by}::All::{p['key']}",
                                "label": f"{yr_prefix} All seasons: {p['label']}",
                                "category": f"Year summary — {by}",
                                "rel_dir": f"YearSummaries/{by}",
                                "filename": p["filename"], "kind": p["kind"],
                                "array": p.get("array"), "gdf": p.get("gdf"),
                            })
                    except Exception:
                        pass

                for aid, yr_ud in all_season_yr_ud.items():
                    total = yr_ud.sum()
                    if total > 0:
                        normed = (yr_ud / total).astype(np.float32)
                    else:
                        normed = yr_ud.astype(np.float32)
                    fname = f"{herd_id}_{aid}_{by}_combinedUD.tif"
                    cache_products.append({
                        "id": f"yearsummary::{by}::ind::{aid}",
                        "label": f"{yr_prefix} {aid} combined UD",
                        "category": f"Year summary — {by}",
                        "rel_dir": f"YearSummaries/{by}/IndividualUDs",
                        "filename": fname, "kind": "float32",
                        "array": normed,
                    })

                n_animals_yr = len(all_season_yr_ud)
                n_seasons_yr = len(yr_seasons)
                year_summary_lines.append(
                    f"Bio-year {by}: {n_seasons_yr} season(s), {n_animals_yr} individual(s)"
                )
        if year_summary_lines:
            stacked_summary.append("Year summaries: " + "; ".join(year_summary_lines))

        # Stash payloads in the process-local cache; build a JSON-safe manifest
        # (no arrays/gdfs) for the Tab 5 store so it can render the checkboxes.
        _POP_OUTPUT_CACHE.clear()
        _POP_OUTPUT_CACHE["products"] = cache_products
        _POP_OUTPUT_CACHE["grid_meta"] = pop_grid
        # Kept for Tab 5: detects "population options changed since last export"
        # to branch a new version, and feeds the population-branch manifest.
        _POP_OUTPUT_CACHE["config"] = pop_config
        export_manifest = [
            {"id": p["id"], "label": p["label"], "category": p["category"],
             "rel_dir": p["rel_dir"], "filename": p["filename"], "kind": p["kind"]}
            for p in cache_products
        ]

        _log_action(
            "GENERATE_POP_OUTPUTS",
            products=len(cache_products),
            use_polys=len(pop_use_gdf),
            foot_polys=len(pop_foot_gdf) if pop_foot_gdf is not None else 0,
            seasons=";".join(ud_by_season.keys()),
            herd_id=herd_id,
        )

        # Stash GeoJSON for Tab 5 map overlay + the export manifest that drives
        # the Tab 5 "select outputs to export" checkboxes.
        try:
            meta_json = json.dumps({
                "use": json.loads(pop_use_gdf.to_crs("EPSG:4326").to_json()) if len(pop_use_gdf) > 0 else None,
                "footprint": json.loads(pop_foot_gdf.to_crs("EPSG:4326").to_json()) if pop_foot_gdf is not None and len(pop_foot_gdf) > 0 else None,
                "config": pop_config,
                "export_manifest": export_manifest,
            }, default=str)
        except Exception:
            meta_json = json.dumps({"config": pop_config, "export_manifest": export_manifest})

        # Build the preview card: contour-by-area table for each surface.
        def _contour_table(gdf, title):
            if gdf is None or len(gdf) == 0:
                return html.Div([html.Strong(title), html.Span(" — no polygons", className="text-muted ms-2")])
            rows = []
            for _, r in gdf.sort_values("contour", ascending=False).iterrows():
                rows.append(html.Tr([
                    html.Td(f"{r['contour']:g}%"),
                    html.Td(f"{r['area_km2']:.2f} km²"),
                ]))
            return dbc.Card(dbc.CardBody([
                html.H6(title, className="text-info"),
                dbc.Table(
                    [html.Thead(html.Tr([html.Th("Contour"), html.Th("Area")])), html.Tbody(rows)],
                    bordered=False, hover=True, size="sm",
                    style={"color": "#E0E0E0"},
                ),
            ]), className="mb-2")

        wrote_card = None
        if wrote_lines:
            wrote_card = dbc.Card(dbc.CardBody([
                html.H6("Ready to export — Tab 5", className="text-success"),
                html.Ul([html.Li(line) for line in wrote_lines]),
                html.Small(
                    "Nothing has been written to disk yet. Go to Tab 5 → Export "
                    "to pick which outputs to save to ModelOutputs/.",
                    className="text-muted",
                ),
            ]), className="mb-2")

        stacked_card = None
        if stacked_summary:
            stacked_card = dbc.Card(dbc.CardBody([
                html.H6(f"Per-season stacked outputs ({herd_id}_Primary_Outputs/) — ready to export", className="text-info"),
                html.Ul([html.Li(line) for line in stacked_summary]),
                html.Small(
                    "For each season: mean UD .tif, _all isopleths .shp, "
                    "_minimum1/_minimum2/_minimum3 (overlap thresholds), _top10/_top20 (UD volume), "
                    f"_stopover (top {pop_config['stopover_pct']:g}% of mean-UD volume, "
                    "Migration Mapper-style). Select and save these in Tab 5.",
                    className="text-muted",
                ),
            ]), className="mb-2")

        preview_children = []
        if wrote_card is not None:
            preview_children.append(wrote_card)
        if stacked_card is not None:
            preview_children.append(stacked_card)
        preview_children.append(_contour_table(pop_use_gdf, "Population Use Contours"))
        preview_children.append(_contour_table(pop_foot_gdf, "Population Footprint Contours"))
        preview = html.Div(preview_children)

        # Build a "what's actually possible" line so the user can pick sensible
        # levels rather than guessing.
        n_use = len(pop_use_gdf)
        n_foot = len(pop_foot_gdf) if pop_foot_gdf is not None else 0

        diag_parts = []
        if not np.isnan(max_overlap_pct):
            diag_parts.append(f"max overlap {max_overlap_pct:.1f}%")
            if n_above:
                buckets = ", ".join(
                    f"≥{int(lvl)}%: {cnt:,} cells" for lvl, cnt in sorted(n_above.items())
                )
                diag_parts.append(f"cells {buckets}")
        diag_line = " | ".join(diag_parts) if diag_parts else ""

        def _write_pop_log(result_str: str) -> None:
            lvl_strs = []
            for lvl in sorted(set(contour_levels)):
                tag = animal_band_levels.get(round(lvl, 4))
                lvl_strs.append(f"{lvl:g}%" + (f" (>={tag} animal{'s' if tag and tag > 1 else ''})" if tag else ""))
            date_range = _MODEL_CACHE.get("input_date_range")
            lines = [
                f"Input data date range: {date_range[0]} — {date_range[1]}" if date_range else "Input data date range: unknown",
                f"Seasons merged: {', '.join(seasons) if seasons else 'all'}",
                f"Merge order: {pop_config['merge_order']}",
                f"Contour type: {pop_config['contour_type']}",
                f"Contour levels: {', '.join(lvl_strs)}",
                f"min_area_drop: {pop_config['min_area_drop']:g} m2   min_area_fill: {pop_config['min_area_fill']:g} m2",
                f"Smoothing (ksmooth): {'on' if pop_config['smooth'] else 'off'}"
                + (f", smoothness={pop_config['smooth_bandwidth']:g}" if pop_config['smooth'] else ""),
                f"Stopover density: top {pop_config['stopover_pct']:g}% of mean UD",
                f"Individuals: {n_individuals} (from {n_sequences} sequences)" + (f" ({n_skipped} skipped for errors)" if n_skipped else ""),
                f"Result: {result_str}",
                f"Run time: {(_dt_pop.datetime.now() - _pop_start).total_seconds():.1f} s",
            ]
            if _ACTIVE_WORKDIR is not None:
                lines.append(f"Export target (on Tab 5): ModelOutputs/{_workdir_version().name}/")
                for wl in wrote_lines:
                    lines.append(f"    {wl}")
                for bs in stacked_summary:
                    lines.append(f"    {herd_id}_Primary_Outputs/{bs}")
            _append_processing_log(lines, header="POPULATION OUTPUTS")

        if n_use == 0 and n_foot == 0:
            # Help the user diagnose: was overlap too low, or did smoothing
            # eat the peaks?
            suggestion: list[str] = []
            if max_overlap_pct < min(contour_levels):
                suggestion.append(
                    f"Maximum cell overlap is {max_overlap_pct:.1f}% — every contour level you set "
                    f"({', '.join(f'{int(c)}%' for c in contour_levels)}) is above that, so the proportion "
                    f"grid never crosses any threshold."
                )
                suggestion.append(
                    "Try contour levels at or below the max overlap (e.g. "
                    f"\"{max(1, int(max_overlap_pct * 0.2))}, {max(2, int(max_overlap_pct * 0.4))}, "
                    f"{max(3, int(max_overlap_pct * 0.6))}, {max(4, int(max_overlap_pct * 0.8))}\")."
                )
            if pop_config["smooth"]:
                suggestion.append(
                    "Gaussian smoothing attenuates narrow peaks — if your data has scattered overlap "
                    f"rather than broad plateaus, try turning Smoothing off, or lowering bandwidth σ "
                    f"(currently {pop_config['smooth_bandwidth']})."
                )
            _write_pop_log(f"0 contours generated. {diag_line}")
            return (
                dbc.Alert(
                    [
                        html.Strong("0 contours generated. "),
                        html.Br(),
                        html.Div(diag_line, className="small text-muted mb-1") if diag_line else None,
                        html.Ul([html.Li(s) for s in suggestion]) if suggestion else None,
                    ],
                    color="warning",
                    dismissable=True,
                ),
                preview,
                meta_json,
            )

        msg = (
            f"Population outputs generated — {n_use} use contours, {n_foot} footprint contours "
            f"from {len(ud_dict)} sequences"
            + (f" ({n_skipped} skipped for errors)" if n_skipped else "")
            + ("." if not diag_line else f". {diag_line}.")
        )
        _write_pop_log(f"SUCCESS - {n_use} use contours, {n_foot} footprint contours")
        return _ok_alert(msg), preview, meta_json

    except Exception as exc:
        _append_processing_log(
            [f"Result: FAILED - {exc}",
             f"Run time: {(_dt_pop.datetime.now() - _pop_start).total_seconds():.1f} s"],
            header="POPULATION OUTPUTS",
        )
        return _err_alert(f"Population output error: {exc}\n{traceback.format_exc()[:600]}"), "", None


# ===========================================================================
# Callbacks — Tab 5: Map & Export
# ===========================================================================

# Anchor colours for a viridis-like ramp used to colour continuous (UD) rasters.
_VIRIDIS_STOPS = [
    (0.0, (68, 1, 84)), (0.25, (59, 82, 139)), (0.5, (33, 145, 140)),
    (0.75, (94, 201, 98)), (1.0, (253, 231, 37)),
]


def _ramp_rgb(t: np.ndarray, cmap: str = "viridis") -> np.ndarray:
    """Map t∈[0,1] (HxW) to an RGB uint8 array (HxWx3).

    ``cmap="gray"`` gives a black→white grayscale ramp; anything else uses the
    viridis anchors.
    """
    t = np.clip(t, 0.0, 1.0)
    if cmap == "gray":
        g = (t * 255.0).astype(np.uint8)
        return np.dstack([g, g, g])
    stops = _VIRIDIS_STOPS
    r = np.zeros_like(t); g = np.zeros_like(t); b = np.zeros_like(t)
    for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= t0) & (t <= t1)
        f = np.where(t1 > t0, (t - t0) / (t1 - t0), 0.0)
        for ch, arr in zip((0, 1, 2), (r, g, b)):
            arr[m] = c0[ch] + (c1[ch] - c0[ch]) * f[m]
    return np.dstack([r, g, b]).astype(np.uint8)


def _png_encode_rgba(rgba: np.ndarray) -> bytes:
    """Minimal dependency-free PNG encoder for an HxWx4 uint8 RGBA array.
    (No Pillow/imageio installed; GDAL's PNG driver is CreateCopy-only.)"""
    import zlib, struct
    h, w = rgba.shape[0], rgba.shape[1]

    def _chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    # Prepend a 0 (no-filter) byte to each scanline, then deflate.
    filtered = np.zeros((h, w * 4 + 1), dtype=np.uint8)
    filtered[:, 1:] = rgba.reshape(h, w * 4)
    idat = zlib.compress(filtered.tobytes(), 6)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit, colour type 6 = RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b""))


# Cache of expensive (read + reproject + PNG-encode) overlay builds, keyed by
# (path, file-mtime, cmap). Lets the opacity slider rebuild the LayerGroup
# children cheaply without re-warping every raster on each drag step.
_OVERLAY_CACHE: dict[tuple, Any] = {}


def _raster_to_overlay_cached(tif_path: "Path", cmap: str):
    """Memoised :func:`_raster_to_overlay`. Returns the same tuple (or None)."""
    try:
        mtime = tif_path.stat().st_mtime
    except OSError:
        return None
    key = (str(tif_path), mtime, cmap)
    if key not in _OVERLAY_CACHE:
        if len(_OVERLAY_CACHE) > 256:        # crude cap; outputs are session-scoped
            _OVERLAY_CACHE.clear()
        _OVERLAY_CACHE[key] = _raster_to_overlay(tif_path, cmap=cmap)
    return _OVERLAY_CACHE[key]


def _raster_to_overlay(tif_path: "Path", cmap: str = "viridis"):
    """Read a GeoTIFF, reproject to EPSG:4326, colour it (continuous *cmap*
    ramp for float UDs; a solid mask colour for integer footprints), and return
    ``(data_uri_png, bounds[[S,W],[N,E]], info_str)`` for a dl.ImageOverlay —
    or ``None`` if the raster can't be read/has no data. *cmap* is "viridis" or
    "gray"."""
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.transform import array_bounds

    with rasterio.open(tif_path) as src:
        if src.count < 1:
            return None
        dst_crs = "EPSG:4326"
        dt, dw, dh = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        if not dw or not dh:
            return None
        src_arr = src.read(1)
        dst = np.zeros((dh, dw), dtype=src_arr.dtype)
        reproject(
            source=src_arr, destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=dt, dst_crs=dst_crs, resampling=Resampling.nearest,
        )
        nodata = src.nodata
        is_float = np.issubdtype(src_arr.dtype, np.floating)

    arr = dst.astype(np.float64)
    valid = np.isfinite(arr)
    if nodata is not None:
        valid &= (arr != nodata)
    valid &= (arr > 0)
    if not valid.any():
        return None

    rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
    if is_float:
        vmax = float(np.percentile(arr[valid], 98)) or float(arr[valid].max())
        if vmax <= 0:
            vmax = float(arr[valid].max()) or 1.0
        norm = np.clip(arr / vmax, 0.0, 1.0)
        rgb = _ramp_rgb(norm, cmap)
        rgba[..., :3] = rgb
        # Valid cells are fully opaque in the PNG; the ImageOverlay's opacity
        # slider is the single, linear transparency control (so opacity=1 reads
        # as 100% opaque). Low vs high probability is shown by colour, not by
        # baked-in per-pixel alpha. Cells with no data stay transparent so the
        # basemap shows through outside the corridor.
        rgba[..., 3] = np.where(valid, 255, 0)
        info = f"UD raster · max≈{arr[valid].max():.3g} · {arr.shape[1]}×{arr.shape[0]} px"
    else:
        # Categorical mask → a solid colour where non-zero. White for the
        # grayscale scheme, orange for viridis. Fully opaque; opacity slider
        # controls transparency.
        mask_rgb = (235, 235, 235) if cmap == "gray" else (230, 126, 34)
        rgba[..., 0] = mask_rgb[0]; rgba[..., 1] = mask_rgb[1]; rgba[..., 2] = mask_rgb[2]
        rgba[..., 3] = np.where(valid, 255, 0)
        info = f"Footprint/mask · {int(valid.sum())} cells · {arr.shape[1]}×{arr.shape[0]} px"

    png = _png_encode_rgba(rgba)
    data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    west, south, east, north = array_bounds(arr.shape[0], arr.shape[1], dt)
    return data_uri, [[south, west], [north, east]], info


# Raster-bearing output subfolders, in display order. category values are
# version-qualified ("V{n}/<sub>") so the user can view any version's rasters.
_RASTER_CATEGORIES_STATIC = [
    ("UDs", "UD (per sequence)"),
    ("IndividualUDs", "Individual UD"),
    ("RangeUDs", "Range UD"),
    ("YearSummaries", "Year summary"),
    ("LineBuffer", "Line Buffer"),
]

def _primary_output_dir(vdir: Path) -> tuple[Path, str] | None:
    """Find the primary outputs folder — either {Herd}_Primary_Outputs (new)
    or BBMM_Output (legacy). Returns (path, folder_name) or None."""
    for d in sorted(vdir.iterdir()) if vdir.is_dir() else []:
        if d.is_dir() and d.name.endswith("_Primary_Outputs"):
            return d, d.name
    legacy = vdir / "BBMM_Output"
    if legacy.is_dir():
        return legacy, "BBMM_Output"
    return None


@app.callback(
    Output("raster-tree-container", "children"),
    Input("main-tabs", "active_tab"),
    Input("store-model-results", "data"),
    Input("store-pop-outputs", "data"),
    Input("btn-clear-raster-overlay", "n_clicks"),
    prevent_initial_call=True,
)
def build_raster_tree(active_tab, _model_results, _pop, _clear):
    """Build an ArcGIS-style collapsible tree of raster categories. Each
    category is a clickable header with a triangle; expanding it reveals
    checkboxes for individual .tif files."""
    if ctx.triggered_id == "btn-clear-raster-overlay":
        pass  # rebuild tree with nothing checked

    if _ACTIVE_WORKDIR is None:
        return html.Span("Set a working directory first.", className="text-muted")
    try:
        mo = _workdir_outputs()
    except Exception:
        return html.Span("No outputs found.", className="text-muted")

    groups = []
    for v in _list_versions():
        vdir = _resolve_version_dir(_ACTIVE_WORKDIR, v)
        # Static categories
        for sub, label in _RASTER_CATEGORIES_STATIC:
            d = vdir / sub
            if not d.is_dir():
                continue
            tifs = sorted(d.rglob("*.tif"), key=lambda p: p.name.lower())
            if not tifs:
                continue
            group_key = f"{vdir.name}/{sub}"
            group_label = f"{vdir.name} · {label}"
            options = [
                {"label": t.stem, "value": str(t)} for t in tifs
            ]
            groups.append((group_key, group_label, options))
        # Primary outputs folder (dynamic name or legacy BBMM_Output)
        prim = _primary_output_dir(vdir)
        if prim:
            prim_dir, prim_name = prim
            tifs = sorted(prim_dir.rglob("*.tif"), key=lambda p: p.name.lower())
            if tifs:
                groups.append((
                    f"{vdir.name}/{prim_name}",
                    f"{vdir.name} · Population (stacked)",
                    [{"label": t.stem, "value": str(t)} for t in tifs],
                ))

    if _POP_OUTPUT_CACHE.get("products"):
        mem_groups: dict[str, list] = {}
        for p in _POP_OUTPUT_CACHE["products"]:
            if p.get("kind") in ("count", "float32", "uint8") and p.get("array") is not None:
                cat = p.get("category", "Population")
                mem_groups.setdefault(cat, []).append(
                    {"label": p["filename"].replace(".tif", ""), "value": f"__mem__::{p['id']}"}
                )
        for cat, opts in mem_groups.items():
            groups.append((f"__mem__{cat}", f"(in memory) {cat}", opts))

    if not groups:
        return html.Span("No raster outputs found.", className="text-muted")

    tree_items = []
    for group_key, group_label, options in groups:
        safe_key = group_key.replace("/", "_").replace(" ", "_")
        header = html.Div(
            [
                html.Span(
                    "▶ ",
                    id={"type": "raster-tree-arrow", "index": safe_key},
                    style={"cursor": "pointer", "userSelect": "none",
                           "display": "inline-block", "width": "1em",
                           "transition": "transform 0.15s"},
                ),
                html.Span(
                    group_label,
                    style={"cursor": "pointer", "fontWeight": "600"},
                    id={"type": "raster-tree-label", "index": safe_key},
                ),
                html.Span(
                    f"  ({len(options)})",
                    className="text-muted",
                    style={"fontSize": "0.75rem"},
                ),
            ],
            id={"type": "raster-tree-header", "index": safe_key},
            n_clicks=0,
            style={"padding": "3px 0", "borderBottom": "1px solid #333"},
        )
        body = dbc.Collapse(
            dbc.Checklist(
                id={"type": "raster-tree-checklist", "index": safe_key},
                options=options,
                value=[],
                style={"paddingLeft": "1.2em", "fontSize": "0.78rem"},
                labelStyle={"display": "block", "padding": "1px 0"},
                inputStyle={"marginRight": "6px"},
            ),
            id={"type": "raster-tree-collapse", "index": safe_key},
            is_open=False,
        )
        tree_items.append(html.Div([header, body]))

    return tree_items


@app.callback(
    Output({"type": "raster-tree-collapse", "index": dash.MATCH}, "is_open"),
    Output({"type": "raster-tree-arrow", "index": dash.MATCH}, "children"),
    Input({"type": "raster-tree-header", "index": dash.MATCH}, "n_clicks"),
    State({"type": "raster-tree-collapse", "index": dash.MATCH}, "is_open"),
    prevent_initial_call=True,
)
def toggle_raster_tree_group(n_clicks, is_open):
    if not n_clicks:
        raise PreventUpdate
    new_open = not is_open
    return new_open, "▼ " if new_open else "▶ "


@app.callback(
    Output("raster-overlay-file", "data"),
    Input({"type": "raster-tree-checklist", "index": dash.ALL}, "value"),
    prevent_initial_call=True,
)
def aggregate_raster_selections(all_values):
    selected = []
    for vals in (all_values or []):
        selected.extend(vals or [])
    return selected


def _render_mem_product(product_id: str, cmap: str = "viridis"):
    """Render an in-memory population product as a map overlay, returning
    the same (data_uri, bounds, info) tuple as _raster_to_overlay."""
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.transform import array_bounds

    products = _POP_OUTPUT_CACHE.get("products", [])
    grid_meta = _POP_OUTPUT_CACHE.get("grid_meta")
    if not grid_meta:
        return None
    prod = next((p for p in products if p.get("id") == product_id), None)
    if prod is None or prod.get("array") is None:
        return None

    from rasterio.crs import CRS
    src_crs = CRS.from_user_input(grid_meta["crs"])
    transform = grid_meta["transform"]
    shape_rc = grid_meta["shape"]
    src_arr = prod["array"].astype(np.float64)

    dst_crs = "EPSG:4326"
    dt, dw, dh = calculate_default_transform(
        src_crs, dst_crs, shape_rc[1], shape_rc[0],
        *array_bounds(shape_rc[0], shape_rc[1], transform),
    )
    if not dw or not dh:
        return None
    dst = np.zeros((dh, dw), dtype=np.float64)
    reproject(
        source=src_arr, destination=dst,
        src_transform=transform, src_crs=src_crs,
        dst_transform=dt, dst_crs=dst_crs, resampling=Resampling.nearest,
    )
    bounds_lrbt = array_bounds(dh, dw, dt)
    overlay_bounds = [[bounds_lrbt[1], bounds_lrbt[0]], [bounds_lrbt[3], bounds_lrbt[2]]]

    valid = np.isfinite(dst) & (dst != 0)
    if not valid.any():
        return None
    vmin, vmax = dst[valid].min(), dst[valid].max()
    if vmax <= vmin:
        vmax = vmin + 1.0

    normed = np.clip((dst - vmin) / (vmax - vmin), 0, 1)
    rgb = _ramp_rgb(normed, cmap)
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])

    png_bytes = _png_encode_rgba(rgba)
    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
    info = f"{prod['filename']} — range {vmin:.4g}–{vmax:.4g}"
    return data_uri, overlay_bounds, info


@app.callback(
    Output("raster-overlay-group", "children"),
    Output("raster-overlay-info", "children"),
    Input("raster-overlay-file", "data"),
    Input("raster-overlay-opacity", "value"),
    Input("raster-overlay-cmap", "value"),
    Input("btn-clear-raster-overlay", "n_clicks"),
    prevent_initial_call=True,
)
def render_raster_overlays(tif_paths, opacity, cmap, _clear_clicks):
    """Render every selected .tif as a stacked set of coloured ImageOverlays.
    Per-file PNG builds are memoised so dragging the opacity slider only rebuilds
    the (cheap) component tree, not the warp/encode."""
    op = float(opacity if opacity is not None else 0.7)
    if ctx.triggered_id == "btn-clear-raster-overlay":
        return [], ""
    paths = tif_paths or []
    if not paths:
        return [], ""
    cmap = cmap or "viridis"
    children, infos, skipped = [], [], 0
    for p in paths:
        if str(p).startswith("__mem__::"):
            result = _render_mem_product(str(p)[len("__mem__::"):], cmap)
        else:
            try:
                result = _raster_to_overlay_cached(Path(p), cmap)
            except Exception:
                result = None
        if result is None:
            skipped += 1
            continue
        data_uri, bounds, info = result
        children.append(dl.ImageOverlay(url=data_uri, bounds=bounds, opacity=op))
        infos.append(f"• {info}")
    if not children:
        return [], html.Span("Selected raster(s) have no displayable data.", className="text-muted")
    note = f"{len(children)} raster(s) shown" + (f", {skipped} skipped (no data)" if skipped else "")
    detail = html.Div(
        [html.Span(note, className="fw-bold d-block")] + [html.Span(s, className="d-block") for s in infos[:12]]
        + ([html.Span(f"…and {len(infos) - 12} more", className="d-block")] if len(infos) > 12 else []),
        className="text-muted",
    )
    return children, detail


# Distinct outline colours cycled across stacked vector layers.
_VECTOR_PALETTE = [
    "#E63946", "#457B9D", "#2A9D8F", "#E9C46A", "#F4A261", "#9B5DE5",
    "#00BBF9", "#FB5607", "#8AC926", "#FF006E", "#3A86FF", "#FFBE0B",
]
# Cache of (path, mtime) → GeoJSON FeatureCollection in EPSG:4326.
_VECTOR_CACHE: dict[tuple, Any] = {}


def _vector_file_to_geojson(path: "Path"):
    """Read a .shp/.geojson, reproject to EPSG:4326, return a GeoJSON dict (or
    None). Memoised by (path, mtime). On first load of a .shp, writes a
    .display.geojson companion so subsequent loads skip GeoPandas entirely."""
    import time as _time
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = (str(path), mtime)
    if key in _VECTOR_CACHE:
        return _VECTOR_CACHE[key]

    t0 = _time.perf_counter()
    companion = path.with_suffix(".display.geojson")

    # Fast path: load pre-baked companion (already EPSG:4326, trimmed columns).
    if companion.is_file() and companion.stat().st_mtime >= mtime:
        try:
            with open(companion, "r", encoding="utf-8") as fh:
                result = json.load(fh)
            t1 = _time.perf_counter()
            print(f"VECTOR PERF [{path.name}]: companion json.load {t1 - t0:.3f}s")
            if len(_VECTOR_CACHE) > 128:
                _VECTOR_CACHE.clear()
            _VECTOR_CACHE[key] = result
            return result
        except Exception:
            pass

    # Slow path: read with GeoPandas, reproject, trim, serialise.
    _MAX_DISPLAY_POINTS = 15_000
    try:
        import geopandas as gpd_local
        gdf = gpd_local.read_file(str(path))
        t1 = _time.perf_counter()
        print(f"VECTOR PERF [{path.name}]: read_file {t1 - t0:.3f}s ({len(gdf)} rows)")
        if gdf.empty:
            result = None
        else:
            if gdf.crs is not None and not gdf.crs.equals("EPSG:4326"):
                gdf = gdf.to_crs(epsg=4326)
                t2 = _time.perf_counter()
                print(f"VECTOR PERF [{path.name}]: to_crs {t2 - t1:.3f}s")
            else:
                t2 = t1
            # Downsample large point layers for display performance.
            geom_type = gdf.geometry.iloc[0].geom_type if len(gdf) else ""
            if geom_type in ("Point", "MultiPoint") and len(gdf) > _MAX_DISPLAY_POINTS:
                import numpy as np
                step = len(gdf) / _MAX_DISPLAY_POINTS
                idx = np.round(np.arange(0, len(gdf), step)).astype(int)
                idx = idx[idx < len(gdf)]
                print(f"VECTOR PERF [{path.name}]: downsampled {len(gdf)} → {len(idx)} points")
                gdf = gdf.iloc[idx]
            keep = [c for c in gdf.columns if c == gdf.geometry.name
                    or gdf[c].dtype.kind in "ifbO"]
            _MAX_DISPLAY_COLS = 8
            geom_name = gdf.geometry.name
            if len(gdf) > 2000 and sum(1 for c in keep if c != geom_name) > _MAX_DISPLAY_COLS:
                _PREFERRED = ["animal_id", "id_bio_year", "timestamp", "seq_id",
                              "sequence", "mig_seq", "problem", "mortality_flag"]
                non_geom = [c for c in keep if c != geom_name]
                priority = [c for c in _PREFERRED if c in non_geom]
                rest = [c for c in non_geom if c not in priority]
                keep = [geom_name] + (priority + rest)[:_MAX_DISPLAY_COLS]
            json_str = gdf[keep].to_json()
            result = json.loads(json_str)
            t3 = _time.perf_counter()
            print(f"VECTOR PERF [{path.name}]: to_json {t3 - t2:.3f}s, total {t3 - t0:.3f}s")
            try:
                with open(companion, "w", encoding="utf-8") as fh:
                    fh.write(json_str)
                print(f"VECTOR PERF [{path.name}]: wrote companion {companion.name}")
            except Exception:
                pass
    except Exception:
        result = None
    if len(_VECTOR_CACHE) > 128:
        _VECTOR_CACHE.clear()
    _VECTOR_CACHE[key] = result
    return result


@app.callback(
    Output("vector-tree-container", "children"),
    Input("main-tabs", "active_tab"),
    Input("store-model-results", "data"),
    Input("store-pop-outputs", "data"),
    Input("btn-refresh-vectors", "n_clicks"),
    prevent_initial_call=True,
)
def build_vector_tree(active_tab, _model, _pop, _refresh):
    """Build an ArcGIS-style collapsible tree of vector files, grouped by
    subfolder under ModelOutputs/."""
    if _ACTIVE_WORKDIR is None:
        return html.Span("Set a working directory first.", className="text-muted")
    try:
        root = _workdir_outputs()
    except Exception:
        return html.Span("No outputs found.", className="text-muted")
    if not root.is_dir():
        return html.Span("No outputs found.", className="text-muted")

    vecs = sorted(
        [p for p in root.rglob("*")
         if p.suffix.lower() in {".shp", ".geojson"}
         and not p.name.endswith(".display.geojson")],
        key=lambda p: str(p).lower(),
    )
    if not vecs:
        return html.Span("No vector files found.", className="text-muted")

    from collections import OrderedDict
    grouped: OrderedDict[str, list] = OrderedDict()
    for p in vecs:
        rel = p.relative_to(root)
        folder = str(rel.parent) if str(rel.parent) != "." else "(root)"
        grouped.setdefault(folder, []).append(p)

    tree_items = []
    for folder, files in grouped.items():
        safe_key = "vec_" + folder.replace("/", "_").replace("\\", "_").replace(" ", "_")
        header = html.Div(
            [
                html.Span(
                    "▶ ",
                    id={"type": "vector-tree-arrow", "index": safe_key},
                    style={"cursor": "pointer", "userSelect": "none",
                           "display": "inline-block", "width": "1em",
                           "transition": "transform 0.15s"},
                ),
                html.Span(
                    folder,
                    style={"cursor": "pointer", "fontWeight": "600"},
                ),
                html.Span(
                    f"  ({len(files)})",
                    className="text-muted",
                    style={"fontSize": "0.75rem"},
                ),
            ],
            id={"type": "vector-tree-header", "index": safe_key},
            n_clicks=0,
            style={"padding": "3px 0", "borderBottom": "1px solid #333"},
        )
        options = [{"label": p.stem, "value": str(p)} for p in files]
        body = dbc.Collapse(
            dbc.Checklist(
                id={"type": "vector-tree-checklist", "index": safe_key},
                options=options,
                value=[],
                style={"paddingLeft": "1.2em", "fontSize": "0.78rem"},
                labelStyle={"display": "block", "padding": "1px 0"},
                inputStyle={"marginRight": "6px"},
            ),
            id={"type": "vector-tree-collapse", "index": safe_key},
            is_open=False,
        )
        tree_items.append(html.Div([header, body]))

    return tree_items


@app.callback(
    Output({"type": "vector-tree-collapse", "index": dash.MATCH}, "is_open"),
    Output({"type": "vector-tree-arrow", "index": dash.MATCH}, "children"),
    Input({"type": "vector-tree-header", "index": dash.MATCH}, "n_clicks"),
    State({"type": "vector-tree-collapse", "index": dash.MATCH}, "is_open"),
    prevent_initial_call=True,
)
def toggle_vector_tree_group(n_clicks, is_open):
    if not n_clicks:
        raise PreventUpdate
    new_open = not is_open
    return new_open, "▼ " if new_open else "▶ "


@app.callback(
    Output("vector-overlay-files", "data"),
    Input({"type": "vector-tree-checklist", "index": dash.ALL}, "value"),
    prevent_initial_call=True,
)
def aggregate_vector_selections(all_values):
    selected = []
    for vals in (all_values or []):
        selected.extend(vals or [])
    return selected


@app.callback(
    Output("vector-overlay-group", "children"),
    Output("vector-overlay-info", "children"),
    Input("vector-overlay-files", "data"),
    Input("vector-overlay-opacity", "value"),
    prevent_initial_call=True,
)
def render_vector_overlays(paths, fill_opacity):
    """Draw each selected vector file as its own coloured dl.GeoJSON layer."""
    paths = paths or []
    if not paths:
        return [], ""
    fo = float(fill_opacity if fill_opacity is not None else 0.35)
    children, skipped, shown = [], 0, []
    for i, p in enumerate(paths):
        gj = _vector_file_to_geojson(Path(p))
        if not gj or not gj.get("features"):
            skipped += 1
            continue
        color = _VECTOR_PALETTE[i % len(_VECTOR_PALETTE)]
        has_points = any(
            f.get("geometry", {}).get("type", "") in ("Point", "MultiPoint")
            for f in gj.get("features", [])
        )
        if has_points:
            for f in gj["features"]:
                f.setdefault("properties", {})["_color"] = color
            children.append(
                dl.GeoJSON(
                    data=gj,
                    options=dict(pointToLayer=_vec_point_style),
                )
            )
        else:
            children.append(
                dl.GeoJSON(
                    data=gj,
                    style={"color": color, "weight": 2, "fillColor": color, "fillOpacity": fo},
                )
            )
        shown.append((Path(p).name, color, len(gj["features"])))
    if not children:
        return [], html.Span("Selected vector file(s) had no readable features.", className="text-muted")
    note = f"{len(children)} layer(s) shown" + (f", {skipped} skipped" if skipped else "")
    legend = [html.Span(note, className="fw-bold d-block")] + [
        html.Span(
            [html.Span("■ ", style={"color": c}), f"{name} ({n})"],
            className="d-block",
        )
        for name, c, n in shown[:12]
    ]
    if len(shown) > 12:
        legend.append(html.Span(f"…and {len(shown) - 12} more", className="d-block"))
    return children, html.Div(legend, className="text-muted")


@app.callback(
    Output("map-geojson-contours", "data"),
    Input("map-layers", "value"),
    Input("store-pop-outputs", "data"),
    prevent_initial_call=True,
)
def update_map_contours(active_layers, pop_json):
    """Feed the Tab-5 contours layer from store-pop-outputs (set by Tab 4's
    Generate Population Outputs OR by Load Previous Results). Without this
    callback the layer was never populated — toggling "Population Use Contours"
    / "Footprint Contours" did nothing. Merges the two selected layers into one
    FeatureCollection, tagging each feature with a per-layer ``_color`` that the
    contourStyle JS reads."""
    empty = {"type": "FeatureCollection", "features": []}
    if not pop_json:
        return empty
    try:
        obj = json.loads(pop_json) if isinstance(pop_json, str) else pop_json
    except Exception:
        return empty
    active = active_layers or []
    feats: list[dict] = []

    def _tag(fc, color):
        out = []
        for f in (fc or {}).get("features", []):
            f = dict(f)
            props = dict(f.get("properties") or {})
            props["_color"] = color
            props["_layer"] = color  # only used for debugging
            f["properties"] = props
            out.append(f)
        return out

    # "pop_contours" = population USE; "footprints" = footprint overlap contours.
    if "pop_contours" in active:
        feats += _tag(obj.get("use"), "#E63946")
    if "footprints" in active:
        feats += _tag(obj.get("footprint"), "#457B9D")
    return {"type": "FeatureCollection", "features": feats}


# Base-layer toggle — actually swap the tile source. Previously the radio
# existed but nothing read it (the TileLayer url was hardcoded to satellite),
# so clicking "Topographic" did nothing.
_BASEMAP_TILES = {
    "esri": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Esri — World Imagery",
    ),
    "topo": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        "Esri — World Topographic",
    ),
}


@app.callback(
    Output("base-tile-layer", "url"),
    Output("base-tile-layer", "attribution"),
    Input("map-base-layer", "value"),
    prevent_initial_call=False,
)
def switch_basemap(base):
    url, attr = _BASEMAP_TILES.get(base, _BASEMAP_TILES["esri"])
    return url, attr


# Tab 5's dash-leaflet map (main-map) initialises inside the hidden tab pane
# (dbc.Tabs renders all panes at load, inactive ones display:none), so Leaflet
# measures a 0x0 container and never draws tiles. When the tab becomes visible,
# Leaflet doesn't re-measure on its own — only a window 'resize' event triggers
# its invalidateSize(). That's why the map appeared only after opening DevTools
# (which fires a resize). This fires a few resize events once Tab 5 is shown so
# the map lays out correctly without any manual intervention.
app.clientside_callback(
    """
    function(active_tab) {
        if (active_tab === 'tab-5') {
            [60, 250, 600].forEach(function(d) {
                setTimeout(function() {
                    window.dispatchEvent(new Event('resize'));
                }, d);
            });
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("main-map", "id"),
    Input("main-tabs", "active_tab"),
    prevent_initial_call=True,
)


@app.callback(
    Output("map-geojson-points", "data"),
    Output("map-geojson-tracks", "data"),
    Input("store-processed-data", "data"),
    Input("store-migtime-table", "data"),
    Input("map-layers", "value"),
    prevent_initial_call=True,
)
def update_map_layers(processed_json, migtime_json, active_layers):
    """Build GeoJSON overlays for the map — vectorized for speed.

    Two output layers (points + tracks); footprint/pop-contour layers are
    written by a separate callback (not shown here) since they come from
    _MODEL_CACHE / store-pop-outputs.

    Subsample budgets: points capped at 5,000 features, per-track
    LineStrings capped at 2,000 vertices. Both via numpy strided slicing
    (`::step`) so we keep the deterministic visual envelope (start, end,
    rough trajectory) without sending 50k+ features through dash-leaflet.
    """
    empty = {"type": "FeatureCollection", "features": []}
    points_geojson = empty
    tracks_geojson = empty.copy()

    if not processed_json:
        return points_geojson, tracks_geojson

    try:
        df = _json_to_df(processed_json, "processed")
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        has_coords = "lon" in df.columns and "lat" in df.columns
        if not has_coords:
            return points_geojson, tracks_geojson

        valid = df.dropna(subset=["lon", "lat"])

        if "raw_points" in (active_layers or []):
            n = len(valid)
            step = max(1, n // 5000)
            sample = valid.iloc[::step]
            lons = np.round(sample["lon"].values, 5)
            lats = np.round(sample["lat"].values, 5)
            problems = sample["problem"].values.astype(int) if "problem" in sample.columns else np.zeros(len(sample), dtype=int)
            morts = sample["mortality_flag"].values.astype(int) if "mortality_flag" in sample.columns else np.zeros(len(sample), dtype=int)

            features = [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(lons[i]), float(lats[i])]},
                    "properties": {"problem": int(problems[i]), "mortality": int(morts[i])},
                }
                for i in range(len(lons))
            ]
            points_geojson = {"type": "FeatureCollection", "features": features}

        if "tracks" in (active_layers or []) and "animal_id" in df.columns and "timestamp" in df.columns:
            features = []
            for idx, (animal_id, grp) in enumerate(valid.groupby("animal_id")):
                grp = grp.sort_values("timestamp")
                coords = np.column_stack([
                    np.round(grp["lon"].values, 5),
                    np.round(grp["lat"].values, 5),
                ]).tolist()
                if len(coords) >= 2:
                    n_pts = len(coords)
                    if n_pts > 2000:
                        step = max(1, n_pts // 2000)
                        coords = coords[::step]
                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": {"animal_id": str(animal_id), "idx": idx},
                    })
            tracks_geojson = {"type": "FeatureCollection", "features": features}

    except Exception:
        pass

    return points_geojson, tracks_geojson


_REPORT_OPTION_ID = "report::processing_report"


@app.callback(
    Output("export-checklist-wrap", "children"),
    Output("export-checklist-empty", "style"),
    Input("store-pop-outputs", "data"),
    prevent_initial_call=False,
)
def populate_export_checklist(pop_json):
    """Rebuild the Tab 5 export checklist from the population-output manifest
    stashed in store-pop-outputs by Tab 4. Items are grouped by kind
    (Vector → Raster) then category. Everything is ticked by default.
    The empty-state hint shows only when Tab 4 has produced no products yet."""
    manifest = []
    if pop_json:
        try:
            obj = json.loads(pop_json) if isinstance(pop_json, str) else pop_json
            manifest = obj.get("export_manifest") or []
        except Exception:
            manifest = []

    # Group by kind, then by category (preserving first-seen order).
    kind_order = ["vector", "raster"]
    kind_labels = {"vector": "Vector", "raster": "Raster"}
    by_kind: dict[str, dict[str, list]] = {k: {} for k in kind_order}
    cat_order_by_kind: dict[str, list[str]] = {k: [] for k in kind_order}
    for m in manifest:
        kind = m.get("kind", "vector")
        cat = m.get("category", "Outputs")
        if kind not in by_kind:
            by_kind[kind] = {}
            cat_order_by_kind[kind] = []
            kind_order.append(kind)
        if cat not in by_kind[kind]:
            by_kind[kind][cat] = []
            cat_order_by_kind[kind].append(cat)
        by_kind[kind][cat].append(m)

    all_options = []
    group_idx = 0
    children = []
    for kind in kind_order:
        cats = cat_order_by_kind.get(kind, [])
        if not cats:
            continue
        children.append(html.Div(
            kind_labels.get(kind, kind),
            style={"fontSize": "0.82rem", "fontWeight": "bold",
                    "color": "#9ecfff", "marginTop": "6px", "marginBottom": "2px"},
        ))
        for cat in cats:
            children.append(html.Div(
                cat,
                style={"fontSize": "0.76rem", "fontWeight": "600",
                        "color": "#aaa", "marginLeft": "6px",
                        "marginTop": "4px", "marginBottom": "1px"},
            ))
            cat_options = []
            for m in by_kind[kind][cat]:
                opt = {"label": m["label"], "value": m["id"]}
                cat_options.append(opt)
                all_options.append(opt)
            children.append(dcc.Checklist(
                id={"type": "export-group", "index": group_idx},
                options=cat_options,
                value=[o["value"] for o in cat_options],
                inputClassName="me-2",
                labelStyle={"display": "block", "fontSize": "0.78rem",
                            "marginBottom": "2px", "color": "white",
                            "marginLeft": "12px"},
            ))
            group_idx += 1

    # Processing report — always offered.
    report_opt = {"label": "Processing report (processing_report.txt)",
                  "value": _REPORT_OPTION_ID}
    all_options.append(report_opt)
    children.append(html.Div(
        "Report",
        style={"fontSize": "0.82rem", "fontWeight": "bold",
                "color": "#9ecfff", "marginTop": "6px", "marginBottom": "2px"},
    ))
    children.append(dcc.Checklist(
        id={"type": "export-group", "index": group_idx},
        options=[report_opt],
        value=[report_opt["value"]],
        inputClassName="me-2",
        labelStyle={"display": "block", "fontSize": "0.78rem",
                    "marginBottom": "2px", "color": "white",
                    "marginLeft": "12px"},
    ))

    empty_style = {"display": "none"} if manifest else {"display": "block"}
    return children, empty_style


@app.callback(
    Output({"type": "export-group", "index": dash.ALL}, "value", allow_duplicate=True),
    Input("btn-export-select-all", "n_clicks"),
    Input("btn-export-clear", "n_clicks"),
    State({"type": "export-group", "index": dash.ALL}, "options"),
    prevent_initial_call=True,
)
def export_select_clear(_all_clicks, _clear_clicks, all_options):
    """Select-all / Clear helpers for the export checklist."""
    if ctx.triggered_id == "btn-export-select-all":
        return [[o["value"] for o in (grp or [])] for grp in all_options]
    return [[] for _ in all_options]


def _write_processing_report(df, out_path: Path) -> str:
    """Write the lightweight processing_report.txt. Returns its filename."""
    report_path = out_path / "processing_report.txt"
    # Force UTF-8 — Windows defaults to cp1252 which can't encode arrows /
    # em-dashes / similar punctuation we use in the report.
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Colorado Migration Corridor Mapper — Processing Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Animals: {df['animal_id'].nunique() if 'animal_id' in df.columns else '?'}\n")
        f.write(f"Points: {len(df):,}\n")
        if "timestamp" in df.columns:
            f.write(f"Date range: {df['timestamp'].min()} → {df['timestamp'].max()}\n")
        if "problem" in df.columns:
            f.write(f"Flagged points: {int(df['problem'].sum())}\n")
        if "mortality_flag" in df.columns:
            f.write(f"Mortality flags: {int(df['mortality_flag'].sum())}\n")
    return "processing_report.txt"


@app.callback(
    Output("export-status", "children"),
    Input("btn-export-selected", "n_clicks"),
    Input("btn-export-all", "n_clicks"),
    Input("btn-export-bios", "n_clicks"),
    State({"type": "export-group", "index": dash.ALL}, "value"),
    State("export-dir", "value"),
    State("store-processed-data", "data"),
    State("store-workdir", "data"),
    State("store-migtime-table", "data"),
    State("store-config", "data"),
    State("store-seq-names", "data"),
    prevent_initial_call=True,
)
def handle_export(selected_clicks, all_clicks, bios_clicks, group_values, out_dir, processed_json, workdir_path,
                  migtime_json, config_json, seq_names):
    checked_ids = [v for grp in (group_values or []) for v in (grp or [])]
    """Flush population outputs from the in-memory _POP_OUTPUT_CACHE to disk.

    "Export Selected" writes only the ticked checklist items; "Export All"
    writes every cached product (plus the processing report). Each product is
    written to ``<out_dir>/<rel_dir>/<filename>`` via
    population_outputs.write_product. Fully deferred: this is the ONLY place the
    Tab 4 population products touch disk.
    """
    triggered = ctx.triggered_id

    products = _POP_OUTPUT_CACHE.get("products") or []
    grid_meta = _POP_OUTPUT_CACHE.get("grid_meta")
    pop_cfg = _POP_OUTPUT_CACHE.get("config")
    by_id = {p["id"]: p for p in products}

    # Resolve which ids to write.
    if triggered == "btn-export-all":
        wanted = [p["id"] for p in products] + [_REPORT_OPTION_ID]
    elif triggered == "btn-export-bios":
        _BIOS_PATTERNS = (
            "_All_", "_All.", "_min2", "_min3", "_top10", "_top20",
            "_stopover", "MigLines", "MigPoints",
            "migration_distance_info", "annualCollars", "MigMetadata",
            "SequencesSummary",
        )
        wanted = [
            p["id"] for p in products
            if any(pat in p.get("filename", "") for pat in _BIOS_PATTERNS)
        ] + [_REPORT_OPTION_ID]
    else:
        wanted = list(checked_ids or [])

    if not wanted:
        return _err_alert("Nothing selected to export. Tick at least one output, or use Export All.")

    want_report = _REPORT_OPTION_ID in wanted
    want_products = [i for i in wanted if i != _REPORT_OPTION_ID]

    if want_products and not products:
        return _err_alert(
            "No population outputs in memory. Generate them in Tab 4 first "
            "(they live in process memory and don't survive an app restart)."
        )

    # ---- Resolve the target directory, with version branching ---------------
    # When exporting to the default workdir location, branch to a NEW version if
    # the population options changed since this version was last exported — the
    # branch REFERENCES the model run's data (it isn't recomputed or copied).
    using_workdir_default = (not out_dir) and bool(workdir_path) and Path(workdir_path).is_dir()
    branched_to = None
    if using_workdir_default:
        base = Path(workdir_path)
        sig = _pop_config_signature(pop_cfg)
        cur = _ACTIVE_VERSION if _ACTIVE_VERSION is not None else ((_list_versions(base) or [None])[-1])
        prev_sig = _POP_EXPORTED.get(cur) if cur is not None else None
        if want_products and cur is not None and prev_sig is not None and prev_sig != sig:
            new_v = _start_new_version(base)
            model_src = _MODEL_SOURCE_VERSION or _latest_version_with_model(base)
            _write_pop_version_manifest(new_v, parent=cur, model_source=model_src,
                                        pop_config=pop_cfg, workdir=base)
            branched_to = new_v
        out_dir = str(_workdir_version(base))
    if not out_dir:
        return _err_alert("Please specify an output directory (or set a working directory in Tab 1).")

    out_path = Path(out_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return _err_alert(f"Cannot create output directory: {exc}")

    exported: list[str] = []
    failures: list[str] = []

    try:
        for pid in want_products:
            prod = by_id.get(pid)
            if prod is None:
                failures.append(f"{pid} (not in memory)")
                continue
            try:
                dest_dir = out_path / prod["rel_dir"]
                write_product(prod, dest_dir, grid_meta)
                exported.append(f"{prod['rel_dir']}/{prod['filename']}")
                if prod.get("kind") == "float32" and prod["filename"].endswith("_meanUD.tif"):
                    try:
                        range_dir = out_path / "RangeUDs"
                        range_dir.mkdir(parents=True, exist_ok=True)
                        import shutil
                        src = dest_dir / prod["filename"]
                        shutil.copy2(str(src), str(range_dir / prod["filename"]))
                        exported.append(f"RangeUDs/{prod['filename']}")
                    except Exception:
                        pass
            except Exception as e:
                failures.append(f"{prod['rel_dir']}/{prod['filename']}: {e}")

        # MigLines / MigPoints shapefiles — use cached or reconstruct.
        try:
            sequences_dict = _MODEL_CACHE.get("sequences_dict")
            if not sequences_dict and processed_json and migtime_json:
                _rdf = _json_to_df(processed_json, "processed")
                _rmig = _json_to_df(migtime_json, "migtime")
                _rnames = _MODEL_CACHE.get("seq_labels") or seq_names or [f"mig{i+1}" for i in range(8)]
                try:
                    import geopandas as _gpd_re
                    per_label = extract_sequences(df=_rdf, migtime_df=_rmig, sequence_names=_rnames)
                    utm_crs_re = _MODEL_CACHE.get("utm_crs") or "EPSG:32613"
                    sequences_dict = {}
                    for label, ld in per_label.items():
                        if ld.empty:
                            continue
                        ld = _gpd_re.GeoDataFrame(
                            ld, geometry=_gpd_re.points_from_xy(ld["lon"], ld["lat"]), crs="EPSG:4326"
                        ).to_crs(utm_crs_re)
                        for mig_key, sub in ld.groupby("mig"):
                            sub = _gpd_re.GeoDataFrame(sub.copy(), geometry="geometry", crs=ld.crs)
                            sequences_dict[str(mig_key)] = sub
                    _MODEL_CACHE["sequences_dict"] = sequences_dict
                    _MODEL_CACHE["seq_labels"] = _rnames
                except Exception:
                    pass
            if sequences_dict and processed_json and migtime_json:
                proc_df = _json_to_df(processed_json, "processed")
                if "timestamp" in proc_df.columns:
                    proc_df["timestamp"] = pd.to_datetime(proc_df["timestamp"], errors="coerce")
                mig_df = _json_to_df(migtime_json, "migtime")
                herd_id = "Herd"
                bio_month, bio_day = 2, 1
                if config_json:
                    cfg_obj = json.loads(config_json) if isinstance(config_json, str) else config_json
                    if isinstance(cfg_obj, dict):
                        herd_id = str(cfg_obj.get("herd_id", "Herd")).strip() or "Herd"
                        bio_month = int(cfg_obj.get("bio_year_start_month", 2) or 2)
                        bio_day = int(cfg_obj.get("bio_year_start_day", 1) or 1)
                import datetime as _dt_exp
                date_stamp = _dt_exp.datetime.now().strftime("%m%d%y")
                s_labels = _MODEL_CACHE.get("seq_labels") or seq_names or []
                utm_crs_str = _MODEL_CACHE.get("utm_crs")
                target_crs = utm_crs_str
                prim_dir = out_path / f"{herd_id}_Primary_Outputs"
                prim_dir.mkdir(parents=True, exist_ok=True)
                mig_written = write_mig_outputs(
                    processed_df=proc_df,
                    migtime_df=mig_df,
                    sequences_dict=sequences_dict,
                    out_dir=prim_dir,
                    herd_id=herd_id,
                    date_stamp=date_stamp,
                    seq_labels=s_labels,
                    bio_year_start_month=bio_month,
                    bio_year_start_day=bio_day,
                    target_crs=target_crs,
                )
                for label, p in mig_written.items():
                    exported.append(f"{herd_id}_Primary_Outputs/{p.name}")
        except Exception as e:
            failures.append(f"MigLines/MigPoints: {e}")

        # Line buffer — regenerate if the model run produced one.
        try:
            if sequences_dict and _MODEL_CACHE.get("linebuffer_distance"):
                lb_dist = float(_MODEL_CACHE["linebuffer_distance"])
                seq_animal = _MODEL_CACHE.get("seq_animal", {})
                utm_crs_str = _MODEL_CACHE.get("utm_crs")
                _build_linebuffer_output(
                    sequences_dict, seq_animal, lb_dist, out_path, utm_crs_str,
                )
                exported.append("LineBuffer/raw_linebuffer.shp")
        except Exception as e:
            failures.append(f"LineBuffer: {e}")

        if want_report:
            if not processed_json:
                failures.append("processing_report.txt (no processed data — complete Tab 1)")
            else:
                try:
                    df = _json_to_df(processed_json, "processed")
                    if "timestamp" in df.columns:
                        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                    exported.append(_write_processing_report(df, out_path))
                except Exception as e:
                    failures.append(f"processing_report.txt: {e}")

        # Remember the exported population signature for this version (persisted
        # to its manifest) so a later options change branches a fresh version.
        if using_workdir_default and want_products and exported and _ACTIVE_VERSION is not None:
            _record_pop_export(_ACTIVE_VERSION, pop_cfg)

        _log_action(
            "EXPORT", trigger=str(triggered), out_dir=out_dir,
            version=(_ACTIVE_VERSION if using_workdir_default else None),
            branched_new_version=bool(branched_to),
            n_exported=len(exported), n_failed=len(failures),
        )

        branch_note = (
            f"New version V{branched_to} created (population options changed; "
            f"model data referenced from the previous version). "
            if branched_to else ""
        )

        if exported and not failures:
            return _ok_alert(
                branch_note
                + f"Exported {len(exported)} file group(s) to {out_dir}: "
                + ", ".join(exported)
            )
        if exported and failures:
            return dbc.Alert(
                [
                    html.Strong(f"{branch_note}Exported {len(exported)} of {len(exported) + len(failures)} to {out_dir}."),
                    html.Br(),
                    html.Span("Failed: " + "; ".join(failures), className="small"),
                ],
                color="warning", dismissable=True,
            )
        return _err_alert("Export failed: " + "; ".join(failures))

    except Exception as exc:
        return _err_alert(f"Export error: {exc}\n{traceback.format_exc()[:500]}")


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    import logging as _logging
    _logging.getLogger("werkzeug").setLevel(_logging.ERROR)
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        threading.Timer(1.5, webbrowser.open, args=("http://127.0.0.1:8050",)).start()
    print("Migration Corridor Mapper running at http://127.0.0.1:8050")
    app.run(debug=True, host="127.0.0.1", port=8050)
