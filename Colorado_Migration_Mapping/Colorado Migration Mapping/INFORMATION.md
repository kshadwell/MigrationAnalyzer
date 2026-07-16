# Colorado Migration Corridor Mapper — Information File (K)

This is the single comprehensive, durable record of what this project is, where it came from, how it works, and the running log of setup/maintenance actions. 

Where it makes sense, each section gives both a **plain-English summary** ("what this is, why it matters") and a **technical detail** block ("how it's implemented"). You can read this top-to-bottom, or jump to any section.

------------------------------------------------------------------------

## Table of Contents

1.  [What this project is (plain-English)](#1-what-this-project-is-plain-english)
2.  [Project history](#2-project-history)
3.  [Quick start — install & run](#3-quick-start--install--run)
4.  [Project folder layout](#4-project-folder-layout)
5.  [The data pipeline at a glance](#5-the-data-pipeline-at-a-glance)
6.  [Setup Log & Pending Items](#6-setup-log--pending-items)
7.  [Module-by-module deep dive](#7-module-by-module-deep-dive)
    - [7.1 `data_ingestion.py`](#71-data_ingestionpy--load--clean--compute-movement-parameters)
    - [7.2 `sequencing.py`](#72-sequencingpy--auto-detect-migrations-from-nsd)
    - [7.3 `modeling.py`](#73-modelingpy--corridor-models-kernel--bbmm-stubs)
    - [7.4 `population_outputs.py`](#74-population_outputspy--merge-individuals-into-population-products)
    - [7.5 `raster_sampler.py`](#75-raster_samplerpy--sample-environment-at-each-gps-fix)
    - [7.6 `road_crossings.py`](#76-road_crossingspy--did-the-animal-cross-a-road)
    - [7.7 `wld_reader.py`](#77-wld_readerpy--read-migrationanalyzer-wld-binary-files)
    - [7.8 `main.py` (the Dash app)](#78-mainpy--the-dash-application)
    - [7.9 Assets — MapLibre map, Leaflet styles, CSS](#79-assets--maplibre-html-map_functionsjs-stylecss)
8.  [Data dictionary (input + computed columns)](#8-data-dictionary)
9.  [Configuration reference (every tunable parameter)](#9-configuration-reference)
10. [Design decisions & rationale](#10-design-decisions--rationale)
11. [Known gotchas & edge cases](#11-known-gotchas--edge-cases)
12. [Future development directions](#12-future-development-directions)

------------------------------------------------------------------------

## 1. What this project is (plain-English)

This is a **desktop web-app for wildlife biologists**. Drop in a CSV of GPS collar fixes from migratory animals (pronghorn, elk, mule deer, etc.) and it walks you through:

1.  **Cleaning** the data — strip bad GPS fixes, catch mortalities, compute speeds and turning angles.
2.  **Finding migrations** automatically — detects when each animal moved between seasonal ranges by looking at how far it drifted from its starting point over time. Migrations can also be detected manually instead.
3.  **Drawing corridors** — turns each animal's individual migration path into a "corridor" (a probability surface showing where the animal spent time).
4.  **Stacking the herd** — merges every individual corridor into a population-level "where the herd migrates" map, with contour lines at 50 %, 75 %, 95 %, etc.
5.  **Exporting** — writes shapefiles, GeoTIFFs, and a methodology report.

The whole thing runs in a browser tab on your own machine. No cloud, no upload, no account.

**Why it exists:** the field standard for this work is a stack of six R Shiny apps called *Migration Mapper* (Wyoming Migration Initiative / Western Corridor Mapping Team). It works, but each app is its own window, requires manual sequence definition for every animal-year, and the modeling backend depends on specialised R packages. This app folds the whole workflow into a single tabbed UI, auto-detects migrations to remove the manual bottleneck, and adds environmental sampling (elevation, snow, road crossings) on top.

------------------------------------------------------------------------

## 2. Project history

| When | What |
|----|----|
| \~2018–present | **Migration Mapper** (R/Shiny) released by the Wyoming Migration Initiative / Western Corridor Mapping Team. Six apps: data cleaning → sequencing → sequence export → UD modeling → population merging → mapping. Reference codebase is at `WesternCorridorMappingTeam-main/` (when present). |
| Dec 2025 | A legacy R prep script (`MigrationMapper_FromAppDownload`) is written — takes CSV exports from CPW's *Wildlife Tracker* app, applies DOP/satellite quality filters, validates required columns, and writes shapefiles in the exact format Migration Mapper expects. This is the bridge from CPW's data system into the R workflow and is the direct ancestor of the cleaning logic in `data_ingestion.py`. (Script no longer in repo.) |
| Early 2026 | Python/Dash rewrite begins. Goal: single app, automated sequencing, environmental sampling, deployable without an R install. |
| \~Mar 2026 | MigrationAnalyzer environmental data assembled — USGS 1/3-arc-second DEM tiles covering Colorado, TIGER Census road shapefiles, and a pickled SNODAS daily snow cube (`snodas_colorado.pkl`, \~3.7 GB). |
| 2026-05-15 | Initial setup on this machine. Python path corrected in batch files; `map_functions.js` rename issue resolved so Dash serves it. See [Setup Log](#6-setup-log--pending-items). |
| 2026-05-16 | Comprehensive reference file created (originally named `INFORMATION_K.md`; renamed to `INFORMATION.md` on 2026-07-08). It absorbed the earlier `INFORMATION.md`, which was merged in + deleted 2026-06-09. |

**Lineage of the cleaning code.** The order of operations in `data_ingestion.process_data()` (column auto-remap → DOP filter → satellite filter → bad-coord filter → validation → burst → movement params → NSD → problem points → mortality) mirrors the R script's order exactly. The Python module is essentially a faithful port that adds biological-year handling and three NSD groupings (calendar year, overall, bio year) that the R version computed via separate scripts in `wmiScripts/`.

------------------------------------------------------------------------

## 3. Quick start — install & run

Once you have cloned the repository and run Setup.bat, you just double-click Start App.bat whenever you want to open the app. More info about accessing Migration Analyzer from Bryan & K. 

### From a terminal (any OS)

```         
pip install -r requirements.txt
python app/main.py
```

The app listens on `127.0.0.1:8050`. It is `debug=True`, so saving a `.py` file under `app/` auto-reloads.

### Dependencies

`requirements.txt` pins minimum versions:

```         
dash >= 2.14            # Web UI framework
dash-leaflet >= 1.0.15  # Leaflet map widget for Tab 5
dash-bootstrap-components >= 1.5   # Bootstrap-themed Dash components
flask-caching >= 2.0    # Server-side dataframe cache
plotly >= 5.18          # NSD / displacement / speed charts
pandas >= 2.1           # Tabular operations
geopandas >= 0.14       # Spatial dataframes
numpy >= 1.24           # Array math
scipy >= 1.11           # KDE, signal smoothing, gaussian_filter
shapely >= 2.0          # Geometry ops
pyproj >= 3.6           # CRS reprojection
fiona >= 1.9            # Vector I/O (used by geopandas)
rasterio >= 1.3         # Raster I/O for UDs and DEM
scikit-learn >= 1.3     # (currently unused — reserved for future modeling)
pyarrow >= 14           # Parquet read/write for session_data
```

There is no `setup.py` and the project is not a Python package — `main.py` adds its parent directory to `sys.path` at startup so `from app.modules.X import …` works regardless of where you launch it from.

------------------------------------------------------------------------

## 4. Project folder layout

```         
Colorado Migration Mapping/            <- THIS is the app's root
├── INFORMATION.md                   <- THIS comprehensive file (sole reference)
├── requirements.txt                   <- pip dependencies
├── Setup.bat / Start App.bat          <- Windows convenience launchers
├── .gitignore                         <- ignores __pycache__, session_data, env data, *.zip
├── app/
│   ├── main.py                        <- Dash UI + every callback (~2660 lines)
│   ├── assets/                        <- auto-served at /assets/ by Dash
│   │   ├── maplibre_map.html          <- iframe map for Tab 2 (MapLibre GL + satellite + 3D terrain)
│   │   ├── map_functions.js           <- L.circleMarker styling for Tab 5's Leaflet map
│   │   └── style.css                  <- range-slider tweaks
│   ├── modules/
│   │   ├── __init__.py                <- package marker (empty)
│   │   ├── data_ingestion.py          <- load + clean + compute movement params + NSD
│   │   ├── sequencing.py              <- auto-detect migrations from NSD shape
│   │   ├── modeling.py                <- Kernel UD, Line Buffer, BBMM, CTMM (via R), dBBMM (via R)
│   │   ├── population_outputs.py      <- merge individual UDs into population products
│   │   ├── raster_sampler.py          <- sample DEM + SNODAS at every GPS fix
│   │   ├── road_crossings.py          <- detect road/highway crossings using TIGER shapefile
│   │   └── wld_reader.py              <- read MigrationAnalyzer .wld binary files (ELK1 format)
│   └── session_data/                  <- per-project persistent state (gitignored)
│       └── <project_name>/
│           ├── processed_data.parquet
│           ├── road_crossings.json
│           └── animal_notes.json
```

**External data (not part of the project folder).** The environmental data lives outside this directory:

```         
MigrationFiles/MigrationAnalyzer/
├── elevation/                         <- 40+ USGS 1/3-arc-second DEM GeoTIFFs (~15 GB)
├── snodas_colorado.pkl                <- pickled SNODAS daily snow cube for CO (3.9 GB)
└── all_roads_merged.{shp,dbf,shx,prj,cpg}  <- TIGER Census roads for CO (~136 MB)
```

The Python modules expect to find these under a folder called `environment_data/` *next to* `app/` (so: `Colorado Migration Mapping/environment_data/elevation/…`). 

------------------------------------------------------------------------

## 5. The data pipeline at a glance

```         
  Raw CSV / Shapefile / ZIP (from CPW Wildlife Tracker, GPS collar vendor, etc.)
                       │
                       ▼
           ┌──────────────────────────┐
           │  Tab 1 — Data Import     │
           │  data_ingestion.py       │
           │                          │
           │  - Auto-detect format    │
           │  - DOP / sat filter      │
           │  - Standardise columns   │
           │  - Compute bursts        │
           │  - Movement params       │
           │    (dist, speed, angles) │
           │  - NSD (3 groupings)     │
           │  - Flag problems         │
           │  - Check mortality       │
           │  - Sample rasters        │
           │    (elev, snow, roads)   │
           └──────────────────────────┘
                       │
                       ▼ processed GeoDataFrame
                       │
           ┌──────────────────────────┐
           │  Tab 2 — Sequencing      │
           │  sequencing.py           │
           │                          │
           │  - Auto-detect mig       │
           │    windows from NSD      │
           │  - Build migtime table   │
           │  - Human review per      │
           │    animal-year:          │
           │      • NSD plot          │
           │      • Map               │
           │      • Range sliders     │
           │      • Accept / Reject   │
           └──────────────────────────┘
                       │
                       ▼ migtime table + extracted sequence GeoDataFrames
                       │
           ┌──────────────────────────┐
           │  Tab 3 — Modeling        │
           │  modeling.py             │
           │                          │
           │  Per sequence:           │
           │   - Kernel UD            │
           │   - Line Buffer          │
           │   - BBMM/CTMM/dBBMM      │
           │     (stubs → Kernel)     │
           │   - Footprint polygon    │
           └──────────────────────────┘
                       │
                       ▼ {seq_name: (UD raster, footprint polygon)}
                       │
           ┌──────────────────────────┐
           │  Tab 4 — Population      │
           │  population_outputs.py   │
           │                          │
           │  - Stack UDs → use grid  │
           │  - Stack footprints      │
           │  - Contour at user %s    │
           │  - Drop small polys      │
           │  - Fill small holes      │
           └──────────────────────────┘
                       │
                       ▼ population-level contour GeoDataFrames
                       │
           ┌──────────────────────────┐
           │  Tab 5 — Map & Export    │
           │                          │
           │  - Leaflet map with      │
           │    layer toggles         │
           │  - Export shapefiles,    │
           │    GeoTIFFs, report      │
           └──────────────────────────┘
```

------------------------------------------------------------------------

## 6. Setup Log & Pending Items

Running log of setup actions and decisions on this machine (Windows 11). New dated entries at the top of the dated section; deferred work in the "Pending / To Revisit" subsection right below.

### Pending / To Revisit

#### Active to-do list (added 2026-05-20)

These are the in-flight tasks mirrored from the session task list. 

- **Diagnose BBMM output divergence vs. canonical reference.** Two suspected causes: (1) `scipy.optimize.minimize_scalar` vs. R `optim` for the Horne 2007 MLE, and (2) our `T_total` divisor in `_bbmm_bridge_accumulate` sums only kept segments while R's `sum(time.lag)` sums all pairs including the ones excluded by `max.lag`. Compare per-season `.tif` outputs against the canonical `A37_BBMM_*` set at `K:\MigrationAnalysis\A37\2026.zip` → `OutputData/Jaffe_IndStackedOutput_040226/`. Visual divergence first confirmed 2026-05-18 after wiring `calc_season_banded_outputs` (this item now subsumes that earlier "BBMM per-season UD `.tif` outputs visually differ" Pending note). Additional differences to check beyond the two suspected causes:
  - **BBMM motion-variance estimator path**: our Horne (2007) MLE via `scipy.optimize.minimize_scalar` vs. R `BBMM::brownian.motion.variance` — different numerical optimisers, possibly different residual parametrisation.
  - **Bandwidth / grid alignment**: our subgrid is built per-sequence from the seq bbox + `mult4buff`; the R workflow may carry global grid cells more strictly.
  - **`apply_tail_cutoff` placement**: we cut the 99.99% tail on each individual UD *before* averaging. R may apply the cutoff after the population merge.
  - **Population merging step**: our `calc_season_banded_outputs` normalises each individual to sum=1 then averages. R's `CalcPopUse` may do a weighted sum or volume-rank-based aggregation.
  - **Cell-size and CRS**: confirm both pipelines use the same projected CRS and 500 m cell size end-to-end (no implicit reprojection differences).
- **Test CTMM and dBBMM end-to-end.** (Backburner) Implementation done (2026-07-09) via R subprocess but not yet verified. Plan is to translate the R scripts to native Python, so deferring testing of the R bridge.
- **Sort minimum outputs by number of species.** Currently just 0/1; should sort by count. Minimum 1 is low-value but keep for now.
- **Investigate pop_use_contours.shp.** Not showing any data — determine what this file is and fix.
- **CTMM season outputs.** Generate spring migration, fall migration, summer, and winter points and lines from CTMM.
- **~50m offset in CTMM points.** Test data showed all points offset ~50 m from original CTMM points. **Audit (2026-07-14):** almost certainly **grid cell snapping** (`np.ceil` on 250m cells → up to ~125m shift), not a projection bug.
- **Polygon shapefiles + smoothing.** Implement Flenner's smoothing method for polygon shapefiles.
- **Subherd selection and re-analysis.** Add a step (possibly before Migtime) to view data and identify subherds, then divide individuals into subherds and rerun analysis. Example: D4 would split into 3 groups (west of Hwy 287, towards Hwy 230, west towards the divide). Add stacked buffered line layers (400 m buffer, per Jerod Merkle). **Research (2026-07-14):** Migration Mapper has no built-in subherd partitioning — `herd_id` is just a filename prefix (DAU code), and there's no grouping/clustering mechanism. No precedent to follow. Approaches under consideration: (1) **In-app visual selection** — show tracklines on the Tab 1 map, let users draw polygons or lasso-select animals into named groups, then run the analysis per group. Most polished but significant to build. (2) **Animal tag UI** — lighter middle ground: a multi-select/tag panel in Tab 1 or Tab 2 where users assign animals to named groups after viewing the data, then run per group. (3) **External pre-processing** — users split their input CSV into separate files by subherd before loading. No app changes, but puts the burden on the user.
- **Statewide grid + polygon shapefile for migration output.** Lower priority — Flenner? Add a statewide grid and polygon shapefile to export migration outputs into.


### 2026-07-15 — Multi-column timestamp selection + CRS/projection handling

**Multi-column timestamps.** The Timestamp column selector in Tab 1 is now multi-select (`multi=True`). Users can pick multiple columns (e.g., a separate date column and time column) which are concatenated with a space separator before datetime parsing. When multiple columns are selected, `pd.to_datetime` uses `format="mixed"` instead of the fixed format string. Matches how Migration Mapper handles split date/time fields.

**CRS/projection handling for shapefiles.** Shapefiles already carried their CRS via the `.prj` sidecar and were reprojected to EPSG:4326 internally. Now the app detects the CRS at preview time and adapts the UI: if the shapefile is in a projected CRS (e.g., UTM Zone 13N), the Column Mapping card automatically swaps "Longitude/Latitude" dropdowns for "UTM Easting/UTM Northing" dropdowns and auto-detects common easting/northing column names (UTME, UTMN, Easting, Northing, POINT_X, POINT_Y). The detected CRS is shown next to the filename (e.g., "Loaded: D16.zip · CRS: EPSG:32613").

**CRS/projection handling for CSVs.** When a CSV is loaded, a warning note explains that the app assumes WGS84 (EPSG:4326) consistent with Wildlife Tracker data. A checkbox ("Yes, my CSV data is in UTM Zone 13N") lets users declare UTM input, which swaps to easting/northing column selectors and triggers reprojection to WGS84 on processing.

**Projected CRS quality filter fix.** The quality filter's "positive longitude = Germany/test data" check (`lon > 0`) was removing ALL rows from projected datasets (UTM eastings are always positive). Now skipped when `is_projected=True`. Same fix applied to `validate_for_migration_mapper` — hemisphere check skipped, coordinate range labels change to Easting/Northing, and `iloc[0]` guarded against empty DataFrames.

**CRS in processing summary.** The Processing Summary card now shows the input CRS with a reprojection note when applicable. The CRS is also saved to `project_meta.json` and shown when loading saved projects. The processing log records the input CRS at the start of each run.

### 2026-07-14 — Misc fixes: auto-open browser, folder picker, output naming

**Auto-open browser on startup.** Added `webbrowser.open` call on app start, gated by `WERKZEUG_RUN_MAIN` to prevent the Dash debug reloader from opening two tabs.

**Folder picker fix.** The bundled embeddable Python 3.13 does not include tkinter, so the Browse button for working directory selection silently did nothing. Fixed by detecting and using the system-installed Python (which has tkinter) for the folder-picker subprocess. Falls back to a PowerShell `Shell.Application.BrowseForFolder` dialog with a console note telling users to install Python from python.org for the better File Explorer picker.

**Note — system Python detection needs hardening.** `_find_system_python()` currently checks a short list of common install paths (`C:\Program Files\Python31x\python.exe`, `shutil.which`). Not all users install Python to the same location — some use `AppData\Local\Programs\`, custom paths, or pyenv. Consider checking the Windows registry (`HKLM\SOFTWARE\Python\PythonCore\`) or `py.exe` launcher (`py -3 -c "import tkinter"`) for more robust detection.

**Output folder naming.** Renamed `Migtime Exports` → `Migtime_Exports` (no spaces in output folder/file names).

**Population outputs: count individuals, not sequences.** Previously, each sequence (e.g., `PH01_2022_Spring` and `PH01_2023_Spring`) was treated as a separate layer in the population stack — so 35 animals with ~2 sequences each produced counts up to 70. Now sequences are grouped by animal ID and averaged into one UD surface per individual before the population merge. The count grid now ranges from 1–N where N = number of unique animals. `seq_animal` and `seq_label` are cached in `_MODEL_CACHE` so the population callback can map sequences back to animals.

**Renamed min1/min2/min3 → minimum1/minimum2/minimum3.** Output filenames and keys changed from `_min1`/`_min2`/`_min3` to `_minimum1`/`_minimum2`/`_minimum3` to avoid confusion with "minus".

**Input data date range in processing log.** Both the MODEL RUN and POPULATION OUTPUTS sections of `processing_log.txt` now include the full date range of the input collar data (e.g., `Input data date range: 09/01/2013 — 07/01/2022`).

**Year summaries by bio-year.** Population outputs now include per-bio-year summaries under `YearSummaries/<bio_year>/`. For each bio-year, the system generates: (1) per-season stacked count surfaces (e.g., Spring_2020, Fall_2020) with the full banded product set (count, meanUD, minimum, top, stopover, isopleths); (2) all-season population summary combining all seasons for that year; (3) per-individual combined UD TIFs under `YearSummaries/<bio_year>/IndividualUDs/`. Bio-year is extracted from the mig_key (`<animal>_<bioYear>_<season>`) using the `seq_animal` mapping to correctly handle animal IDs containing underscores. Year summaries appear in the Tab 5 export checklist under "Year summary — <year>" categories and in the Tab 5 raster overlay picker.

**Files touched.** `app/main.py` (`_find_system_python`, `_pick_directory_native`, entry point browser open, `Migtime_Exports` rename, individual-level UD stacking in `generate_pop_outputs`, `input_date_range` caching, processing log additions, year summary generation, `_RASTER_CATEGORIES`), `app/modules/population_outputs.py` (`minimum` rename in `compute_season_banded_products`, `_mask_to_gdf`).

### 2026-07-09 — Real CTMM implementation via R subprocess

Replaced `calc_ctmm_stub` with a full `calc_ctmm` function (`modeling.py`) that calls R's `ctmm` package via an Rscript subprocess. Matches CalcCTMM.R from WMI MAPP3.x: `ctmm.guess` → `ctmm.select` (AIC/BIC/AICc, pHREML) → `ctmm::occurrence` on the population subgrid → 99.99% tail cutoff → contour-based footprint.

**Architecture:** Python writes sequence points as a temp CSV + the population grid as a temp GeoTIFF, calls `Rscript ctmm_bridge.R` with 9 arguments (input CSV, popgrid TIF, UD output TIF, footprint output TIF, info criteria, contour, mult4buff, max timeout, metadata JSON path), then reads back the UD/footprint rasters and metadata JSON. `_find_rscript()` checks PATH then common Windows R install locations.

**R bridge script (`app/modules/ctmm_bridge.R`):** checks for required packages (`ctmm`, `move`, `sf`, `terra`, `R.utils`, `jsonlite`) — exits with code 2 and `MISSING_PACKAGES:...` if any are missing. Builds telemetry via `move::move` → `ctmm::as.telemetry`, runs model selection with timeout, computes occurrence distribution on the cropped pop grid, applies 99.99% tail cutoff, writes UD + footprint TIFs + metadata JSON.

**Graceful fallback:** if R is not installed, required R packages are missing, Rscript times out, or the R script errors, `calc_ctmm` falls back to `calc_kernel_ud` with a warning explaining what to install. The warning is also surfaced in each result row's metadata (`method_note`).

**UI (Tab 3, `main.py`):** when CTMM is selected in the model dropdown, an info alert now reads: *"To run CTMM, ensure R is installed, along with the packages: ctmm, move, sf, terra, R.utils, jsonlite. If R or any package is missing, the model will fall back to Kernel UD."*

**Files touched:** `app/modules/modeling.py` (`_find_rscript`, `calc_ctmm` replacing `calc_ctmm_stub`, `run_model` dispatcher updated), `app/modules/ctmm_bridge.R` (new), `app/main.py` (CTMM param panel info alert, stale comment updated).

### 2026-07-09 — Real dBBMM implementation via R subprocess

Replaced `calc_dbbmm_stub` with a full `calc_dbbmm` function (`modeling.py`) that calls R's `move::brownian.bridge.dyn` via Rscript subprocess. Matches CalcDBBMM.R from WMI MAPP3.x: `move::move` → `move::burst` (segmenting at max_lag gaps) → `brownian.bridge.dyn` with margin/window params → 99.99% tail cutoff → contour footprint.

**Architecture:** Same Rscript bridge pattern as CTMM. Python writes sequence points as temp CSV + pop grid as temp TIF, calls `Rscript dbbmm_bridge.R` with 12 arguments (input CSV, popgrid TIF, UD output TIF, footprint output TIF, location error, max lag, contour, margin, window, mult4buff, max timeout, metadata JSON path), reads back results. Required R packages: `move`, `sf`, `terra`, `R.utils`, `jsonlite`.

**R bridge script (`app/modules/dbbmm_bridge.R`):** Checks for required packages (exits code 2 if missing). Implements the >1/3 max-lag bail, <4 point bail, burst segmentation by connectivity, dynamic BB computation with timeout. Multi-layer result collapsed via `sum(bb)` (matching CalcDBBMM.R). Reports `dbb_mean_motion_variance` in metadata.

**Graceful fallback:** If R is not installed, packages are missing, Rscript times out, or R errors, falls back to regular BBMM (EB) with a warning.

**UI (Tab 3):** Both CTMM and dBBMM panels now have an info alert listing required R packages, plus an optional "Rscript Path" text input with helper text telling users to run `R.home("bin")` in RStudio to find their R install.

**Rscript auto-detection (`_find_rscript`):** Expanded to check `RSCRIPT_PATH` env var, `R_HOME` env var, system PATH, Windows registry (`HKLM/HKCU SOFTWARE\R-core\R`), `AppData\Local\Programs\R`, and `Program Files\R`. Among candidates, prefers the installation whose library contains the required packages.

**Files touched:** `app/modules/modeling.py` (`calc_dbbmm` replacing `calc_dbbmm_stub`, `_find_rscript` expanded), `app/modules/dbbmm_bridge.R` (new), `app/main.py` (dBBMM param panel info alert + Rscript path input, `_apply_model_ui_params` wiring, imports updated).

### 2026-07-09 — Excluded-point counts in Tab 2 sequence card

Added a status line to the `seq-confidence` div in `render_seq_panels` (`main.py`). When the selected animal-year has problem or mortality-flagged points, the sequence card now appends e.g. *"Excluded from sequencing: 23 problem, 4 mortality."* Counts come from `animal_df` (already filtered to the selected animal-year). Nothing shown if no flags.

### 2026-07-09 — Bundled embeddable Python 3.13 for portable deployment

Replaced the hardcoded `C:\Program Files\Python313\python.exe` path in `Setup.bat` and `Start App.bat` with a relative path to a bundled embeddable Python (`python-3.13/python.exe`, ~21 MB). Both batch files now use `%~dp0python-3.13\python.exe`. The bare embeddable Python (no packages) is committed to the repo; `Setup.bat` bootstraps pip on first run (downloads `get-pip.py`), then installs all `requirements.txt` dependencies into `python-3.13/Lib/site-packages/` via `--target`. Installed packages (`Lib/`, `Scripts/`) are gitignored — each user runs Setup.bat once after cloning. The inner `.gitignore` has a `!python-3.13/python313.zip` exception so the stdlib archive isn't blocked by the `*.zip` rule. `python313._pth` has `import site` uncommented so pip and installed packages are discoverable.

### 2026-07-09 — Population output min_area_drop / min_area_fill ignored user value of 0

**Bug:** entering `0` for min_area_drop or min_area_fill in Tab 4 silently used the defaults (10000 / 5000). Same `float(x or default)` pattern fixed in Tab 1 on 2026-06-25 — `0` is falsy in Python, so `0 or 10000` evaluates to `10000`.

**Fix (`main.py`, `generate_pop_outputs`):** replaced `float(min_drop or 10000)` / `float(min_fill or 5000)` with `float(min_drop) if min_drop not in (None, "") else 10000.0` (and same for min_fill). Blank → default; explicit `0` → `0.0`.

### 2026-07-09 — Model processing log no longer shows irrelevant parameters from other model types

**Bug:** running a BBMM model logged dBBMM parameters (`dbbmm_margin`, `dbbmm_window`) and CTMM parameters (`info_criteria`) in the processing log and version manifest, because `get_model_config` (`modeling.py`) returns a single config dict with defaults for every model type, and the logging dumped all keys.

**Fix (`main.py`, `run_modeling`):** added a `_MODEL_KEYS` mapping that defines which config keys are relevant to each model type (shared keys like `cell_size`/`contour` plus model-specific ones). Both the version manifest and the processing log now filter `param_fields` to only the relevant keys.

### 2026-07-09 — Mortality truncation behavior confirmed matching Migration Mapper

Checked `Check4Morts.R` (App 1) and `app3_calcSequences.R` (App 3) in the R Migration Mapper source. **Both apps flag mortality points (set `mortality=1`) without truncating the animal's timeline.** App 3 drops `problem==1` and `mortality==1` points at sequence extraction — same as our `extract_sequences`. No code change needed; removed from the pending list.

### 2026-07-09 — Git repo initialized and pushed to Gitea

Initialized git in `MigrationAnalyzer/`, added `.gitignore` for large data files (`elevation/`, `snodas_colorado.pkl`, `all_roads_merged.gpkg`), and pushed to `https://dnrapp110.naturenet.state.co.us/git/ShinyDev/MigrationAnalyzer.git`. Remote URL includes `ShinyDev@` username to force terminal password prompt (avoids GUI credential helper hanging). Created `deploy.sh` for push convenience.

### 2026-07-07 — Road-crossing detection under-reported: local roads (S1400) were excluded

**Symptom:** test animals that clearly cross roads reported `crosses_road: False` / `crosses_highway: False`. **Root cause:** the MTFCC code filter in `road_crossings.py` was `_ROAD_CODES = {"S1100","S1200"}` — i.e. only interstates/US-highways (S1100) and secondary highways (S1200). **Local roads S1400 (117,388 of the 144,107 features — the vast majority) were excluded**, so an animal that crossed a county/local road but not a numbered highway reported no crossing. Highway detection was also too narrow (`_HIGHWAY_CODES = {"S1100"}`, only 134 interstate features).

**Fix (`road_crossings.py`):**
- `_ROAD_CODES = {"S1100","S1200","S1400"}` — "road" now means ANY road incl. local. `_HIGHWAY_CODES = {"S1100","S1200"}` — "highway" = any numbered primary/secondary highway. `crosses_road` counts any intersection; `crosses_highway` if any hit is S1100/S1200. (Highway ⊆ road; the road-vs-highway distinction is now just "crossed a local road only" vs "crossed a numbered highway".)
- `detect_crossings_batch` now `sort_values("timestamp")` per animal before building the track LineString, so the connecting segments follow real movement order (groupby preserves input order, not necessarily chronological; ISO-string timestamps also sort chronologically).
- **Verified on D4_Test6 (207 animal-years): crosses_road 43 → 164, crosses_highway → 43.** The roads layer used for matching grew 1,404 → 118,792 features. The first test animal (previously False) now correctly reports `crosses_road: True`. Wiring was already fine (results keyed by `id_bio_year`, stored in `road_crossings.json`, surfaced via `_crossing_phrase`/Tab 2). Detection is still opt-in via the Tab 1 "Detect road crossings" checkbox (off by default — it's slower now with 119k features, but sindex keeps it fine).

**Coverage limitation (data, not code — flag for real runs):** `MigrationAnalyzer/all_roads_merged.shp` covers only **19 Colorado counties** (Boulder, Denver, Larimer, Weld, Grand, Routt, Moffat, Eagle, Garfield, Summit, Park, Pitkin, Rio Blanco, Lake, Clear Creek, Gilpin, Jackson, Logan, Morgan) + 3 southern-WY counties (Albany, Carbon, Laramie). Bounds lat **38.69–42.43**, lon −109.05 to −102.65. **The other 45 CO counties are NOT covered** (no El Paso, Pueblo, Mesa, Douglas, Jefferson, Arapahoe, Gunnison, Montrose, La Plata, etc.), so animals there report "no crossing" for lack of road data. The bundled file IS the merged product and the **source county files are gone** — you can't gain coverage by re-merging what's present; the missing counties must be downloaded.

**Statewide roads plan (2026-07-07):** TIGER has no single statewide All-Roads file (per-county All-Roads includes S1400 local; the one statewide Primary/Secondary file omits local roads). Plan (per user): download the missing counties' All-Roads and merge.
- **New utility `merge_tiger_roads.py`** (project root, next to `Start App.bat`): reads county `tl_*_roads.shp`/`.zip` from `--input`, folds in the existing merged layer by default (so only the missing 45 counties need downloading), dedupes on `LINEARID`, and writes **`all_roads_merged.gpkg`** (GeoPackage — a full-state all-roads merge is ~1M+ features, past shapefile's 2 GB / 10-char-field limits). Reports MTFCC counts + counties + bounds. County FIPS parsed from the TIGER filename → `county_fip`. Verified: folding the existing layer into a temp `.gpkg` round-trips (143,962 features, schema `LINEARID/FULLNAME/RTTYP/MTFCC/county_fip/geometry`, CRS EPSG:4269).
- **`road_crossings.py` loader now prefers `all_roads_merged.gpkg`, falls back to the old `.shp`** (`_ROADS_FILENAMES`, `_resolve_roads_file`; `_MERGED_SHP` may be `None` → handled in `_load_roads`). So dropping in the merged `.gpkg` needs no code change — just restart the app.
- **Download source:** `https://www2.census.gov/geo/tiger/TIGER2024/ROADS/` → `tl_2024_08XXX_roads.zip` (08XXX = county FIPS; e.g. 08041 = El Paso). Missing FIPS list is in this session's notes / regenerable from the merged file's `county_fip` vs the 64 CO FIPS.

### 2026-07-07 — Elevation "not sampled" bug: one corrupt DEM tile was aborting the whole pull

**Symptom:** with elevation ticked in Tab 1, Tab 2's elevation chart showed "Elevation — not sampled (enable in Tab 1 raster variables)". **Root cause was NOT the code flow** (which is correct end-to-end — verified `process_data` → `sample_rasters` → `df_out` → cache/parquet all preserve `elevation_m`). It was a **corrupt/truncated DEM tile**: `MigrationAnalyzer/elevation/USGS_13_n42w106_20130911.tif` is **219 MB vs ~405 MB** for its siblings — a half-finished download. It opens (header intact) but reading the never-downloaded blocks raises `TIFFReadEncodedTile() failed`. The user's data reaches lat 41.10, which lands in that tile (n42w106 covers lat 41–42, Colorado's north edge). In `sample_rasters` the per-tile batch `ds.sample()` raised, propagated up, and the Tab 1 sampling `try/except` swallowed it as "raster sampling failed" — so `elevation_m` was **never added for ANY point**, not just the corrupt-tile ones.

**Fix 1 — resilience (`raster_sampler.sample_rasters`).** Wrapped the per-tile batch read in `try/except`; on failure it falls back to per-point windowed reads (`rowcol` + 1×1 `Window`), each individually guarded. A bad tile now NaNs only its own unreadable pixels instead of killing the whole variable. Verified on the real `D4_Test6` project (196,131 fixes): **193,003 (98.4%) now get elevation** (range 1525–3519 m, realistic for CO); only 3,128 northern-edge points in the corrupt tile stay NaN.

**Fix 2 — visibility.** `sample_rasters` records failed tile filenames in `df.attrs["dem_tile_errors"]`; the Tab 1 processing log now appends `WARNING: N fix(es) could not be sampled from corrupt/truncated DEM tile(s): <name>. Re-download from USGS 3DEP…` so a future bad tile is diagnosable from the UI instead of silently dropping data.

**Fix 3 — the actual source bug (no re-download needed).** A coverage/size audit of the whole CO area (lat 37–41, lon 102–109) showed: **CO-core interior (lat 38–41 × lon 103–109, 28 tiles) is complete and healthy**; absent border-ring tiles (n37 row, w102/w110 cols) are legitimately outside CO. Crucially, `n42w106` already has **three good full-size re-releases** (345/348/**358** MB) sitting next to the corrupt 219 MB `_20130911` copy — USGS re-issues cells under different dates and the folder kept them all. `_load_dem` was loading **all 51** files and, since each point matches the FIRST covering tile in sorted-filename order, it always hit the oldest (`20130911`, corrupt) copy. Fixed `_load_dem` to **dedupe by n{lat}w{lon} cell, keeping the LARGEST file per cell** (reliably skips truncated copies; also cuts loaded tiles 51→35, less memory). **Verified: D4_Test6 now samples 196,131/196,131 = 100%** (picks `n42w106_20230314.tif`, 358 MB; no tile errors). Fixes 1 (per-tile fallback) + 2 (warning) remain as safety nets for the true "only a corrupt copy exists" case. **No tile re-download required.** App imports clean (61 callbacks); files pass syntax.

### 2026-07-06 — Versioned outputs: each model run writes to ModelOutputs/V{n}/

Implemented the deferred "versioned output organization" item. Design decided with the user (three forks):
1. **Version boundary = each model run.** Clicking "Run Models" (Tab 3) starts a new `ModelOutputs/V{n}/` (n = max existing + 1); that run's model outputs *and* the Tab 4/5 population/export outputs built on it all land in that same `V{n}`.
2. **Carry-forward = reference, not copy.** Each version records paths to the shared inputs it drew from in `V{n}/version_manifest.json` — nothing is duplicated.
3. **Scope = only model + population outputs are versioned.** Tab 1 processed data (`processed_data.parquet`, `processing_log.txt`, `FlagsRemoved.gpkg`, `road_crossings.json`) and Tab 2 migtime (`Migtime Exports/`, `ResidentsNomadsRemoved.*`) stay **shared** at the `ModelOutputs/` top level and are referenced by every version.

Implementation (all in `main.py`):
- **New process-local `_ACTIVE_VERSION`** + helpers next to `_workdir_outputs`: `_list_versions()` (scans `ModelOutputs/V*`), `_workdir_version()` (active/latest version dir; falls back to latest-on-disk, else V1), `_start_new_version()` (max+1, sets active), `_write_version_manifest()` (writes `version_manifest.json`: version, created ISO timestamp, model, `model_params`, `parent_version`, `changed_from_parent` param diffs, and `shared_inputs` `../`-relative references).
- **`_workdir_outputs()` is now explicitly the SHARED top-level dir** (docstring updated); the versioned call sites were switched to `_workdir_version()`: Tab 3 UDs/Footprints/IndividualUDs/RangeUDs/BBMM_Output/herd-metadata/distance-CSVs/`model_results.csv`, the Tab 5 model+pop loaders (`load_previous_model_results`, `load_previous_pop_outputs` → latest version), the Tab 5 raster-overlay category scanner, and the Tab 5 export default directory. The vector-overlay scanner still `rglob`s the whole `ModelOutputs/` tree (finds versioned + shared). Tab 1/2 writes and the continuous `processing_log.txt` append stay shared.
- **`run_modeling`** calls `_start_new_version()` at the start of its workdir-write block, writes the manifest with the run's `param_fields`, and logs `version=` in the `RUN_MODELS` action.
- **Restart/re-open:** `_set_active_workdir` and the `render_workdir_state` restore path re-adopt the latest on-disk version (or None for a fresh workdir; the first model run creates V1).
- **Verified:** simulated two runs → V1/V2 created; V2 manifest correctly records `parent_version: 1`, param diffs (`bmvar 1000→1500`, `contour 99→95`, unchanged `max_lag` omitted), and `../`-relative shared-input refs; a simulated restart re-adopts V2. Full app imports with 60 callbacks (no errors).

**Follow-up same day — population re-runs also branch a version (per user).** Extended the version boundary: a model run is no longer the *only* trigger. If the user re-runs population outputs (Tab 4) with **changed options** and exports, the export branches a new `V{n}` that **references** (doesn't copy or recompute) the model run's UDs/Footprints/`model_results.csv`.
- **Branch detection is by population-config signature.** `_POP_OUTPUT_CACHE["config"]` holds the Tab 4 `pop_config`; `_POP_EXPORTED[version]` maps a version → the signature (`json.dumps(sort_keys)`) last exported into it. On export to the default workdir location, if the current version already has an export **and** the current signature differs, `handle_export` calls `_start_new_version()` and writes a population-branch manifest. Same options → no branch (re-exports into the same version). Changing only the Tab 5 checklist *selection* does NOT branch (that's just which files to write), only Tab 4 options do.
- **New state + helpers (`main.py`):** `_MODEL_SOURCE_VERSION` (version physically holding the in-use UDs), `_POP_EXPORTED` (seeded from disk via `_seed_pop_exported` on workdir load, updated by `_record_pop_export` which also persists `pop_config` + `population_exported:true` into the version manifest), `_pop_config_signature`, `_latest_version_with_model`, `_write_pop_version_manifest` (writes `type:"population"`, `parent_version`, `model_source_version`, `reused_from` model refs).
- **Population-branch manifest** carries `type:"population"`, `parent_version`, `model_source_version`, and `reused_from` = `../V{model}/UDs`, `/Footprints`, `/model_results.csv`.
- **Loader robustness:** `load_previous_model_results` now resolves the UD dir via `_latest_version_with_model()` (the latest version that actually contains `UDs/*.tif`), so a population-only latest version transparently reuses the model version's UDs. `_set_active_workdir` + the restore path set `_MODEL_SOURCE_VERSION` and seed `_POP_EXPORTED` from disk.
- **Verified:** model run V1 + export(configA) → recorded; export(configB, changed) → branches V2 with `parent_version:1`, `model_source_version:1`, `reused_from ../V1/…`; export(configB again) → no branch; `_latest_version_with_model()` returns 1 while active is 2; restart seeding recovers both versions' signatures.

**Follow-up same day — Tab 5 overlays are version-qualified (per user), resolving the raster-picker limitation above.** The Tab 5 raster-overlay **category dropdown is now dynamic and version-qualified**: `populate_raster_categories` enumerates every `V{n}/<subfolder>` that actually holds `.tif` files and offers them as e.g. "V1 · UD (per sequence)", "V2 · Population (banded)" (subfolders scanned: `UDs`, `BBMM_Output`, `IndividualUDs`, `RangeUDs`; empty ones skipped). The category value is version-qualified (`"V{n}/<sub>"`), and `populate_raster_overlay_files` resolves it under the shared `ModelOutputs/` root — so the user can view rasters from **any** version, including a model version whose UDs a later population-only version only references. The **vector-overlay** picker already labelled options by ModelOutputs-relative path (`V{n}/…/x.shp`), so it was already version-qualified. New callback → 61 total; verified category enumeration across two versions on disk (V1/UDs, V1/BBMM_Output, V2/BBMM_Output; empty `V2/UDs` skipped).

### 2026-06-29 — Tab 5 selective export; Tab 4 population outputs now fully deferred

Implemented the pending Tab 5 export-selection UI (resolves the "Pending (per user)" item from the 2026-06-24 stopover entry). Architecture decision (per user): **fully deferred** — Tab 4 computes every population product **in memory only** and writes **nothing** to disk; Tab 5 flushes the user-selected subset to `ModelOutputs/` on demand.

- **Compute/write split in `population_outputs.py`.** Factored `calc_season_banded_outputs` into:
  - `compute_season_banded_products(...)` — does all the banding math (count surface, mean-UD, minN, topP, stopover, isopleths) and returns an ordered list of **product descriptors** (`{key, kind, filename, label, array|gdf}`) with in-memory payloads. No disk I/O.
  - `write_product(product, out_dir, grid_meta)` — writes one descriptor; dispatches on `kind` (`count`→float32 w/ NaN nodata, `float32`, `uint8`, `vector`→shp).
  - `_mask_to_gdf(...)` — polygonize+cleanup extracted from the old inner `_write_mask_shp`.
  - `calc_season_banded_outputs` is now a thin wrapper (compute → write all) kept for backward compatibility; returns the same `{key: Path}` dict.
- **`main.py` — new `_POP_OUTPUT_CACHE`** (process-local, like `_MODEL_CACHE`; does **not** survive restart). `generate_pop_outputs` (Tab 4) no longer writes shapefiles/tifs — it builds `cache_products` (merged use/footprint contours + per-season banded sets + combined "All"), stashes payloads in `_POP_OUTPUT_CACHE`, and puts a JSON-safe `export_manifest` (id/label/category/rel_dir/filename/kind, no arrays) into `store-pop-outputs` for the UI. Preview cards relabeled "Ready to export — Tab 5".
- **Tab 5 Export card rebuilt.** Replaced the three placeholder buttons (Export Shapefiles / GeoTIFFs / Report) with a `dcc.Checklist` (`export-checklist`, grouped by category, all ticked by default) + **Export Selected** above **Export All**, plus Select all / Clear helpers. `populate_export_checklist` builds it from the manifest; the processing report is always offered as a synthetic `report::processing_report` option. `handle_export` rewritten to write the chosen products from `_POP_OUTPUT_CACHE` via `write_product` into `<out_dir>/<rel_dir>/<filename>`; reports per-file success/failures.
- **Consequence of full deferral (accepted, per user):** Tab 5's disk-scanning raster/vector overlays are empty until something is exported; the pop-use/footprint contour map overlay still draws from the `store-pop-outputs` GeoJSON. In-memory products are lost on app restart — regenerate Tab 4. The Tab 3 modeling writes (IndividualUDs, RangeUDs, MigLines, herd metadata) are a **separate** flow and were left untouched.
- **Verified:** `compute_season_banded_products` + `write_product` reproduce the same 13-file set as the legacy wrapper on a synthetic 2-UD grid; full app imports with 60 callbacks registered (no duplicate-output/ID errors).

#### Output inventory — what each tab writes to the working directory (`<workdir>/ModelOutputs/`)

Snapshot updated 2026-07-06 (versioned outputs). "Auto" = written by the app as a side effect of running that tab's step (only when a working directory is set in Tab 1). "User-specified" = nothing is written until the user chooses it. Update this block if the write paths change.

**Shared vs versioned (as of 2026-07-06):** Tab 1 + Tab 2 outputs are **shared** at the `ModelOutputs/` top level. Tab 3 + Tab 5 outputs are **versioned** under `ModelOutputs/V{n}/` — a new `V{n}` per model run. Paths below are relative to `ModelOutputs/` (shared) or `ModelOutputs/V{n}/` (versioned) as marked.

**Tab 1 — Data Processing** *(auto, on "Process Data"; SHARED — top level)*
- `processed_data.parquet` — cleaned/processed GPS table.
- `road_crossings.json` — road-crossing detection results.
- `processing_log.txt` — created here as the run report; later tabs *append* dated sections to this same file.
- `<Herd>_<Project>_FlagsRemoved_<DDMMMYYYY>.gpkg` — cleaned GeoPackage (kept fixes), via `write_flags_removed_shapefile`.
- *(Also: a persistent project copy of the processed parquet under `app/session_data/` — NOT in ModelOutputs.)*

**Tab 2 — Migtime / Sequences** *(auto, on "Export Updated Table"; SHARED — top level)*
- `Migtime Exports/migtime_<YYYYMMDD_HHMMSS>.csv` — the migtime table (friendly column names + seq_map legend).
- `ResidentsNomadsRemoved.csv` + `ResidentsNomadsRemoved.shp` — archived Resident/Nomadic animal-years (only if any were classified as such).
- `<...>FlagsRemoved.gpkg` — refreshed to reflect current flag edits; processed parquet re-flushed to disk.

**Tab 3 — Modeling** *(auto, when a workdir is set; the run itself is user-initiated; VERSIONED — under `V{n}/`, a new version created each run)*
- `version_manifest.json` — provenance: model, params, `parent_version`, `changed_from_parent` diffs, `shared_inputs` references.
- `UDs/*.tif` — per-sequence migration UD rasters.
- `Footprints/*.shp` — per-sequence movement footprints.
- `IndividualUDs/*.tif` — per-individual UDs *(only if the BBMM "per-individual UDs" box is ticked)*.
- `RangeUDs/averageUD_<season>.tif` (+ `RangeUDs/Individual_<season>/…`) — winter/summer range UDs *(only if the BBMM "ranges" box is ticked)*.
- `BBMM_Output/MigLines.shp`, `MigPoints.shp`, … — migration line/point products (`write_mig_outputs`).
- `<Herd>_metadata_<MMYYYY>.{csv,xlsx}` — herd-level metadata (`write_herd_metadata`).
- `<Season>_migration_distance_info.csv` — per-season distance summaries (`write_per_season_distance_csvs`).
- `model_results.csv` — one row per sequence (status/runtime/etc.).

**Tab 4 — Population Outputs** *(NOTHING auto-written as of 2026-06-29 — fully deferred)*
- Computes all population products **in memory** into `_POP_OUTPUT_CACHE`; nothing touches disk here. See the fully-deferred change above.

**Tab 5 — Export** *(USER-SPECIFIED — the only place Tab 4's population products reach disk; VERSIONED — default target is the current `V{n}/`, or a NEW branch version if population options changed since this version was last exported)*

The Tab 5 checklist exposes exactly the products computed by Tab 4. "Export Selected" writes the ticked items; "Export All" writes all of them (+ the report). Each writes to `<out_dir>/<rel_dir>/<filename>` (default `out_dir` = the current version's `ModelOutputs/V{n}/`; changing Tab 4 options and re-exporting branches to a new `V{n+1}` that references the model run's data):
- `popUseMerged/Pop_use_contours.shp` — merged population-use contours.
- `footPrintsMerged/Footprint_contours.shp` — merged footprint contours.
- `BBMM_Output/<Herd>_BBMM_<Season>_<MMYYYY>…` per season **and** a combined "All":
  - `.tif` (overlap-count surface) and `_meanUD.tif` (normalised mean-UD density)
  - `_min1/_min2/_min3` `.tif` + `.shp` (≥N-individual overlap bands)
  - `_top10/_top20` `.tif` + `.shp` (top-X% of use by count volume)
  - `_stopover` `.tif` + `.shp` (top stopover-% of mean-UD volume)
  - `_all.shp` (isopleth contour set)
- `processing_report.txt` — synthetic checklist option (always offered; needs Tab 1 processed data).

### 2026-06-26 — Consolidated MigLines + made season distance CSVs summaries

Migration distance outputs reorganized for usability (parity with `CalcSeqDistances.R` intentionally broken; per user).
- **MigLines_Dist removed; merged into MigLines.** `MigLines_Dist` was just `MigLines` + two distance columns, so `write_mig_outputs` (`population_outputs.py`) now writes a single `MigLines.shp` carrying all three per-sequence distances: `Eucl_Dist_` (first->last straight line, km), `Cumu_Dist_` (path length, km), and new `MaxPair_km` (greatest straight-line distance between any two fixes — the migration's max spread). Shapefile `.dbf` caps field names at 10 chars, so `MaxPair_km` (=10) is the longest usable on the shp.
- **`{Season}_migration_distance_info.csv` is now a season SUMMARY**, not per-sequence rows with repeated stats. Three rows (`eucl_firstlast_km`, `cumu_path_km`, `maxpair_spread_km`) × columns `mean_km, sd_km, min_km, max_km, n_sequences`. Long descriptive metric names live here (CSV has no field-name limit). Per-sequence distances now live on MigLines.shp instead.
- **New shared helper** `_line_distances_km(xs, ys)` in `population_outputs.py` returns `(eucl, cumu, maxpair)` km from ordered projected coords; used by both `write_mig_outputs` and `write_per_season_distance_csvs` so the three metrics are defined once. `calc_seq_distances` (modeling.py) is now unused by the app but left in place.
- **Clarified metric meanings** (these were a source of confusion): `MaxPair_km`/`maxpair_spread_km` is the max distance between ANY two fixes (not sequential, not start->end). `Eucl_Dist_` is start->end; `Cumu_Dist_` is total path length. Three distinct metrics, all per-sequence.
- Smoke-tested the helper (path (0,0)->(3000,0)->(3000,4000): eucl=5, cumu=7, maxpair=5 km; single point -> zeros). Glossary CSV not updated per user (kept as their working doc).

### 2026-06-25 — Dropped redundant combined_UD from RangeUDs/Individual_{Summer,Winter}

The range per-individual writer (`main.py`, inside the `want_ranges` loop) called `write_individual_uds(..., mode="both")` once per range season. Because each call passes only one season's sequences, the `mode="combined"` output (`AnimalID_combined_UD.tif`, grouped by animal) was identical to the `mode="season"` output (`AnimalID_<Season>_UD.tif`) — a pure duplicate. Changed that call to `mode="season"` so only `AnimalID_Summer_UD` / `AnimalID_Winter_UD` are written. The migration `IndividualUDs/` call still uses `mode="both"` (there "combined" genuinely merges all seasons, so it is NOT redundant). Updated the BBMM output glossary CSV to drop the two removed rows.

### 2026-06-25 — Processing filters honour the user: blank = disable, explicit 0 respected

Removed the hard-coded fallback defaults for the Tab 1 filter thresholds (per user). The app now does exactly what the user enters.
- **Two bugs in the old `float(x or default)` pattern (`main.py` config assembly):** (1) a cleared box silently re-applied a default; (2) a user-entered **0** is falsy, so `0 or default` turned it into the default too. Replaced with a `_num_or_none(v)` helper → blank/`""` → `None`; any explicit value (including 0) → `float(v)`.
- **Disable semantics (None = skip that check):** `flag_problem_points` skips speed / DOP / satellite independently when its threshold is None; `check_mortality` returns all-unflagged if **either** distance or time is None; `quality_filter` logs each DOP/sat check as "disabled" when None. Affected filters: max speed, mortality distance, mortality time, DOP cutoff, satellite cutoff.
- **Kept defaults intentionally:** bio-year start month/day and the column-name inputs are **structural** (drive year grouping / column resolution, not filters), so they still default when blank (Feb 1, `LoclAID`/`DT_MST`/`Long`/`Lat`) rather than disabling — a blank bio-year would break `calc_bio_year`.
- **Plumbing:** `process_data` passes `cfg.get(...)` (None-able) into all three functions; log lines report active criteria or "disabled"/"all disabled". `DEFAULT_CONFIG` still holds the old numbers for any *non-UI* caller of `process_data`, but the UI now overrides with None when blank.
- **Verified** with a smoke test: all-on flags the bad fix; all-None disables; DOP-only works; `sat_cutoff=0` flags nothing (proves literal 0 is honoured, not coerced to 6); mortality-off leaves all unflagged.

### 2026-06-25 — DOP/satellite fixes flagged not dropped; two dark-theme label fixes

**DOP & satellite quality fixes now FLAGGED, not dropped.** Previously `quality_filter` (`data_ingestion.py`) deleted fixes with `DOP > dop_cutoff` or `NumSats < sat_cutoff`, so they never reached Tab 2. Per user, those fixes should stay visible on Tab 2 and be auto-flagged as problem points instead.
- `quality_filter`: removed the two DOP/sat drop steps (now logs the counts as "kept, will be flagged"). Still drops **unmappable** rows — positive longitude (Germany/test) and NA coordinates — since those can't enter geometry math.
- `flag_problem_points`: gained `dop_cutoff` / `sat_cutoff` params; `problem=1` now if **speed > max** OR **DOP > cutoff** OR **NumSats < cutoff** (NA values never flag). `DOP`/`NumSats` survive into `gdf` because `load_data` only renames columns. Verified the point cache stores `problem` (`main.py:5035`) and `_build_point_geojson` renders it with the "problem" marker (`main.py:5112`).
- `process_data`: passes `cfg["dop_cutoff"]`/`["sat_cutoff"]` into `flag_problem_points`; log message updated.
- **Side effect (acceptable):** kept low-quality fixes now participate in movement-param/NSD computation (a high-DOP fix with a wild coordinate can inflate a neighbour's speed and get it flagged too). Downstream `extract_sequences` still excludes all `problem`/`mortality_flag` points, so modeling is unaffected. Behavioral (speed/mortality) flagging was already flag-not-drop and unchanged.
- **Empty processing parameters:** clearing the Tab 1 inputs does NOT disable filtering — each blank falls back to a hard-coded default via `float(x or default)` (max speed 10.8, DOP 10, sats 6, mortality 50 m / 48 h, bio-year Feb 1). No error. **(Superseded same day — see "blank = disable" entry below.)**

**Two dark-theme (CYBORG) label visibility fixes in `main.py`:**
- `model-cores` slider marks: now `{i: {"label": str(i), "style": {"color": "white"}}}` so the numbers under the slider are visible.
- `pop-contour-type` radio (Area/Volume): added `labelStyle={"color": "white"}`.

### 2026-06-24 — Population stopover output (Migration Mapper-style)

Added a stopover product to the per-season banded population outputs, matching Migration Mapper's definition.

- **What a stopover is here:** the top **10%** of the population **mean-UD volume** — the densest cells whose cumulative UD probability mass reaches 10%. This mirrors MM's `create.corridors.stopovers.R` (MAPP 2.x) / `CalcPopUse.R` Volume contour (MAPP 3.x), which take the population average UD, convert to a volume contour (`getVolumeUD`), and keep the top `stopover_percent`%. It is a **population-level** product computed from the already-combined mean UD — NOT per-animal behavioral stopovers (no residence-time / speed thresholding). BBMM density already concentrates where animals moved slowly (the bridge variance uses inter-fix time lags), so the dense UD core is MM's space-use proxy for a stopover.
- **Why mean-UD volume, not the count surface:** deliberately different from the existing `_top10/_top20` bands, which rank the **overlap-count** grid (closer to MM *corridors*). Stopovers use the `mean_ud` density (also written as `_meanUD.tif`), matching MM's stopover input exactly.
- **Implementation** (`app/modules/population_outputs.py`, `calc_season_banded_outputs`): new `stopover_pct: float = 10.0` param; section "3b" ranks `mean_ud` descending, accumulates to `stopover_pct%` of total mass, writes `{prefix}_stopover.tif` (uint8 mask) + `{prefix}_stopover.shp`. Reuses `_write_mask_shp` for small-patch cleanup (`min_area_drop`, default 20,000 m² — matches MM's `min_area`); generalized `_write_mask_shp` with an optional `value` arg so the shp records the percent. Returned `written` dict gains `stopover_tif` / `stopover_shp` keys. Set `stopover_pct=0`/None to skip.
- **Wiring:** both `calc_season_banded_outputs` call sites in `main.py` use `pop_config["stopover_pct"]`, so stopovers generate per season + the combined "All" pass during BBMM population output. The Tab 4 preview "banded outputs" helper text and config summary now list the stopover density.
- **Where stopovers are written:** `<workdir>/ModelOutputs/BBMM_Output/<herd>_BBMM_<season>_<date>_stopover.{tif,shp}` (same folder/prefix as the other banded outputs), produced when "Generate Population Outputs" runs with a workdir set.
- **Tab 4 UI — "Calculate stopovers" checkbox + collapsible density.** A `pop-stopover-toggle` checkbox (default **ticked**) sits above the "Generate Population Outputs" button. When ticked, a `dbc.Collapse` (`pop-stopover-collapse`) reveals the "Stopover Density (%)" input (`pop-stopover-pct`, default 10, min 0 / max 100) with helper text: *"Recommended: 10 — the top 10% of the population-level UD considered as stopovers, consistent with WMI's Migration Mapper."* A small callback `toggle_stopover_pct` opens/closes the collapse from the checkbox. Plumbing: `State("pop-stopover-toggle")` + `State("pop-stopover-pct")` → `generate_pop_outputs(stopover_on, stopover_pct, ...)` → `pop_config["stopover_pct"]` (set to **0.0 when unticked**, which skips the output via the `stopover_pct > 0` guard) → both `calc_season_banded_outputs` calls.
- **[DONE 2026-06-29] Pending (per user):** a Tab 5 checkbox UI to let users pick exactly which outputs to export (stopovers one option). Implemented as a fully-deferred export — see the 2026-06-29 Setup Log entry. This 2026-06-24 entry built the *capability* + Tab 4 density control; the Tab 5 export selection now exists.

### 2026-06-22 — Tab 1: removed snow environmental variables; elevation now defaults to checked

UI trim of the Tab 1 "Environmental Variables" card (per user).

- **Removed the three snow boxes** (Snow Depth, Snow Water Equivalent, Snow Density) by reducing `AVAILABLE_VARIABLES` in `app/modules/raster_sampler.py` to just `elevation_m`. That dict is the single source for the `raster-var-checklist` options, so the boxes vanish and snow stops being sampled. Rationale: most users don't want snow, and anyone who does can upload a `.wld` file containing it. The SNODAS sampling code in `raster_sampler.py` is kept (harmless, still callable) so the capability can be restored by re-adding the entries.
- **Elevation now defaults to checked.** Changed the `raster-var-checklist` default from `value=[]` to `value=["elevation_m"]` in `main.py` — elevation is wanted in nearly every run; users can still uncheck it to skip DEM sampling. Updated the adjacent comment and dropped the now-stale "& SNODAS" mention from the helper text ("Sampled from the MigrationAnalyzer DEM (10m)").
- **Left intact:** the enrichment-column detector in `main.py` (~line 640) still checks for `snow_depth_m`/`swe_m`/`snow_density_kgm3` in *loaded* projects, so a project that already has snow columns (e.g. from a `.wld`) still surfaces them. Both files parse clean.
- **DEM helper text — dropped SNODAS, cite the real source.** The small text under the DEM checkbox previously read "Uses MigrationAnalyzer DEM (10m) & SNODAS (1km daily)". Removed the SNODAS half (snow is gone from the UI) and renamed the source: it's not a "MigrationAnalyzer DEM" — the tiles in `MigrationAnalyzer/elevation/` are named `USGS_13_nXXwYYY.tif`, the canonical USGS naming where `13` = **1/3 arc-second** (≈10 m), from the **USGS 3D Elevation Program (3DEP)** distributed via The National Map. New text: *"Sampled from the USGS 3DEP 1/3 arc-second DEM (~10 m)."* (`main.py`, the `html.Small` below `raster-var-checklist`.)
- **Note for testing these UI changes:** `Start App.bat` runs the server without Dash hot-reload, so code edits don't appear until the server window is closed and relaunched (then hard-refresh the browser, Ctrl+F5). The "DEM not pre-ticked / SNODAS still shown" the user saw after the edits was a stale running instance, not a code problem.

### 2026-06-22 — Pinned `requirements.txt` to demoed versions; considered async backend and rejected it

Post-demo dependency hardening. Two related decisions:

- **Considered an async (Quart/ASGI) backend; rejected.** There is no separate Quart or FastAPI backend in the repo — the app is Dash on its built-in Flask (WSGI) server (`server = app.server`), and the main app being built is itself Dash-on-Flask, so Flask is already the congruent stack. Async was evaluated for "could help users" but doesn't fit this workload: the slow paths (`modeling.py` Kernel UD/BBMM, `population_outputs.py`, `raster_sampler.py`, `data_ingestion.py` cleaning 100k+ fixes) are **CPU-bound** — async only helps I/O-bound concurrency, and the app is a single-user desktop deploy (`Start App.bat` → `127.0.0.1:8050` → opens browser). Async would add risk across the ~7,500-line `main.py` for no real gain. If UI-freeze-during-modeling becomes the complaint, the right fix is **Dash background callbacks** (DiskcacheManager local / CeleryManager multi-user), not async. If ever hosted multi-user, scale with WSGI workers first — note `_DF_CACHE` is a per-process in-memory dict and would need a shared cache (Redis) before running multiple workers.

- **Pinned `requirements.txt` to the exact demoed versions.** The file previously used loose `>=` lower bounds, so a fresh `Setup.bat` on a new machine would pull whatever is newest that day (e.g. a future Dash 5) and could break an app whose code never changed. The installed/demoed env was already ahead of the old floors (Dash 4.1.0, dash-bootstrap-components 2.0.4, dash-leaflet 1.1.3, plotly 6.7.0, pandas 3.0.3, numpy 2.4.5, etc.), so pinning to `==` those versions freezes the known-good state. `pip install -r requirements.txt --dry-run` resolved with no conflicts; `main.py` parses clean. To bump later: change one pin → reinstall → run `Start App.bat` → click through the tabs → keep or revert that single line.

### 2026-06-16 — Tab 5: stack multiple output rasters + vector overlays on the map

Reworked Tab 5's overlay UI from single-select to multi-overlay (`main.py`).

- **Rasters:** the "File" picker is now `multi=True` ("Files (stack several)") plus a "Select all in category" button. The single `dl.ImageOverlay(id="raster-overlay")` was replaced by `dl.LayerGroup(id="raster-overlay-group")`, whose children are built one `ImageOverlay` per selected `.tif` (`render_raster_overlays`). Per-file PNG warp/encode is memoised in `_OVERLAY_CACHE` (keyed by path+mtime+cmap) so the opacity slider only rebuilds the component tree.
- **Vectors:** new "Vector Overlays (.shp / .geojson)" card — `populate_vector_overlay_files` scans `ModelOutputs/` **recursively** for `.shp`/`.geojson`, labels them by path relative to ModelOutputs (so duplicate names stay distinct), multi-select + "Select all" + "Refresh list". `render_vector_overlays` reads each via geopandas, reprojects to EPSG:4326, and draws one colour-cycled `dl.GeoJSON` per file into `dl.LayerGroup(id="vector-overlay-group")`. Non-JSON (datetime) columns dropped before serialisation; geojson cached in `_VECTOR_CACHE`. A fill-opacity slider applies to all vector layers.
- Existing population use/footprint contour layer (`map-geojson-contours`, from Tab 4) is unchanged and still toggled via the Layer Controls checklist.
- Decisions (per user): rasters = multi-select stack (not a blanket show-all, to control load); vectors = whatever shapefiles already exist in ModelOutputs.

### 2026-06-16 — Coarse-fix BMVar fallback changed 5000 → 1000

`get_model_config` previously auto-set `bm_var=5000` when median fix rate > 12 h. The `5000` and the `>12h` rule were **port-specific inventions** — neither appears anywhere in the reference R workflow (`WesternCorridorMappingTeam-main`: MAPP3.x defaults `BMVar=NULL`, i.e. always EB; Chloe forces 1000 md/bighorn, 1400 elk; Jaffe forces 1000). Changed the fallback value to **1000** to match Jaffe/Chloe's mule deer/bighorn FMV. The `>12h` auto-trigger itself is retained as a safeguard (still not in any reference). Updated value + comments in `modeling.py:get_model_config` and the Tab 3 auto-logic message/comments in `main.py`. Elk would arguably want 1400 — left single-value for now (see the conditional-BMVar entry below re: per-species thresholds).

### 2026-06-16 — Tab 3 BBMM: conditional BMVar by fix-rate threshold (Chloe-style)

Added a per-sequence conditional FMV/EB switch on Tab 3, adapted from Chloe's CB_MAPP workflow. Rationale: Chloe forces a fixed motion variance (FMV) for coarse-fix data and estimates it (EB) for fine-fix data; we now expose the same idea in the UI.

- **UI** (`main.py`, `render_model_params`, BBMM panel): new checkbox `bbmm_bmvar_conditional` ("Conditional BMVar by fix-rate threshold") + numeric `bbmm_bmvar_threshold` (default 5, units "hrs between points").
- **Behaviour:** when the box is checked AND a BMVar number is entered, each sequence whose **median** gap between fixes is **> threshold** uses the entered BMVar (FMV); sequences with finer fixes (≤ threshold) estimate variance (EB). Unchecked = unchanged behaviour. No effect if BMVar is left blank.
- **Plumbing:** `_apply_model_ui_params` writes `config["bm_var_fix_rate_threshold_hours"]`; `calc_bbmm_stub` forwards it; `calc_bbmm` gained a `bm_var_fix_rate_threshold_hours` arg and decides EB vs FMV per sequence at the variance step. Metadata/log now report a `variance_mode` of `EB`/`FMV`/`EB (conditional)`/`FMV (conditional)`.
- **Departure from Chloe:** fix rate is derived **per sequence from the timestamps** (median gap), not read per-collar from a metadata CSV — closer to Jaffe's data-driven approach. A single threshold applies to all (Chloe used 5h md/bighorn, 3h elk). Revisit if per-species/per-collar thresholds are needed.

### 2026-06-16 — BBMM extras: winter/summer range UDs + per-individual UDs + FMV note + expanded herd metadata (km & annual collars)

Driven by the cross-script comparison of WMI MAPP vs Jaffe vs Chloe workflows. Five related changes.

- **Verified already present (no change needed):** (1) the **99.99% tail cutoff before normalization** runs in both `calc_bbmm` and `calc_kernel_ud` (`_apply_tail_cutoff(..., 0.9999)`); (2) the **population mean-UD density surface** is written as `_meanUD.tif` by `calc_season_banded_outputs`.

- **FMV note (UI).** Under the BBMM "Brownian Motion Variance" box, appended: *"Often 1000 for Mule Deer/Bighorn, 1400 for elk."* (the USGS species guidance Jaffe/Chloe use).

- **Winter & summer range UDs (new, Chloe 3b/3c-style).** New BBMM-panel checkbox **"Winter & summer range UDs"** + a **"Range min. days of data"** input (default 30). On a BBMM run with a workdir, `build_range_sequences` (`modeling.py`) derives, per animal-year, the **summer** window (spring-end → fall-start) and **winter** window (fall-end → next-year spring-start). Spring vs fall is identified by **Tab-2 season labels if present (contains 'spring'/'fall'), else by date order** (earliest window = spring, latest = fall). Animal-years are **skipped — and individually noted in `processing_log.txt`** — when a bounding migration date is missing (no population-mean fallback, per user choice) or the window has fewer than `mindays` distinct days of fixes. Each season's range sequences run through BBMM (same config), then `write_range_density` averages per-individual (across years) → mean across individuals → `RangeUDs/averageUD_Summer.tif` / `averageUD_Winter.tif` (**mean-UD density only**, like Chloe — no count/min/top). Range BBMMs reuse the migration config but don't write per-seq tifs into `UDs/`.

- **Per-individual UDs (new).** New BBMM-panel checkbox **"Per-individual UDs"**. `write_individual_uds` writes, per animal, **both** a per-season UD (`<animal>_<label>_UD.tif`) **and** a combined UD (`<animal>_combined_UD.tif`) into `ModelOutputs/IndividualUDs/` (and `RangeUDs/Individual_<season>/` when ranges are also on). Averaging is **normalize-then-average** (our `_meanUD` convention) — note this differs slightly from Chloe's *99%-then-average* for her density product (flagged for exact parity later). Animal/label grouping uses explicit `seq_animal`/`seq_label` maps built in `run_modeling` (animal ids contain underscores, so the mig_key can't be split positionally).
  - Both options are passed as pattern-matching model-param inputs (`bbmm_individual`, `bbmm_ranges`, `bbmm_range_mindays`) so the `ALL`-matched State in `run_modeling` reads them without the "nonexistent object" error; `_apply_model_ui_params` ignores them (they're run options, not calc params).

- **Expanded herd metadata (combine Jaffe + Chloe).** `write_herd_metadata` already produced sex counts (Males/Females), median per-season start/end dates, and distances in **miles** (cumulative + euclidean). Added: (a) **kilometres alongside miles** for every cumulative/euclidean distance stat (`avg/min/max_mig_km_cumu_<seas>`, `..._km_eucl_<seas>`, `..._all`); (b) **annual active collars** (unique animals per `bio_year`) both as `ActiveCollars_<year>` rows AND a dedicated `<herd>_annualCollars_<MMYYYY>.csv` mirroring Chloe's `metadata_annualCollars.csv`. Active collars are counted by **biological year** (matches Chloe's `nsdYear`).

- **Logging.** `run_modeling` writes `PER-INDIVIDUAL UDs` and `WINTER / SUMMER RANGE UDs` sections (counts, per-season summary, mindays, and the per-animal skip notes, capped at 40) to `processing_log.txt`, plus `INDIVIDUAL_UDS` / `RANGE_UDS` lines to `session_log.txt`. The new annual-collars CSV is included in the existing metadata-files log line.

**Verification.** App imports/registers clean. Unit-tested on synthetic data: `build_range_sequences` (correct summer/winter windows, correct skip notes incl. last-year winter, underscore animal ids handled), `write_individual_uds` (per-season + combined, correct grouping), `write_range_density` (per-individual→population, sums to 1), and `write_herd_metadata` (sex, dates, miles+km, ActiveCollars rows + dedicated CSV). **Not yet exercised:** a full in-app BBMM run with the new checkboxes on (user testing next) — note winter-range BBMMs can be slow (months of fixes per individual).

**Files touched.** `app/modules/modeling.py` (`build_range_sequences`, `_normalize_ud`/`_mean_normalized`/`_safe_token`/`_valid_uds_grouped`, `write_individual_uds`, `write_range_density`), `app/modules/population_outputs.py` (`write_herd_metadata`: km rows, annual-collars rows + CSV; per-seq km), `app/main.py` (BBMM panel: FMV note + 3 new option controls; modeling imports; `seq_animal`/`seq_label` maps; post-modeling per-individual + range block + logging), `INFORMATION.md` (this entry).

### 2026-06-15 — Tab 5 map fixes: render-on-tab-open + working Topographic/Satellite basemap toggle

- **Map only drew after opening DevTools (Ctrl+Shift+I).** `dbc.Tabs` renders all five tab panes at load and hides inactive ones with `display:none`, so Tab 5's dash-leaflet map (`main-map`) initialised inside a 0×0 hidden container and drew no tiles. Leaflet only re-measures (`invalidateSize()`) on a window `resize` event — which is exactly what opening DevTools fires, so the map appeared then. **Fix:** a clientside callback on `main-tabs.active_tab` — when it becomes `tab-5`, dispatch `window 'resize'` a few times (60/250/600 ms, to cover the brief delay before the pane is visible/measurable) so Leaflet lays out tiles on its own. (Output is a throwaway `main-map.id` returning `no_update`.) Note this didn't affect Tab 2's map because that one is a self-contained MapLibre `<iframe>`.
- **Basemap toggle did nothing + labels unreadable.** The `map-base-layer` radio existed but **no callback read it** — the `dl.TileLayer` url was hardcoded to Esri satellite — so clicking the other option changed nothing. The radio also defaulted to `osm` while the map showed satellite (inconsistent), and its labels were dark-on-dark. **Fix:** (1) labels turned white (`labelStyle`/Label `color:#FFFFFF`); (2) options changed to **Topographic** / **Satellite**, default **Satellite** (`value="esri"`, matching what's shown); (3) gave the TileLayer `id="base-tile-layer"` and added a `switch_basemap` callback (`Input map-base-layer.value → Output base-tile-layer.url/attribution`) using `_BASEMAP_TILES` — Satellite = Esri World Imagery, Topographic = Esri World Topo Map (same provider, no API key). Toggling now swaps the basemap live.

**Files touched.** `app/main.py` (Tab-5 basemap radio labels/options/default; `base-tile-layer` id; `switch_basemap` callback + `_BASEMAP_TILES`; clientside tab-5 resize callback), `INFORMATION.md` (this entry).

### 2026-06-11 — REFERENCE: two BBMM/population methodologies (WMI MAPP vs Jaffe USGS-style) — which we trust and how they differ

**Trust ranking (decided with the user).** **`code2run.R` (WMI MAPP3.x) is the source of truth** — most up-to-date, comes from the Wyoming Migration Initiative / Western Corridor Mapping Team. **`MAPP.R` is an okay back-pocket reference.** The example outputs we were comparing against (`MM_E18_E22_Example/.../Jaffe_Output0403`) were produced by a **third, different script** — `C:\Users\shadwelk\Downloads\BBMM Processing with USGS function (For E18 E22).R` (N. Jaffe, 7/2024), which follows **USGS/Sawyer conventions, NOT the WMI MAPP pipeline.** So the `min1/min2/min3` + `top10/top20` + integer-count tifs we've been matching are a USGS-style product, and the official MAPP `CalcPopUse` doesn't even produce them. This matters: aligning to Jaffe means committing to USGS conventions that differ from WMI MAPP on both the BBMM side and the population-aggregation side.

**The two traditions, side by side.**

| Aspect | WMI MAPP3.x (`code2run.R` / `CalcBBMM.R` / `CalcPopUse.R`) — TRUSTED | Jaffe USGS-style script (the example we compared to) |
|---|---|---|
| BBMM motion variance | `BMVar = NULL` → **EB (estimated)** by default; no fix-rate switching | **Per-sequence rule:** avg fix rate > 7 h → **forced FMV** (`FBMV = 1000` elk / 800 deer); ≤ 7 h → EB. (USGS recommendation) |
| `max.lag` | **8 h** | **27 h** (`27*60` min) |
| `time.step` / `location.error` | 5 min / 20 m | 5 min / 20 m (same) |
| Per-individual footprint contour | 99% (`contour=99`) | 99% (`CalcVol` cuts at cumsum ≥ 0.99) (same) |
| Grid | `CalcPopGrid`: proportional `mult4buff` (0.3), `cell.size` 500 in code2run | `ext(locs) + 10000` (**fixed 10 km** buffer), `cell.size = 250` |
| Per-individual collapse | **Yes** — `merge_order = c("id","year")` averages across years within individual first | **Yes** — `mean()` per `newUid` across that animal's seasonal UDs |
| Population product | **UD-density % isopleth contours** (Area or Volume), with ksmooth smoothing + drop_crumbs + fill_holes; output = `popUseMerged` / `footPrintsMerged` contour polygons | **Sum of binary 99% footprints = overlap COUNT raster**, then `min1/2/3` (count > 0/1/2) and `top10/20` (cells above the 90th/80th **percentile of non-zero counts**); no smoothing, no min-area, no % contours |
| Output form | contour polygons (density isopleths) | count raster + threshold masks (tifs/shp) |

**Key methodological notes (for whoever picks the standard later):**
- **Animal-years vs unique individuals (overlap count).** Both reference methods collapse to **unique individuals** (equal weight per animal) — this is the field standard; counting animal-years pseudoreplicates (long-collared animals dominate; repeated years aren't independent samples of *where* the corridor is) and breaks the "number of animals" meaning of min1/min2/min3. Counting all animal-years is only appropriate if the question is "use intensity / total traffic." **Our app's `calc_season_banded_outputs` currently counts animal-year sequences, not unique individuals** — diverges from BOTH references (inflates counts; e.g. an elk collared 4 yrs counted up to 4×). A code change (group ud_dict by individual, average across years, then count) is needed to match either standard.
- **top10/top20 method.** Percentile-of-non-zero (Jaffe) = "highest-use X% of the corridor **area**" — interpretable, but integer-count ties make the cutoff lumpy. Cumulative-mass / volume isopleth (our current code) = "smallest area holding X% of the use **mass**" — the textbook UD-isopleth definition, best applied to a true probability density (the `meanUD` product), not the count surface. Recommendation if we go this route: percentile-topX on the **count** surface, volume-isopleth on the **density** surface.

**What our app implements today.** Both families coexist: `popUseMerged`/`footPrintsMerged` (MAPP `CalcPopUse`-style % contours) AND the `BBMM_Output` banded set (Jaffe/USGS-style count + min/top). Our BBMM port (`calc_bbmm`) follows MAPP `CalcBBMM` (EB default, max.lag 8 h) — i.e. the trusted lineage — NOT the Jaffe USGS variant (FMV-1000-at->7 h, max.lag 27 h).

**Open decision (not yet made).** Which standard is CPW's source of truth? It forks both the BBMM parameters (EB vs USGS-FMV; max.lag 8 vs 27) and the population aggregation (density % contours vs footprint-overlap count). Per the trust ranking, **lean WMI `code2run.R`** unless CPW specifically wants USGS-style products. To exactly reproduce the Jaffe example, you'd need: max.lag 27, the >7 h→FMV 1000 rule (per-sequence; our single-BMVar control can't do this — blank≈EB matches the ~4 h-fix majority of E18/E22), per-individual count collapse, and percentile-topX — several of which are deliberate departures from the trusted code2run.R.

**No code changed in this entry — documentation only.** Source: `BBMM Processing with USGS function (For E18 E22).R` read in full; `code2run.R` / `CalcBBMM.R` / `CalcPopUse.R` in `WesternCorridorMappingTeam-main/MAPP3.x_code_workflow/`.

### 2026-06-11 — Population outputs reworked to match Migration Mapper (count surface, 250 m grid, animal-overlap contour bands) + full workflow logging

Driven by a direct comparison of our `BBMM_Output` vs Migration Mapper's (`C:\Users\shadwelk\Documents\ImportTest\ModelOutputs\BBMM_Output` vs `C:\Users\shadwelk\Documents\MM_E18_E22_Example\2026\BBMM_Output\Jaffe_Output0403`).

**Diagnosis (why ours looked different — "splotchy / different value ranges").** The main per-season tif was a fundamentally different product:
- **MM main tif** = integer **overlap-count** surface (values 1..N individuals; e.g. Spring 1–27, All 1–42), float32 with `nodata=nan`. Its non-zero extent equals its own `min1` tif → confirmed it's the sum of individual footprints.
- **OUR main tif** = normalized **mean-UD density** (sum=1, values ~1e-9..1e-3) → concentrates near high-use cells ("splotchy"), totally different value range.
- Reassuringly, individual coverage was close: `min1` areas ours ≈ 3,350 km² vs MM ≈ 3,080 km² — so the BBMM footprints themselves are comparable; we were just writing the wrong main product, on a coarser grid (ours 500 m vs MM 250 m).

**Changes made (per user direction).**

1. **Default grid cell size 500 → 250 m, user-overridable.** `create_population_grid` and `get_model_config` defaults are now 250. New Tab-3 input **`model-cell-size`** (default 250) is read by `run_modeling` (`cell_size_m`) and passed to `create_population_grid`. Note: 250 m is ~4× the cells of 500 m → slower but matches MM and far less blocky.

2. **Main per-season tif → overlap-count surface (matches MM); density kept as a separate file.** In `calc_season_banded_outputs`: new `_write_tif_count` writes `count_grid` as float32 with `0 → NaN` (`nodata=nan`) as the main `<Herd>_BBMM_<season>_<date>.tif`. The normalized mean-UD density is still written, now as `..._meanUD.tif`. Verified: main tif shows integer values 1..N with nan background; `_meanUD` sums to 1.

3. **`top10/top20` computed on the broad use (count) surface**, not the concentrated mean-UD density (which gave tiny specks — ours were 68/180 cells vs MM's 4,129/8,771). Now rank cells by overlap count descending and accumulate to X% of total count mass.

4. **Population contour levels now prepend "≥1 animal" and "≥2 animals" bands** ahead of the user's percent levels (matches MM). In `generate_pop_outputs`: with N sequences, in Area mode a level X% means "cells where ≥X% of individuals overlap", so ≥1 animal = `100/N %` and ≥2 = `200/N %`. These are merged into `contour_levels` (so `calc_population_use` / `calc_population_footprint` produce those outer bands); `animal_band_levels` maps the level→count for labelling/logging.

5. **`processing_log.txt` (ModelOutputs/) is now a full workflow record.** New `_append_processing_log(lines, header)` appends dated sections to the same file the Tab-1 processing report starts. Added: a **DATA PROCESSED** timestamp header (process_uploaded_data), **MIGTIME TABLE EXPORTED** (export_migtime), **MODEL RUN** (run_modeling — model, cell size, cores, median fix rate, every parameter *with values incl. defaults*, OK/error counts, per-sequence errors, runtime, output folders; logged on success AND on failure), and **POPULATION OUTPUTS** (generate_pop_outputs — seasons, merge order, contour type, contour levels annotated with the ≥1/≥2-animal tags, min-area/smoothing settings, sequences used, success/error, runtime, and the exact files written; logged on success, 0-contours, and failure).

**Verification.** App imports/registers clean; `calc_season_banded_outputs` round-tested on synthetic UDs (main=count 1..N nan-bg, `_meanUD` sum=1, min/top present). The Dash-callback pieces (cell-size flow, ≥1/≥2 contour bands, log appends) compile/register but need a live run to confirm — user testing next.

**Still open.** After the user re-runs at 250 m: re-compare the count main tif to MM's (value range + extent should now align), and re-check whether the EB-likelihood fix left coverage close to MM or undershooting. The `top10/20`-on-count definition is our best read of MM's; exact MM topX definition still unconfirmed.

**Files touched.** `app/modules/modeling.py` (`create_population_grid` default, `get_model_config` cell_size); `app/modules/population_outputs.py` (`_write_tif_count`, main=count + `_meanUD`, top on count surface); `app/main.py` (`model-cell-size` UI + wiring; ≥1/≥2 contour bands; `_append_processing_log` + DATA PROCESSED / MIGTIME / MODEL RUN / POPULATION OUTPUTS sections); `INFORMATION.md` (this entry).

### 2026-06-10 — Modeling: EB-likelihood fix, parameter-flow verification, Kernel fixes (working toward Migration Mapper parity)

Context: the user's output tifs look different from Migration Mapper's, and we're isolating **parameter** differences from **modeling** differences. Steps taken so far:

- **BBMM EB motion-variance likelihood fixed (`modeling.py` `_estimate_brownian_motion_variance`).** The negative log-likelihood used `sq/v` for the data term; the correct 2-D bivariate-normal term is `sq/(2v)` (each coordinate is N(0, v) with the same v, so per-triplet −loglik = `log(v) + (dx²+dy²)/(2v)`; `sq` already holds `dx²+dy²`). The old `sq/v` double-weighted the residual and biased the estimated Brownian motion variance **high** → over-diffuse UDs. After the fix the EB estimate drops (test sequence: ~halved, tighter footprint), which should move our UDs toward R's. This is a genuine *modeling* correctness fix (matches BBMM's `brownian.motion.variance`), independent of the parameter question.

- **Verified that UI model parameters are actually used (not silently defaulted).** Audited the full chain `model-param panel → run_modeling State({"type":"model-param","key":ALL}) → _apply_model_ui_params → config → run_model → calc_*`. Confirmed config-level override for **every** method: BBMM (bm_var, location_error, max_lag, time_step, contour, mult4buff), Kernel (smooth_param, contour), LineBuffer (buff_distance), dBBMM (window, margin, location_error, contour), CTMM (info_criteria, contour). Confirmed **end-to-end for BBMM** that values reach the computation (run metadata echoed bm_var/loc_err/max_lag/contour; changing contour 99→50 and bm_var 500→5000 changed the footprint). Blank fields correctly keep the computed default.
  - **Caveat to remember:** BBMM's BMVar, *when left blank*, is still forced to 5000 if median fix rate > 12 h (`get_model_config`); a typed value always wins. This auto-FMV path is a prime suspect for output divergence vs Migration Mapper (which always uses EB / `BMVar=NULL`).

- **Kernel UD fixes (`modeling.py`).**
  - **Crash fixed:** `calc_kernel_ud` chained `.drop(columns="_yr_jul")` after a `groupby.apply`; pandas ≥2.2 excludes the grouping column from the apply result, so the drop raised `KeyError: ['_yr_jul']` and broke the Kernel model whenever subsampling ran. Split the drop out with `errors="ignore"` so it's version-safe.
  - **Default `subsample` `1 → None`:** R's `CalcKernel` defaults to `subsample=NULL` (no subsampling); our default of `1` kept only ~one fix per year+Julian-day — a large unintended data reduction that would also diverge from Migration Mapper. Now keeps all fixes by default; the (now working) block still honours an explicit value.
  - Verified: Kernel runs clean at the default (all fixes kept, auto href bandwidth), honours a forced bandwidth/contour, and the subsample block no longer crashes.

- **Still open (the actual parity investigation).** We have NOT yet determined whether the tif divergence is parameters or modeling — that needs a controlled comparison: run our BBMM on one sequence with Migration Mapper's exact parameters (EB, locerr 20, max.lag 8, time.step 5, contour 99, mult4buff 0.3, cell 500) and diff against a reference tif. Candidate remaining *modeling* differences to check if params match: grid alignment/extent, EB optimiser (`scipy.minimize_scalar` vs R `optimize`), and normalisation. Candidate *parameter* difference: the auto-FMV-at-coarse-fix-rate rule above.

**Files touched.** `app/modules/modeling.py` (`_estimate_brownian_motion_variance` data term; `calc_kernel_ud` subsample drop; `get_model_config` Kernel `subsample` default), `INFORMATION.md` (this entry).

### 2026-06-09 — Tab 4 "Load Previous Population Outputs" button + raster-overlay opacity fix

- **Tab 4: Load Previous Population Outputs.** New button (`btn-load-pop-outputs`) under "Generate Population Outputs", mirroring Tab 3's load. Callback `load_previous_pop_outputs` reads the saved `popUseMerged/Pop_use_contours.shp` + `footPrintsMerged/Footprint_contours.shp` from the working directory (via the existing `_load_pop_outputs_from_disk`) into `store-pop-outputs`, and builds the contour-by-area preview from the stored GeoJSON (new `_pop_preview_from_store` helper). So Tab 5 can draw the population/footprint contours and Tab 4 shows the area table without re-running the population merge. (Difference from Tab 3's load: Tab 3 also rebuilds `_MODEL_CACHE` from the UD/footprint tifs so you can *regenerate*; this Tab-4 button only loads the already-merged contours for viewing.) Outputs are `allow_duplicate=True` (generate_pop_outputs holds the primaries).
- **Raster-overlay opacity fix.** User reported opacity=1 wasn't fully opaque. Cause: `_raster_to_overlay` baked a probability-scaled per-pixel **alpha ramp** into the PNG (UD: `alpha = 70 + 185·norm`, so only the single hottest cell hit 255; footprint masks: 200), so visible transparency was `ImageOverlay.opacity × pixel_alpha/255` — never fully opaque except at the peak cell. Fix: valid (in-corridor, value>0) cells are now **alpha 255**; no-data cells stay 0 (transparent, basemap shows through). The opacity slider is now the single linear control (opacity=1 = 100% opaque); the low→high gradient is conveyed by **colour** (viridis/grayscale), not baked-in alpha. Verified: all valid pixels decode to alpha 255.

**Files touched.** `app/main.py` (`_pop_preview_from_store`, `load_previous_pop_outputs`, Tab-4 button; `_raster_to_overlay` alpha), `INFORMATION.md` (this entry).

### 2026-06-09 — Tab 5: view output GeoTIFFs as map raster overlays (UD / footprint / banded), with a colour-scale option

- **Why.** The user wanted to view the model output `.tif`s (per-sequence UDs, footprints, and the banded population rasters in `BBMM_Output/`) directly on the Tab-5 map — the continuous surface under the vector contours. Confirmed feasible and cheap as long as **one raster is shown at a time** (rendering hundreds of per-sequence UDs at once would be the only expensive path, and is deliberately avoided via a picker).
- **Approach.** Per selected tif: read it, **reproject to EPSG:4326** (`rasterio.warp.calculate_default_transform` + `reproject`, nearest), colour to an RGBA PNG, and feed a **`dl.ImageOverlay`** (dash-leaflet 1.1.3 has it) with the 4326 bounds + an opacity slider. The PNG is a base64 data-URI — no temp files. Single read+warp+encode = ms for typical grids; the opacity slider adjusts opacity without re-warping.
- **No image libs available** (no matplotlib / PIL / imageio; GDAL's PNG driver is CreateCopy-only), so PNG encoding is a tiny **dependency-free zlib encoder** (`_png_encode_rgba`, colour type 6 / RGBA) and the colour ramp is hand-rolled in numpy (`_ramp_rgb`).
- **Colour scale option (this request).** New **"Colour scale"** dropdown on the Raster Overlay card — **Viridis** (default) or **Black & white** (grayscale) — wired into `render_raster_overlay` and through to `_raster_to_overlay(tif_path, cmap)`. `_ramp_rgb(t, cmap)` returns a black→white ramp for `cmap="gray"`, else the viridis anchors. Float UDs get the continuous ramp (alpha rising with probability so the core reads stronger); integer footprint/mask rasters get a solid fill whose colour follows the scheme (white for grayscale, orange for viridis). Continuous vs mask is auto-detected by dtype. Changing the colour scale re-renders; the opacity-only path still skips the re-render.
- **UI (`app/main.py`).** New "Raster Overlay (.tif)" card in the Tab-5 left column: **Category** dropdown (`UDs` / `Footprints` / `BBMM_Output`), **File** dropdown (lists `*.tif` in that `ModelOutputs/<category>/` folder; refreshes on category change, Tab-5 open, and after a model run/load), **Colour scale** dropdown, **Opacity** slider, **Clear overlay** button, and an info line (value range + pixel size). The `dl.ImageOverlay(id="raster-overlay")` was added to the map's children.
- **Callbacks (`app/main.py`).** `populate_raster_overlay_files` (category → file options, globbing the folder) and `render_raster_overlay` (file/opacity/cmap/clear → `raster-overlay` url/bounds/opacity + info). UD float rasters normalise to the 98th percentile of positive values so a single hot cell doesn't wash out the ramp.
- **Verification.** App imports/registers clean; round-trip tested on synthetic tifs — UD → valid RGBA PNG reprojected to correct CO lat/lon bounds; footprint → solid mask PNG; empty raster → graceful `None`; viridis vs grayscale produce distinct ramps (mid = teal vs mid-grey). **Not yet checked in-app:** the ImageOverlay actually drawing on the Leaflet map and the dropdowns populating from the real working directory.

**Files touched.** `app/main.py` (`_VIRIDIS_STOPS`, `_ramp_rgb`, `_png_encode_rgba`, `_raster_to_overlay`; Tab-5 "Raster Overlay" card + colour-scale dropdown; `raster-overlay` ImageOverlay on the map; `populate_raster_overlay_files`, `render_raster_overlay` callbacks), `INFORMATION.md` (this entry).

### 2026-06-09 — Tab 5 contours rendering fixed + Tab 3 "Load Previous Results" (skip re-running models)

Two related modeling-output features.

**Overwrite vs append (answered for the record).** Running a model **overwrites per-sequence files**: each sequence writes `ModelOutputs/UDs/<SeqName>.tif` and `ModelOutputs/Footprints/<SeqName>.tif` in rasterio `"w"` mode (truncate), and `model_results.csv`, `popUseMerged/Pop_use_contours.shp`, `footPrintsMerged/Footprint_contours.shp` are fixed-name and replaced. Nothing is timestamped/versioned. **Caveat:** the folders are not cleared first, so a later run with *different/fewer* sequence names leaves stale tifs behind — which "Load Previous Results" would also pick up. (Errored sequences write no tif, so every tif on disk = a successful sequence.)

**1. Tab 5 (Map & Export): population/footprint contours now render.**
- **Root cause.** The `map-geojson-contours` dl.GeoJSON layer was in the layout but **no callback ever fed it** — `update_map_layers` only outputs points + tracks. So ticking "Population Use Contours" / "Footprint Contours" did nothing (silent blank).
- **What changed (`app/main.py`).** New **`update_map_contours`** callback: `Output("map-geojson-contours","data")`, `Input("map-layers","value")` + `Input("store-pop-outputs","data")`. It reads `store-pop-outputs` (shape `{"use", "footprint", "config"}`, already EPSG:4326), and — based on which toggles are on (`pop_contours` → population use, `footprints` → footprint overlap) — merges the selected layers into one FeatureCollection, tagging each feature with a per-layer `_color`.
- **Styling.** New **`contourStyle`** fn in `app/assets/map_functions.js` (`dashExtensions.default.contourStyle`) colours by `feature.properties._color` (pop use `#E63946`, footprint `#457B9D`) and scales fill opacity by contour % so the core reads darker. Wired via the new module-level `_contour_style = {"variable": "dashExtensions.default.contourStyle"}` on the contours layer's `style` prop (mirrors how `_seq_point_style` is used for points).
- So after Generate Population Outputs **or** Load Previous Results sets `store-pop-outputs`, the Tab-5 toggles draw the contours. (Layers are off by default — `map-layers` defaults to `["raw_points","tracks"]`.)

**2. Tab 3 (Modeling): "Load Previous Results" — reuse a prior run without re-modelling.**
- **Why.** `_MODEL_CACHE` (pop_grid + per-sequence `{ud_raster, footprint_polygon, metadata}`) lives in **process memory only** and is lost on app restart; Tab 4's Generate Population Outputs reads it, so after a restart the user had to re-run everything. The UD/footprint GeoTIFFs are already on disk — this loads them back.
- **`load_model_outputs_from_disk(ud_dir, footprint_dir, metadata_csv)`** (new, `app/modules/modeling.py`): reads every `<seq>.tif` in `UDs/` as that sequence's UD raster, derives the population grid (transform/shape/CRS/cell_size) from the first raster, polygonises the matching `Footprints/<seq>.tif` mask via `_polygon_from_uint8_mask`, and pulls display fields from `model_results.csv` when present. Returns `(pop_grid, results, utm_crs, method)` — the same `results` shape `run_all_sequences` produces — or `None` if no UD tifs. Round-trip tested: UD sum preserved (=1.0), footprints polygonised, grid rebuilt.
- **UI + callback (`app/main.py`).** New **"Load Previous Results"** button (`btn-load-model-results`) under "Run Models". Callback **`load_previous_model_results`**: rebuilds `_MODEL_CACHE`, renders the Tab-3 results table (via the extracted `_model_results_table_from_results` helper, shared shape with a fresh run), and **also loads any saved population contours** — `_load_pop_outputs_from_disk` reads `popUseMerged/Pop_use_contours.shp` + `footPrintsMerged/Footprint_contours.shp` back into the `store-pop-outputs` JSON (EPSG:4326). Outputs are all `allow_duplicate=True` (run_modeling / generate_pop_outputs hold the primaries).
- **Flow:** Tab 3 → Load Previous Results → Tab 4's "Seasons to Merge" repopulates (`refresh_pop_seasons_checklist` keys off `_MODEL_CACHE`), regenerate population outputs (or they're already loaded), and Tab 5 draws everything — no model re-run.

**Verification.** App imports/registers clean (no duplicate-output/circular errors); loader round-trip tested on synthetic tifs. **Not yet checked in-app:** (a) the contour polygons actually drawing on the Tab-5 Leaflet map (the JS `style` fn resolving in this dash-leaflet version), and (b) Load Previous Results against the real working directory (the user's workdir is on another drive — no `ModelOutputs/` present in the repo tree to test against here).

**Still open / noted:** `_MODEL_CACHE` remains in-process (Load Previous Results is the restart-recovery path, not auto-persistence); folders aren't cleared before a run, so stale tifs from a prior differently-named run can accumulate (candidate: clear or version per run).

**Files touched.** `app/modules/modeling.py` (`load_model_outputs_from_disk`), `app/main.py` (`_contour_style`; contours layer `style`; `update_map_contours`; Tab-3 "Load Previous Results" button; `_model_results_table_from_results`, `_load_pop_outputs_from_disk`, `load_previous_model_results`; `load_model_outputs_from_disk` added to both modeling import blocks), `app/assets/map_functions.js` (`contourStyle`), `INFORMATION.md` (this entry).

### 2026-06-09 — Population outputs: smoothing now ports R's ksmooth (outline smoothing, not grid blur)

- **Why.** Goal: make population-output contours directly comparable to Migration Mapper. R (`CalcPopUse.R:341`, `CalcPopFootprint.R:206`) smooths the **polygon outlines after contouring** with `smoothr::smooth(method="ksmooth", smoothness=ksmooth_smoothness)` (default 2) — this de-pixelates the staircase edges while preserving each contour's area and position. Our app was instead **blurring the proportion grid** with `scipy.ndimage.gaussian_filter(sigma=1.5 cells)` *before* contouring, which moves the contour lines and changes their areas — not comparable. (The UI field was even mislabeled "Bandwidth (σ)".)
- **What changed (`app/modules/population_outputs.py`).**
  - New **`_smooth_ksmooth(geom, smoothness)`** — a port of `smoothr`'s ksmooth. Each ring is densified, parameterised by cumulative arc length (circular, since rings are closed), and every vertex becomes the Gaussian-weighted average of its neighbours along the boundary. Bandwidth = `smoothness * mean(segment length)`; kernel sd scaled like R's `stats::ksmooth` normal kernel (`sd = 0.3706506 × bandwidth`). Uses a bounded windowed sweep (not an M×M matrix) for speed/memory; guards tiny/degenerate rings and falls back via `buffer(0)` on invalid output. Handles Polygon + MultiPolygon, smoothing exterior and hole rings.
  - **`_contours_from_grid`** no longer blurs the grid. It now contours the raw grid → drop crumbs (`min_area_drop`) → fill holes (`min_area_fill`) → (when `simplify`) smooth outlines via `_smooth_ksmooth`. This matches R's order. The param was renamed `smooth_bandwidth` → `smoothness` locally (callers pass positionally, so no call-site churn). Both Population Use and Population Footprint route through this one function.
  - Removed the now-dead `gaussian_filter` import.
- **UI (`app/main.py`).** Field relabeled **"Smoothness (ksmooth)"**, default **1.5 → 2** to match R's `ksmooth_smoothness`, with help text clarifying it smooths outlines (areas preserved), not the surface. The config still carries the value under the legacy key `smooth_bandwidth` (documented) to avoid churn across the population-function call sites; the metadata CSV likewise still labels it `smooth_bandwidth` (a candidate rename to `ksmooth_smoothness` for exact R parity was left open).
- **Verification.** On a deliberately sharp plus-shaped test contour: raw 58.0 km² (21 staircase vertices) → ksmoothed 54.8 km² (161 vertices, valid polygon), a ~5.5% area change from corner-rounding; smoother real corridors change less. Modules + full app import clean. (Not yet checked in-app on real outputs.)
- **Still-open parity items (not smoothing):** remaining differences vs R will come from the contour-extraction details (Area vs Volume cumulative logic) and exact densification, to audit later.

**Files touched.** `app/modules/population_outputs.py` (`_smooth_ksmooth`, `_contours_from_grid`, docstrings, import), `app/main.py` (pop-output smoothing label/default/help + config key comment), `INFORMATION.md` (this entry).

### 2026-06-09 — Tab 3 modeling: BBMM time-lag units bug fixed + model parameters now actually applied

Focused pass on getting the **Brownian Bridge (BBMM)** model working, driven by the WMI reference (`MAPP3.x_code_workflow/code2run.R` + `functions/CalcBBMM.R`). Our `calc_bbmm` was already a faithful port (FMV custom bridge + EB Horne-2007 MLE, the >1/3-max-lag bail, <4-point bail, 99.99% tail cut, contour footprint), but two things were broken.

- **(1) Time-lag units bug — the big correctness fix (`app/modules/modeling.py`).** `calc_bbmm` computed step durations with `work[date_col].astype("int64")` assuming **nanoseconds**, but pandas 2.x can store datetimes at **microsecond** resolution, so the lags came out **1000× too small** (a 4-hour gap read as 0.24 min). That collapsed the `lag·α(1-α)·BMvar` term so the bridge was **dominated by location error and effectively ignored BMvar** — symptom: BMvar values of 50, 4000, and 195600 all produced byte-identical, over-tight UDs. This very likely explains the long-standing "BBMM differs from the canonical reference" divergence noted in earlier entries. **Fix:** compute lags resolution-independently via `(work[date_col] - work[date_col].iloc[0]).dt.total_seconds()`. After the fix the EB estimate corrected from a bogus **195600 → 195.6** (exactly the 1000×), and FMV now widens the UD monotonically with BMvar (50→7 km², 2000→44 km², 20000→148 km²) as it should.
- **(2) Model-panel parameters were collected but never used (`app/main.py`).** `run_modeling` built its config purely from `get_model_config()` defaults — it never read the `bbmm-*` inputs, so changing BMVar / Location Error / Max Lag / Time Step / Contour did nothing. Added **`_apply_model_ui_params(config, model, params)`** which overrides the defaults from the panel values (blank BMVar correctly keeps the auto/estimated value = R's `BMVar=NULL`; only non-blank values override).
- **(3) Pattern-matching ids for the param panel.** First wiring used plain `State("kernel-bw", …)` etc. — but only the selected model's inputs exist in the layout at any time, and a string `State` on an absent id raises *"A nonexistent object was used in a State"* (suppress_callback_exceptions doesn't cover this). **Fix:** every model-param input now uses a pattern-matching id `{"type": "model-param", "key": "<name>"}`, and `run_modeling` reads them with `State({"type":"model-param","key": ALL}, "value")` + `… "id")`, zipping them into a `{key: value}` dict. `ALL` matches only the inputs currently present, so it never errors regardless of selected model.
- **(4) Added the missing BBMM `mult4buff` parameter** to the panel (R default 0.3 — the per-sequence subgrid buffer), reordered the BBMM panel to match the R argument order, and clarified the BMVar/FMV help text.
- **(5) Minor:** `get_model_config` would have raised for `Kernel`/`LineBuffer` (valid dropdown values missing from its validation set) — added `KERNEL`/`LINEBUFFER`.
- **Verification.** App imports/registers clean; param overrides apply (forced FMV, loc error, contour, mult4buff) while blank BMVar stays auto; BBMM runs in both EB and FMV modes producing normalised UDs (sum≈1) + footprints. User confirmed a real BBMM run completes; a UD `.tif` spot-check is still pending.
- **Parameter status vs `CalcBBMM`:** exposed & wired — BMVar, location.error, max.lag, time.step, contour, mult4buff. Not exposed — `max.timeout` (Python has no per-sequence timeout yet; would be misleading to expose). `cell.size` (500 m) is hardcoded in the pop-grid build (R sets it in `CalcPopGrid`) — candidate to surface later.

**Files touched.** `app/modules/modeling.py` (`calc_bbmm` time-lag computation), `app/modules/modeling.py`→`get_model_config` (valid-method set), `app/main.py` (`render_model_params` panel ids + `mult4buff`; `_num_or_none`/`_apply_model_ui_params`; `run_modeling` States + signature + override call), `INFORMATION.md` (this entry).

### 2026-06-09 — Tab 1: import an externally-created migtime CSV (WMI format)

- **Why.** Users who already defined/reviewed migration sequences elsewhere — chiefly the WMI Migration Mapper, whose export looks like `migtimeExport_*.csv` — should be able to load that table instead of re-detecting from scratch. The example file used to build this: `C:\Users\shadwelk\Documents\MigrationFiles\migtimeExport_20260304164654.57955.csv`.
- **The WMI format.** One row per animal-year. Columns: `id_bioYear`, `newUid` (the animal id), `bioYear` (2-digit), `bioYearFull` (4-digit), `tempStartMonth`/`tempStartDay` (bio-year start), `mig1start`/`mig1end` … `mig8start`/`mig8end` (note: no underscore), `notes`. Missing dates are the literal `NA`. Slot positions are meaningful and preserved (e.g. spring in `mig1`, fall in `mig3`).
- **UI.** New **"Import Migtime CSV (optional)"** card at the bottom of the Tab-1 left column: a `.csv` drag/drop (`upload-migtime`), an **Animal-ID column** dropdown (auto-populated from the file's headers, pre-guesses `newUid`/uid-like columns), **bio-year start** month/day inputs (auto-filled from `tempStartMonth`/`tempStartDay` when present), and an **Import Migtime** button. Status line reports the result.
- **Two callbacks.** `handle_migtime_upload` decodes the file (utf-8-sig to drop any Excel BOM), stashes the raw text in `store-migtime-import-raw`, and pre-fills the controls via `_sniff_migtime_columns`. `import_migtime` maps the file onto our internal migtime schema, writes `store-migtime-table` (so Tab 2 + modeling consume it), syncs `seq-bio-year-month`/`-day` to the chosen start, and merges the file's `notes` column into `store-animal-notes` (keyed by the reconstructed `id_bio_year`).
- **Schema mapping** (`_parse_external_migtime`): `newUid` → `animal_id`, `bioYearFull` → `bio_year`/`bio_year_full`, `mig{n}start`/`mig{n}end` → `mig{n}_start`/`mig{n}_end` (`NA` → blank, dates normalised to `YYYY-MM-DD`), `notes` → `notes`, plus `auto_detected=False`, `reviewed=True`. Header matching is fuzzy via `_norm_hdr` (lower-case, alphanumerics only) so `mig1start` / `mig1_start` / `Mig1 Start` all resolve.
- **The key-matching gotcha (this was the actual blocker).** First cut reconstructed `id_bio_year = animal_id + '_' + bioYearFull` and assumed the animal name matched. It didn't: the loaded GPS data stores `animal_id` with **underscores** (`E18_SP_14_2022_010823`) while the WMI file's `newUid` uses **hyphens** (`E18-SP-14-2022-010823`) — so the join silently produced zero matches and Tab 2 showed nothing. The year format was a red herring (both are effectively 4-digit once `bioYearFull` is used). **Fix:** `_norm_animal` collapses any run of non-alphanumeric characters to a single underscore, and `import_migtime` reads the unique `animal_id`s out of the loaded GPS data (`store-processed-data`) and **snaps** each file id onto the real one before building the key. The status message reports the match rate ("All 112 animal ids matched your GPS data") and warns loudly when 0 match (wrong Animal-ID column) or when no GPS data is loaded yet. Validated on the example: 112/112 animals snapped, 496/501 reconstructed keys present in the processed `id_bio_year` set (the 5 misses are animal-years absent from that GPS extract).
- **Deliberately NOT done:** the user initially asked to switch the whole app's key to a 2-digit suffix (`animal_23`) thinking the year format was the cause. Since the real cause was the hyphen/underscore separator — and a global 2-digit change would touch processing, Tab 2, modeling, and output filenames for no benefit here — the normalisation/snap approach was used instead. A 2-digit *display* convention remains open as a separate, optional change if wanted later.
- **Caveat for users.** Imported sequences only resolve in Tab 2 / modeling when the loaded GPS data uses the same animals and the same bio-year start; the importer sets the bio-year start and surfaces the match rate so a mismatch is obvious. (Still to be exercised against a second, different dataset.)

**Files touched.** `app/main.py` (`_norm_hdr`, `_norm_animal`, `_sniff_migtime_columns`, `_parse_external_migtime`; `store-migtime-import-raw` store; Tab-1 "Import Migtime CSV" card; `handle_migtime_upload` + `import_migtime` callbacks), `INFORMATION.md` (this entry).

### 2026-06-09 — Tab 2 map: colored (in-migration) points drawn on top of black points

- **Why.** When a migration window is selected and the user zooms out, dense black (unassigned) fixes were drawing over the colored in-migration fixes, so the selection was hard to see — the black dots "overpowered" the colored ones.
- **What changed.** Added a `circle-sort-key` to the `animal-points-layer` in `app/assets/maplibre_map.html`. Within a single MapLibre circle layer, features with a higher `circle-sort-key` are drawn later (on top). Unassigned points carry `c == '#000000'` (the default from `_build_point_geojson`); points inside a migration window carry a palette colour. The expression `['case', ['==', ['coalesce', ['get','c'], '#000'], '#000000'], 0, 1]` gives black points key 0 and every coloured point key 1, so the colour always renders above the black field regardless of source order.
- **Side benefit.** Where a coloured and a black dot overlap, `queryRenderedFeatures` now returns the coloured one first, so clicks land on the in-migration point.
- **Scope.** Draw order *within* the points layer only; the selection-halo and flash-halo layers are separate layers stacked above the points, so they're unaffected. The white slot-8 palette colour (`#FFFFFF`) is treated as "coloured" (key 1), which is correct — only the literal unassigned `#000000` sinks to the bottom.

**Files touched.** `app/assets/maplibre_map.html` (`animal-points-layer` `layout.circle-sort-key`), `INFORMATION.md` (this entry).

### 2026-06-09 — Tab 2: resizable map panel (widens the NSD plot) + Notes auto-save

Two Tab-2 review-ergonomics changes, both in `app/main.py`.

**1. The map panel is now user-resizable in both dimensions, and shrinking it widens the NSD plot.**

- **Why.** The NSD chart was sometimes too small for a thorough visual read. The map and NSD live in side-by-side columns, so the user wanted to shrink the map to give the NSD plot more room — in both height and width.
- **What changed.**
  - The map's iframe wrapper went from `resize: vertical` to **`resize: both`** (one grip at its bottom-right corner changes width *and* height). Width is bounded `300px–75vw`, height keeps its prior range. `paddingBottom: 10px` leaves a thin iframe-free strip so the native resize grip isn't swallowed by the iframe's own mouse capture. MapLibre GL (4.7.1) re-fits via its container `ResizeObserver`, and the NSD `dcc.Graph` (responsive) redraws as its container grows.
  - **Column layout reworked so the map's width actually feeds the NSD plot.** The middle (NSD/charts) column became flex-grow (`width=True`, `minWidth:0`); the right (map) column became content-sized (`width="auto"` → Bootstrap `col-auto`, `flex:0 0 auto`). The map wrapper is the width *driver*: narrowing it shrinks the whole right column, and the freed horizontal space flows into the NSD column.
  - **Why the first attempt didn't work.** The initial pass put `resize: horizontal` on the *column* (whose grip sits at the very bottom of the column, under the Flag box) while the user was dragging the *map's* corner — which only had vertical resize. Moving `resize: both` onto the map wrapper put the control where the user actually drags.
  - **The long-text "width floor" trap.** A content-sized (`col-auto`) column is as wide as its widest child's *max-content*, which for a card of text is the longest unwrapped line — that would stop the map from shrinking. Fixed with the `width: 0; min-width: 100%` trick on the Notes and Flag cards (and the resize-hint caption): they fill the column's width but contribute 0 to its intrinsic width, so the map stays the sole width driver. The map's CardHeader text was trimmed to "Animal Locations" for the same reason, with the resize hint moved to a neutralised caption directly under the map.

**2. Notes now auto-save; the "Save Notes" button is gone.**

- **Why.** Previously notes were only persisted when the user clicked **Save Notes** — typing a note and then switching animals or reloading lost it (navigating reloads the box from the store). The user wanted automatic per-animal-year saving without a button, but without a per-keystroke server round-trip.
- **What changed.**
  - The Notes textarea got **`debounce=800`**: Dash sends the value ~0.8 s after the user stops typing, and flushes immediately on blur / animal navigation — at most one small write per pause, no per-keystroke lag.
  - New **`autosave_animal_notes`** callback (replaces the old `save_animal_notes` button handler) keys the text by the selected animal-year, updates `store-animal-notes`, and writes `animal_notes.json`. Because a textarea's blur fires *before* the click that navigates away, `State("seq-animal-dropdown")` still holds the OLD animal at commit time, so type-then-navigate lands the edit on the right row. A no-op guard (`notes_store.get(key) == new_val → PreventUpdate`) skips the redundant write that the programmatic reload on animal-switch would otherwise cause, so disk is only touched on real changes. Surfaces a small green "✓ Saved".
  - **Removed** the `btn-save-notes` button (and its empty label spacer); the `notes-save-status` div remains to show the auto-save indicator. `autosave_animal_notes` is now the primary writer of `store-animal-notes` / `notes-save-status` (no `allow_duplicate`); `apply_classification`, the unclassify callback, and project-load keep their `allow_duplicate=True` outputs.
  - **Residual edge:** an edit made and then the tab closed within the ~0.8 s debounce (without clicking away first) could still be missed — same exposure as the old button, just far smaller. Export and downstream still read the live `store-animal-notes`, and the store is `storage_type="local"` so it also survives same-browser reloads.

**Files touched.** `app/main.py` (Tab-2 middle/right columns + map wrapper styles; Notes textarea `debounce`; `save_animal_notes` → `autosave_animal_notes`; removed `btn-save-notes`), `INFORMATION.md` (this entry).

### 2026-06-09 — Tab 2: auto-detect point colours, clearing the NSD chart, and sequence-name propagation

Fixed three related Tab 2 (sequence-setting) bugs. The root of the first two turned out to be the server-side dataframe-cache token, and fixing it correctly forced a clean re-architecture of the big `update_nsd_plots` callback.

**Why (the three reported problems).**

1. **Auto-detected sequences left every map point black.** Manual slider edits coloured points, but clicking Auto-detect All did not.
2. **Cleared sequences wouldn't leave the NSD chart.** After Clear Sequences (or a per-slot Clear sequence) the shaded migration bands stayed on the NSD plot.
3. **Renaming a sequence (mig1 → Spring) didn't follow through.** The new label didn't appear on the NSD bands, the slider-card headers, or the exported migtime table.

**Root cause of #1 and #2 — the migtime store token never changed.** DataFrames live in a server-side `_DF_CACHE`; the `dcc.Store` only carries a tiny token `{"__cache_key","rows","cols"}` (see `_df_to_json`/`_json_to_df`). Auto-detect and Clear edit the migtime *values* without changing the table's row/col shape, so the token string was byte-identical between writes — Dash saw "no change" on `store-migtime-table` and never re-fired the consumers. So `update_seq_map` never repainted the points (stayed black) and nothing re-rendered the chart (bands lingered). Manual editing only *appeared* to work because navigating animals re-fired the map via the dropdown Input.

**What changed.**

- **`_df_to_json` now stamps a monotonic `rev` nonce for `cache_key == "migtime"`** (module-level `_DF_TOKEN_REV`). Every migtime write yields a distinct token, so the `store-migtime-table` Input reliably fires its consumers (map recolour + chart re-render). Other caches (e.g. `"processed"`) are unaffected — they're written rarely and read mostly via `State`.
- **Split the monolithic `update_nsd_plots` into a writer + a renderer.** `update_nsd_plots` both *read* and *wrote* `store-migtime-table`, so it could not take that store as its own Input (Dash circular dependency). The split removes that constraint:
  - **`build_migtime_store`** (writer, `Output store-migtime-table`): builds the empty scaffold on first load and, on Auto-detect All, runs the full-DF NSD detection + `apply_auto_detections`. Triggered by animal dropdown, Auto-detect All, and num-sequences. Leaves the table alone on plain navigation/num change (the scaffold always carries all 8 mig slots, so a count change needs no rebuild — and crucially does **not** wipe user edits).
  - **`render_seq_panels`** (renderer, `Input store-migtime-table`, no migtime Output): rebuilds the four plots, the NSD bands, and the slider cards **strictly from the migtime row for the selected animal** — the single source of truth. It runs **no auto-detection**. This is what makes clearing stick: Clear Sequences / per-slot clear blanks the row → the store changes (new rev) → this re-fires → no windows found → no bands drawn.
- **Behaviour change worth noting:** the chart no longer shows per-animal auto-detection *suggestions* on plain navigation before Auto-detect All has been run. Bands now reflect only what's actually in the migtime table, which is what keeps the map and chart consistent and lets clears truly clear. One Auto-detect All click still populates every animal-year at once (the WMI review-then-edit workflow).
- **Sequence-name propagation via a new `store-seq-names`.**
  - New `dcc.Store(id="store-seq-names")` + `sync_seq_names` callback mirror the Sequence Names inputs (now `debounce=True`, so a rename commits on blur, not mid-keystroke) into one authoritative ordered list.
  - `render_seq_panels` labels the NSD bands and slider-card headers from it. **Component ids still use the stable slot key `mig{n}`** (so `slider_to_migtime` / `clear_single_sequence` / `slider_to_dates`, which parse the slot number out of the id, keep working) — only the *displayed* `html.Strong` text uses the friendly label.
  - `render_seq_name_inputs` now seeds each box from `store-seq-names` (and takes it as an Input) so labels restored on load reappear in the boxes; `sync_seq_names` mirrors them straight back unchanged, so it converges in one extra render rather than looping (debounce keeps the round-trip off the typing path).
  - Modeling (`run_modeling`) already consumed the name inputs for `seq_labels`, so the labels carry through `extract_sequences` and the downstream analysis unchanged.
- **Migtime export naming (user chose "rename + keep a mig map").** New helper `_friendly_migtime_for_export` renames the per-slot date columns to the user labels (`mig1_start` → `Spring_start`, …) for the human-facing CSV and adds a `seq_map` legend column (`"mig1=Spring;mig2=Summer;…"`). Applied in both `export_migtime` and `overwrite_migtime`. `load_previous_migtime` reads `seq_map` to rename the friendly columns back to the canonical `mig{n}_start/_end` schema the pipeline relies on (lossless round-trip) and restores the labels into `store-seq-names` (so a reload re-populates the name boxes + relabels the chart). Slots left at the default `mig{n}` are neither renamed nor added to the legend.
- **Shared palette.** Extracted the 8-colour sequence palette to a module-level `SEQ_COLORS`; the NSD bands, slider cards, and the map points (`_build_point_geojson`) now all index into the same list, so a sequence's colour can never drift between the chart and the map.

**Verification.** `main.py` byte-compiles and the full module imports cleanly (all callbacks register with no circular-dependency or duplicate-output errors). Not yet exercised in the live UI — suggested manual pass: pick an animal → Auto-detect All (points colour) → rename Seq 1 to "Spring" (band + card header update) → Clear Sequences (bands + colours drop) → Export Updated Table, then Load Previous Table (names round-trip).

**Files touched.** `app/main.py` (`_df_to_json` rev nonce; `SEQ_COLORS`; `_seq_working_df` helper; split into `build_migtime_store` + `render_seq_panels`; `store-seq-names` store + `sync_seq_names`; `render_seq_name_inputs` seeding + debounce; `_friendly_migtime_for_export`; `export_migtime` / `overwrite_migtime` / `load_previous_migtime`; `_build_point_geojson` palette; layout/docstring comment updates), `INFORMATION.md` (this entry).

**Doc consolidation (same day).** Reviewed the old terser `INFORMATION.md` against this file and migrated the few facts it carried that weren't already here — the git repo-root-scope rationale (into the 2026-05-16 git entry), the per-function R-source mappings for `sequencing.py` / `modeling.py` / `population_outputs.py` (the "R lineage" lines added to §7.2/§7.3/§7.4), the migtime "was a SQLite table; the boolean flags are Python additions" note (§8.3), and the "language portability of the processing core" future-dev bullet (§12). With nothing left only in `INFORMATION.md`, that file was deleted so this is the single reference.

### 2026-06-08 — Tab 2: Resident / Nomadic / Migratory classification (flag, don't delete)

Added a movement **Classification** control to the Tab 2 Notes card (`app/main.py`): a 3-option `dbc.RadioItems` (`id="animal-classification"`) — **Resident / Nomadic / Migratory**, single-select — plus an **Unclassify** button (`id="btn-unclassify"`). Used to mark animal-*years* that have no identifiable routine migration.

- **Auto-populated Notes.** Picking an option fills the Notes textarea (`apply_classification` callback) with a canonical sentence + the existing road/highway crossing phrase (`_crossing_phrase`):
  - Resident → `Resident. No migration identified.`
  - Nomadic → `Non-migratory, nomadic. Lots of movements but no migration identified.`
  - Migratory → `Migration identified.`
  - …each followed by `Crosses highway.` / `Crosses road.` when applicable.
- **Persistence.** New `dcc.Store(id="store-animal-classification")` (local-storage) + `animal_classifications.json` on disk (helpers `_load_classifications` / `_save_classifications`), keyed by `id_bio_year`, mirroring how `animal_notes.json` works. The generated note is also written to the notes store/disk so it flows into the exported migtime `notes` column. `update_seq_map` reflects the stored value into the radio on animal navigation; `apply_classification` guards against that programmatic round-trip (`if classification == class_store.get(animal_key): PreventUpdate`) so navigating animals never clobbers free-text notes.
- **Unclassify.** Clears the stored classification, resets the radio to `None`, and wipes the auto-generated note for that animal-year.
- **Export behavior (flag, not delete).** On **Export Updated Table** (`export_migtime`), Resident/Nomadic animal-years are kept out of the analysis but **not removed from the dataset**:
  - Their rows are dropped from the *exported* migtime CSV (so `extract_sequences` builds no migration sequences for them → excluded from modeling).
  - Their fixes stay in the processed data, tagged in-place via a new `classification` column (no row deletion).
  - They're archived to `ModelOutputs/ResidentsNomadsRemoved.{csv,shp}` (with a `classification` column), alongside `FlagsRemoved.gpkg`.
  - Migratory and unclassified animal-years are untouched.

Rationale for flag-not-delete (user request 2026-06-08): keep a reversible record and avoid mutating the source dataset; analysis exclusion is achieved through the migtime/sequence path, which is what actually drives the UD/BBMM modeling. `_REMOVED_CLASSIFICATIONS = ("resident", "nomadic")` is the single source of truth for which classes are excluded.

### 2026-06-08 — Tab 2: NSD double-click toggle now reads bio range from `layout.meta`

The double-click bio-year ↔ data-extent toggle (`app/assets/map_functions.js`) was failing to zoom back out for some animals. Cause: it cached the bio-year window with a heuristic in `tick()` that re-cached any visible range spanning ~365 days; Plotly's autorange padding made a zoomed-in data extent (for animals whose data spans ~330–350 days) look ~1 year wide, poisoning the cache so the second double-click thought it was already at the bio window. Fix: `update_nsd_plots` now stamps the exact bio range onto each figure as `layout.meta.bioRange`; the JS reads that authoritative value (`getBio`) and the heuristic re-cache loop was removed. (User reported still not working in practice — left in as the cleaner implementation; revisit if the toggle is needed.)

### 2026-06-06 — Tab 2 charts: drag = pan (grab hand), not box-zoom

**Why.** Plotly's default `dragmode` is `'zoom'` — drag draws a selection rectangle and zooms into it. The user wanted to drag-pan the timeline left/right (the natural "grab and slide the chart" mental model) and still use the scroll wheel to zoom.

**What changed.** Added `dragmode="pan"` to all four chart `update_layout` calls (NSD, Displacement, Speed, Elevation) in `update_nsd_plots`. Cursor becomes a grabbing hand on hover, drag pans the x-axis. `scrollZoom: True` on the NSD plot config still handles wheel-zoom. Other three charts keep wheel disabled (we set scrollZoom only on NSD because they're short enough to read at default zoom).

**Files touched.** `app/main.py` (four `update_layout` calls), `INFORMATION.md` (this entry).

### 2026-06-06 — Double-click toggle v3: actually find the Plotly graph div

**Why.** v2's toggle still wasn't snapping back to bio-year on the second double-click. Root cause: `document.getElementById('nsd-plot')` returns Dash's wrapper `<div>`, NOT the inner `.js-plotly-plot` element Plotly actually attaches its `.layout` and event API to. v2 then bailed out on `if (!el.layout)` and never wired the `plotly_doubleclick` listener — so Plotly's *default* double-click (autorange) was firing all along, and "snap back" never had a chance.

**What changed.** New `findGraphDiv(id)` helper. Looks up the wrapper by id, descends into `.js-plotly-plot` (or returns the wrapper itself in case Plotly is attached directly). Everything else stays the same: range-based toggle, span-heuristic re-cache.

**Files touched.** `app/assets/map_functions.js` (`findGraphDiv` + tick refactor), `INFORMATION.md` (this entry).

### 2026-06-06 — Double-click toggle v2: range-based, plus NSD y-axis clamp at 0

**Why.** The first pass tracked state in a JS variable; on real use it stuck in `'full'` after the first double-click because Dash re-renders didn't always update the title (the title-change heuristic for re-snapshotting). Also: NSD is squared displacement so it's mathematically non-negative, but Plotly's autorange happily pads below zero on zoom-out, which is misleading.

**What changed.**

- **Toggle now reads `gd.layout.xaxis.range` at click time** instead of tracking state in a JS variable. If the current range matches the cached `bioRange[chartId]` → autorange to data extent. Otherwise → snap back to bio range. Robust to any number of Dash re-renders between clicks; the cache is what survives, not a transient `'bio' | 'full'` flag.
- **Bio-range cache refresh heuristic**: replaced title-change detection with a span check. A Dash-set bio-year range is always 365–366 days end-to-end (we measure `(t1 - t0) / 86400000`); user zooms produce arbitrary spans. So the polling tick re-caches `bioRange[id]` whenever it sees a year-sized span that differs from the current cache. User-zoom spans never qualify, so the cache only updates on real Dash redraws.
- **NSD y-axis clamp**: added `yaxis={"rangemode": "nonnegative"}` to the NSD figure's `update_layout`. NSD is squared displacement (km²) and cannot be negative; rangemode='nonnegative' tells Plotly to keep the axis pinned at zero on the low end during autorange and during user pan/zoom-out. Other three charts (Displacement, Speed, Elevation) left alone — displacement can be near-zero but isn't conceptually bounded the same way; speed and elevation can take their normal autoranges.

**Files touched.** `app/assets/map_functions.js` (toggle IIFE rewritten), `app/main.py` (NSD `yaxis.rangemode`), `INFORMATION.md` (this entry).

### 2026-06-06 — Tab 2 charts: double-click toggles bio-year ↔ full data extent

**Why.** Plotly's default `doubleClick: 'reset+autosize'` only goes one direction once the chart is already at the data extent: subsequent double-clicks no-op. The user's mental model is a *toggle* — first double-click = zoom out to full data, second double-click = revert to the bio-year window. Same for all four time-series charts.

**What changed.** New IIFE near the top of `app/assets/map_functions.js`. Iterates `['nsd-plot', 'displacement-plot', 'speed-plot', 'elevation-plot']` on a 750 ms tick. For each chart not yet wired, attaches `plotly_doubleclick` listener that toggles per-chart `state` between `'bio'` and `'full'`, calling `Plotly.relayout(gd, ...)` with either the cached bio range or `xaxis.autorange: true`. Returns `false` to suppress Plotly's default reset.

**Detecting Dash re-renders without clobbering toggle state.** Bio-year range needs to be re-cached when Dash redraws the chart for a new animal-year (the range moves). Naive approach — comparing `el.layout.xaxis.range` to the cache each tick — would also fire right after the user toggled to "full", clobbering state. Fix: detect re-render by watching `layout.title.text` (the NSD plot's title is `NSD — <animal>` so it changes per render); when title changes, re-snapshot bio range and reset state to `'bio'`. User toggles don't change the title, so state survives.

**Files touched.** `app/assets/map_functions.js` (new IIFE), `INFORMATION.md` (this entry).

### 2026-06-06 — Click an NSD-chart point to flash the same fix on the map

**Why.** With per-fix markers now visible on the NSD plot, the user wanted to be able to ask "where on the ground was *that* point?" — click a marker on the chart, see it pulse on the map.

**What changed.**

- **`app/assets/maplibre_map.html`**: added a `flash-halo` GeoJSON source + `flash-halo-layer` circle layer drawn above the selection halos. Bright cyan (`#00E5FF`) 3.5 px stroke, transparent fill, 10–22 px radius interpolated by zoom. Also cached the latest points GeoJSON in a module-level `pointsData` variable on every `update-data` message, because MapLibre's `getSource(...)._data` is not a stable API and `querySourceFeatures` only returns viewport features (would miss off-screen flashes).
- **`flash-point` message handler in the iframe**: looks up the feature whose `properties.d` matches the timestamp the parent sent. Exact match first; if that misses (the map subsamples to \~3000 points on large herds via `step = max(1, n // 3000)`, so the click timestamp may not exist in the map's GeoJSON), falls back to the feature closest in time so the flash still lands near the right place. Sets the flash source to that single feature, pulses `circle-stroke-opacity` between 1.0 and 0.25 every 200 ms for 1.6 s, then clears the source. If the point is off-screen, eases the map to it (500 ms) so the pulse is actually visible.
- **`app/main.py` clientside callback on `nsd-plot.clickData`**: extracts `clickData.points[0].x` (the timestamp the marker represents in Plotly) and normalises it to `YYYY-MM-DD HH:MM:SS` UTC — matching the format `_build_animal_map_entry` writes into the GeoJSON `d` property. Posts `{type: 'flash-point', d: <stamp>}` into the iframe. Output uses `Output("nsd-plot", "clickData", allow_duplicate=True)` returning `no_update` — a pure side-effect callback (Dash needs *some* output but we don't actually want to change anything).
- **Why UTC-format normalisation matters**: Plotly returns `clickData.points[0].x` as an ISO-ish string that varies between browsers and Plotly versions; the map's `d` property is the exact strftime from pandas. Normalising both sides through `Date.parse → UTC strftime` makes the match deterministic.

**Files touched.** `app/assets/maplibre_map.html` (source, layer, handler, points cache), `app/main.py` (new clientside callback), `INFORMATION.md` (this entry).

### 2026-06-06 — Tab 2 charts: light-grey lines + per-fix markers on the NSD plot

**Why.** The four time-series charts (NSD, Displacement, Speed, Elevation) each used a distinct accent colour — blue, orange, teal, brown — competing with the per-sequence colours on the map and slider cards for the user's attention. Charts in this UI are reference material, not the focal point, so they should recede visually. Also: the NSD curve as a pure line hid the underlying fix density, making it hard to spot data gaps or unusual sampling cadence around a candidate migration window.

**What changed.**

- All four `go.Scatter` line traces (`update_nsd_plots` in `app/main.py`) now use `#cfcfcf` (light grey) instead of `#7ecfff` / `#f4a261` / `#a8dadc` / `#b08968`. Line widths kept at the existing 1–1.5 px range.
- NSD trace mode changed from `"lines"` to `"lines+markers"`. Markers are size 5 black fill with a 1 px light-grey stroke (`#cfcfcf`) — the grey ring is what makes them legible against the dark `plotly_dark` background; pure black or pure grey alone disappeared into either the chart background or the grey connecting line. The contrast also reads them as distinct "fixes" rather than as nodes on the line.
- Displacement / Speed / Elevation stayed lines-only — they sample at the same cadence as NSD, so duplicating markers there would just add noise.

**Files touched.** `app/main.py` (four `go.Scatter` traces in `update_nsd_plots`), `INFORMATION.md` (this entry).

### 2026-06-06 — Mortality flag cascades forward in time for the whole animal

**Why.** Mortality is terminal — once the animal is dead, every subsequent GPS fix is the collar transmitting from a carcass (or stationary on the ground). Asking the user to box-select every trailing fix is busywork and error-prone. The biological model is "flag the death moment; everything after is mortality."

**What changed.** In `_apply_flag_to_selection`'s `mortality` branch: take the earliest timestamp the user selected within the current animal, then expand the update mask to `(animal_id == this animal) & (timestamp >= earliest_death)`. That captures every fix for this animal from the death moment onward — across all bio years, since a mortality once in 2024 means every 2025 fix is also post-mortem. `problem` and `mortality_flag` are set on the cascaded mask, not just the selection. `n_matched` is updated to the cascaded count so the success banner reports the real number of fixes affected, and the verb string includes the death timestamp so the user can verify the cascade started at the point they intended.

**Why not cascade Unflag in the same way.** Asymmetric on purpose: walking back a mortality means deciding *where* the animal "came back to life," which is ambiguous (it didn't). If a user mis-flags a death and wants to undo, "Unflag Selected" on the originally-clicked point + a box select on the trailing run is correct; auto-cascading the unflag would silently un-mortality fixes the user might have intentionally flagged later for a different animal-death event. Revisit if a user reports it as a footgun.

**Files touched.** `app/main.py` (`_apply_flag_to_selection` mortality branch), `INFORMATION.md` (this entry).

### 2026-06-06 — Flag clicks are now in-memory only; disk save deferred to "Export Updated Table"

**Why.** User reported flagging a couple of points took noticeably long. Even after we restricted the map-cache rebuild to a single animal earlier, each flag click still did three synchronous disk operations: parquet write to the project session_data, parquet write to the workdir, and FlagsRemoved.gpkg write. On large herds the FlagsRemoved write dominates because it serialises the entire processed DataFrame (every animal × every column × every fix) through pyogrio. The user's mental model is right: flagging is a per-animal edit, persistence should be batched and triggered explicitly.

**What changed.**

- **`_apply_flag_to_selection` (`app/main.py`)**: stripped the disk-save block entirely. The function now updates `store-processed-data` and the single-animal `_MAP_CACHE` entry in memory, logs `USER_FLAG` with `persisted=False`, and returns. Every downstream Tab 2 callback reads from `store-processed-data`, so the UI shows the new flag state immediately — what's gone is the disk round-trip, not the user-visible update.
- **`export_migtime` (`app/main.py`)**: now also takes `store-processed-data` and `store-config` as State. After writing the migtime CSV, it flushes the current in-memory processed DataFrame to (a) the project session_data parquet via `_save_processed_to_disk`, (b) the workdir `processed_data.parquet`, and (c) the FlagsRemoved.gpkg. So "Export Updated Table" is now the single canonical "save everything" button — migtime CSV + flag state + cleaned GPKG — and the status banner reports the FlagsRemoved filename when the persist step succeeds.
- **Risk acknowledged**: if the user makes flag edits and closes the browser tab without clicking Export, those edits are lost. Acceptable tradeoff for the latency win on individual clicks, and consistent with how the migtime table already works (Tab 2 edits live in `store-migtime-table` until Export). Could later add a beforeunload nag if it becomes a real footgun.

**Files touched.** `app/main.py` (`_apply_flag_to_selection`, `export_migtime`), `INFORMATION.md` (this entry).

### 2026-06-06 — FlagsRemoved now writes GeoPackage (.gpkg) instead of Shapefile (.shp)

**Why.** ESRI Shapefile's `.dbf` attribute table caps field names at 10 ASCII characters (a dBASE III constraint from the 1980s). Every flag toggle was re-emitting FlagsRemoved as `.shp` and GDAL was silently laundering long names — `mortality_flag` → `mortality_`, and worse, `displacement_animal_id` and `displacement_id_bio_year` both started with `displaceme` and collided into `displace_1` / `displace_2`. That's a real downstream-correctness problem (silent name collisions, lost round-trip, cross-tool confusion), not just terminal noise. The earlier "suppress the warnings" patch hid the symptom without fixing the cause.

**What changed.** `write_flags_removed_shapefile` now writes `.gpkg` via `gdf.to_file(..., layer=stem, driver="GPKG")`. GeoPackage is a modern OGC SQLite-backed format with no field-name limit, opens cleanly in QGIS, ArcGIS Pro, R `sf`, and `geopandas`. Removed the `warnings.catch_warnings()` suppression block — with `.gpkg` there are no warnings to suppress. Filename changed from `<Herd>_<Project>_FlagsRemoved_<DDMMMYYYY>.shp` to `…_FlagsRemoved_<DDMMMYYYY>.gpkg`; layer name inside the .gpkg matches the file stem so GIS tools open it with a sensible default label. Function name kept as `write_flags_removed_shapefile` for now (every caller already uses that name); not worth a rename + import churn.

**What stayed `.shp`.** MigPoints, MigLines, MigLines_Dist, popUseMerged, footPrintsMerged — these are the shapefiles the original WMI Migration Mapper *consumes*. Forcing GeoPackage there would break compatibility with downstream R / ArcGIS workflows the analyst team already runs. FlagsRemoved is different: it's a visual cross-check exported *by* this app, not a Migration Mapper input.

**Files touched.** `app/modules/population_outputs.py` (writer + docstring), `app/main.py` (Tab 1 comment), `INFORMATION.md` (this entry).

### 2026-06-06 — Flag actions: rebuild only the edited animal's map cache

**Why.** User reported clicking "Flag as Problem" and seeing nothing happen. Root cause: `_apply_flag_to_selection` was calling `_precompute_animal_maps(df.copy())`, which clears `_MAP_CACHE` and rebuilds an entry for *every* animal-year in the dataset. On herds with dozens of animals that is a multi-second hang while the per-animal `_build_animal_map_entry` loop runs — long enough that a user clicks the button, sees no immediate UI response, and gives up.

**What changed.** Replaced the herd-wide rebuild with a single-animal rebuild keyed on `animal_key` (the dropdown's current `<animal_id>_<bio_year>`). Slice `df[df["id_bio_year"] == animal_key]`, build one entry, write it into `_MAP_CACHE[animal_key]`. Other animals' cached entries are untouched — they'll be rebuilt lazily by `_ensure_animal_map_entry` next time the user navigates to them, picking up the flag changes from the on-disk parquet then. Wrapped in try/except so a single bad animal can't break the flag callback.

**Files touched.** `app/main.py` (`_apply_flag_to_selection`), `INFORMATION.md` (this entry).

### 2026-06-06 — Ghost-point click target restored + FlagsRemoved warning suppression

**Why.** After demoting flagged points to ghost styling earlier today, the user reported that clicking ghost points to *unflag* them yielded `"No points selected. Click points on the map first."` That message comes from `_apply_flag_to_selection`'s empty-selection guard — meaning `store-tab2-selection` was empty when the Unflag callback read its State. Root cause: the ghost styling dropped `circle-radius` to 1.5/3/5 px (was 2.5/5/8), making the points hard to hit at typical zooms — clicks were missing and landing on empty map, which clears the iframe's `selectedKeys` set (`maplibre_map.html` line \~256). Also: every `write_flags_removed_shapefile` call (which runs on every flag toggle) spewed ~15 UserWarning + RuntimeWarning lines about ESRI Shapefile's 10-char field-name truncation, drowning the terminal in noise.

**What changed.**

- **`app/assets/maplibre_map.html`**: reverted `circle-radius` to the standard `2.5/5/8` interpolation for *all* points. Flagged points still read as ghosts via 15 % fill opacity + thin red/grey stroke at 85 % opacity — the visual demotion is intact, only the hit-test target is restored.
- **`app/modules/population_outputs.py`** (`write_flags_removed_shapefile`): wrapped the `gdf.to_file(out_path)` call in `warnings.catch_warnings()` with two `filterwarnings("ignore", ...)` patterns for `"Column names longer than 10 characters"` and `"Normalized/laundered field name"`. Scope is local — every other shapefile writer in `population_outputs.py` still gets the warnings, so they remain available for debugging when an export is genuinely going wrong.

**Why not rename the long columns instead of suppressing.** FlagsRemoved is a visual cross-check shapefile, not a column-round-trip artefact. The Migration Mapper reference uses the same truncation. Renaming risks breaking compatibility with downstream R / ArcGIS tools that expect the truncated names.

**Files touched.** `app/assets/maplibre_map.html` (radius), `app/modules/population_outputs.py` (warnings suppression), `INFORMATION.md` (this entry).

### 2026-06-06 — Problem points become "ghost points": shown but excised from analysis + track line

**Why.** When the user flags a fix as a problem, three things should happen: (1) it must be excluded from sequence extraction/modeling, (2) it must still be visible on the map so the user can see what was removed, and (3) the connecting track line should read A→C — skipping the flagged B — so the visual matches the analytical reality. Previously only the modeling/export side filtered correctly; the map line still walked through flagged points, and points-of-removal had only a thin red border (visually still a "normal" point).

**What changed.**

- **`app/modules/population_outputs.py`**: added `import pandas as pd` at the top. `write_flags_removed_shapefile` was calling `pd.api.types.is_datetime64_any_dtype` to coerce DBF-hostile datetimes to strings without ever importing pandas — first time the FlagsRemoved refresh ran on a flag toggle (`main.py` line \~4334) it raised `NameError: name 'pd' is not defined`. Caught and logged but the shapefile silently failed to write.
- **`app/modules/sequencing.py` (`extract_sequences`)**: replaced the dead `if "flag" in df.columns` filter (matched the long-standing to-do list item) with explicit checks on numeric `problem` and `mortality_flag` columns. Flagged fixes are now dropped before the per-sequence date-window slicing, so every sequence GeoDataFrame consists only of kept fixes — the modeling side sees A→C with B excised.
- **`app/main.py` (`_build_animal_map_entry`)**: track-line construction now builds a `keep_line = (problem == 0) & (mortality_flag == 0)` mask from the per-animal slice *before* striding into the LineString. The line walks through only kept fixes, so visually the path now reads A→C when B is flagged. Same `~3000-vertex` subsampling cap as before, just applied to the kept slice.
- **`app/assets/maplibre_map.html` (`animal-points-layer`)**: flagged fixes now render as proper ghost dots — 60 % smaller radius (`1.5/3/5` vs `2.5/5/8`), 15 % fill opacity (was 90 %), thinner stroke (1.2 vs 2), and slightly faded stroke (85 %). Unflagged points are unchanged. Effect: the flagged fix is still visible enough to point at, but unmistakably "demoted" — no chance of mistaking it for an in-analysis point.

**Files touched.** `app/modules/population_outputs.py`, `app/modules/sequencing.py`, `app/main.py` (track-line build), `app/assets/maplibre_map.html` (points-layer paint), `INFORMATION.md` (this entry).

### 2026-06-06 — Tab 2: Max sequences setting now re-renders the slot list live

**Why.** Changing the "Max sequences" input from 4 → 2 left four slider cards on screen. `seq-num-sequences` was wired as a `State` on `update_nsd_plots`, so the new value was only picked up the next time some *other* trigger (animal change, Auto-detect All) fired. User expected it to reflect immediately.

**What changed.** Promoted `seq-num-sequences` from `State` to `Input` on `update_nsd_plots`, and reordered the function signature accordingly. Every edit to the number now fires the callback and re-renders the slot list to the new count.

**Files touched.** `app/main.py` (`update_nsd_plots` decorator + signature), `INFORMATION.md` (this entry).

### 2026-06-06 — Tab 2: per-sequence "Clear sequence" button on each slider card

**Why.** The header-level Clear Sequences button blanks every slot for the current animal at once. The user wanted a finer scalpel: clear just one sequence (e.g. a bogus mig3) while leaving mig1/mig2 intact.

**What changed.**

- Each sequence card in `update_nsd_plots`'s slot-render loop now has a small outline-secondary `Clear sequence` button in the header next to the confidence/empty meta line. Pattern-matching id `{"type": "btn-clear-seq", "index": "mig{N}"}` so a single callback can address every slot.
- New callback `clear_single_sequence` (next to `clear_current_animal_sequences`). Pattern-matching: `Input({"type": "btn-clear-seq", "index": MATCH}, "n_clicks")` → `Output({"type": "seq-range-slider", "index": MATCH}, "value")`. Sole output is the slider's `[0, 0]`. Dash's pattern-matching rules require every MATCH key to appear in every Output, so a single callback can't both reset the MATCH slider *and* write to the non-pattern `store-migtime-table` — keeping this callback Output-only-MATCH is what makes Dash accept it. The existing `slider_to_migtime` callback (already wired to slider value changes) picks up the `[0, 0]` and blanks `mig{N}_start` / `mig{N}_end` for the current animal's migtime row, so the migtime mutation still happens — just one hop later via the already-built plumbing.
- Does *not* set the per-row `seq_cleared` sticky flag — that flag means "this whole animal is in a blank-slate state, suppress detection suggestions for all slots." A per-slot clear is narrower: the other slots should still show their detection suggestions on the next render. The slider snapping handled by the MATCH output covers the visible reset for the cleared slot.

**Files touched.** `app/main.py` (button in sequence card header, new `clear_single_sequence` callback), `INFORMATION.md` (this entry).

### 2026-05-22 — Tab 2: "Clear Auto-Detect" → "Clear Sequences" (per-animal sticky reset)

**Why.** The previous "Clear Auto-Detect" button wiped every `mig{i}_start` / `mig{i}_end` cell across the *entire* migtime table, but the sliders kept showing fresh auto-detection suggestions because `update_nsd_plots` re-runs `detect_migrations_nsd` on every callback fire and uses the detection output (not migtime) to position the sliders. Net effect: the button reset the map's point colours but the sliders looked unaffected, which read as "broken" to the user. The user also pointed out that clearing the whole table on a per-animal review screen is the wrong scope — they want to clear *this* animal's sequences and move on, not blow away an hour of review work on the other 50 animals.

**What changed.**

- **Button rename + id change.** Header label is now `Clear Sequences`; id is `btn-clear-sequences` (was `btn-clear-autodetect`). Outline-secondary styling unchanged.
- **New per-row sticky flag `seq_cleared` (bool) in the migtime table.** Added lazily by the clear callback so existing migtime rows without the column still work. When True, `update_nsd_plots` forces `detection_by_slot = {}` for that animal so all sliders render at `[0, 0]` and `confidence_text` reads *"Sequences cleared for <animal>. Drag any slider to start defining a window manually, or click Auto-detect All to re-run detection."* The flag survives animal navigation — that's what makes "Clear" actually stick.
- **`clear_current_animal_sequences` (was `clear_autodetected_migrations`).** Now takes `seq-animal-dropdown` as State and operates on a single row (`migtime["id_bio_year"] == selected_animal`). Blanks that row's mig date columns, sets `auto_detected=False`, sets `seq_cleared=True`. Returns the migtime + a status banner like "Cleared 4 date entries for E18_2024. Sliders reset to 0."
- **`slider_to_migtime` flips `seq_cleared=False` on drag.** The user dragging a slider is the unambiguous signal that they're done with the blank slate and are defining sequences again. Without this, the cleared flag would persist forever and the *next* slider drag would have its detection-driven repositioning overridden on the next callback fire.
- **Auto-detect All implicitly resets `seq_cleared` for everyone.** The existing scaffold rebuild path in `update_nsd_plots` calls `build_migtime_table(...)` which returns a fresh table without the `seq_cleared` column. So clicking Auto-detect All gives a clean slate across the whole herd — which matches user intent for that button.

**Files touched.** `app/main.py` (button label/id, callback rename + scope change, `update_nsd_plots` cleared-flag check before slot render, `slider_to_migtime` flag-off-on-drag), `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 2: vertical resize handles on the sequence card and NSD plot

**Why.** Fixed-height sections make Tab 2 awkward when the user wants either a denser overview (small sequence card, large NSD) or a detailed editing view (large sequence card with many sliders visible, compact NSD).

**What changed.** Each block is wrapped in an `html.Div` with `resize: vertical; overflow: hidden` plus min/max heights. Sequence Date Ranges card defaults to `260px` (range `80`–`800`) with `overflowY: auto` on the body. NSD plot defaults to `280px` (range `120`–`900`); the inner `dcc.Graph` uses `style.height: 100%`, `responsive=True`, and `config.responsive: True` so Plotly redraws when the container resizes. CardHeader gained a `↕ drag corner to resize` hint. Browser-native `resize: vertical` puts the grip in the bottom-right corner; per-window-session, resets on page reload.

**Files touched.** `app/main.py` (Tab 2 middle column), `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 2: scroll-wheel zoom on the NSD plot

**Why.** NSD covers a full bio-year; zooming into a specific date range used to require Plotly's draw-a-rectangle from the modebar, which was hidden via `displayModeBar: False`.

**What changed.** Added `scrollZoom: True` to the NSD plot's `dcc.Graph` config. Wheel up/down zooms; double-click resets to the bio-year x-range. Other plots (Displacement, Speed, Elevation) intentionally not given the same treatment — they're short enough to read at default zoom.

**Files touched.** `app/main.py` (one config dict), `INFORMATION.md` (this entry).

### 2026-05-19 — Briefly added a server-mirrored pop-out window for NSD + sliders, then reverted

**Status: REVERTED.** Built a `?view=popout` second-window flow (commits `6b9a94a`, `ff6576c`) with a 1.5 s `dcc.Interval` polling server-side `_DF_CACHE` versions so slider edits flowed between windows within \~1.5 s. Worked, but user decided a scroll-wheel zoom on the NSD plot met the underlying need more simply. Reverted in `fae1297` and `17b601c`. Noted here so a future multi-window attempt doesn't re-invent the same plumbing without knowing it existed:

- Server-side `_CACHE_VERSIONS: dict[str, int]` bumped by `_df_to_json` on every write. Token shape gained `"v": N`.
- `_maybe_refresh_cache_token(cache_key, current_token)` returns a fresh token only when server `v` \> client `v`.
- Layout factory `serve_layout()` checked `flask.request.args.get("view") == "popout"`.
- Hidden mirrors of plot/seq IDs plus existing `suppress_callback_exceptions=True` kept popout-view callbacks from choking on missing outputs.

If multi-window comes back, that pattern (Interval + version counter, no websockets) is the cheapest viable approach.

### 2026-05-19 — Tab 2: elevation-over-time chart

**Why.** Wanted an elevation timeline alongside NSD/Displacement/Speed to spot vertical movement invisible on NSD.

**What changed.** New `dcc.Graph(id="elevation-plot")` below Speed. Pulls from existing `elevation_m` column (sampled at Tab 1 processing time when the Elevation raster variable is ticked). When the column is absent or all-NaN, title reads `Elevation — not sampled (enable in Tab 1 raster variables)` so the user knows why it's empty. Same bio-year x-range as the other plots.

**Files touched.** `app/main.py` (Tab 2 layout + `update_nsd_plots`), `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 2: removed NSD/Displacement toggle, show both stacked

**Why.** Header had an `NSD | Displacement` button group whose only function was to swap which of the two plots sat in the top slot — the other still appeared just below in either mode. Zero information difference between modes, plus visual noise.

**What changed.** Removed the button group from `Sequence Date Ranges` CardHeader, `toggle_nsd_view` callback, `store-nsd-view-mode` store, and the corresponding `Input` on `update_nsd_plots`. `nsd-plot` always shows NSD; `displacement-plot` always shows Displacement.

**Files touched.** `app/main.py`, `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 2 sequence sliders: drag-the-middle + live map repaint

**Why.** rc-slider's default track behavior is "click jumps the nearest handle." Users defining a migration window often want to *shift* a fixed-width window across the calendar — drag the middle, both handles move together. Also: slider edits should make the map repaint immediately rather than only after Auto-detect or a manual click.

**What changed.**

*1. Drag the middle (clientside JS).* New IIFE in `app/assets/map_functions.js` installs a single document-level `mousedown` listener in **capture phase** so it runs before rc-slider's own handler. When the target is `.rc-slider-track` inside `.seq-range-slider`: - Walks up to the nearest element whose `id` parses as JSON — that's Dash's pattern-matching id (`{"index":"mig1","type":"seq-range-slider"}`) on the slider component. - Reads current value and min/max from the two handles' `aria-valuenow` / `aria-valuemin` / `aria-valuemax` (rc-slider keeps these in sync with React state). - Locks the (high − low) length. On `mousemove`, computes pixel delta × `(max−min) / width` = value delta. Clamps so `[newLow, newLow + length]` stays in `[min, max]`. - Pushes the new value with `window.dash_clientside.set_props(idDict, { value: [newLow, newHigh] })`, which updates Dash's React state and triggers all downstream callbacks. - `e.preventDefault()` + `e.stopPropagation()` block rc-slider's default jump-to-position. Empty slots (`v0 === v1`) bail early so the user can still click the rail to seed a window.

*2. Track styling.* `.seq-range-slider .rc-slider-track` gets `cursor: grab` and `:active { cursor: grabbing; }` to signal the new affordance.

*3. Slider → migtime callback (server).* New pattern-matching callback `slider_to_migtime` on the slider's `value` change writes `migN_start` and `migN_end` into the migtime row keyed by the current `seq-animal-dropdown` value. Parses `N` from the slider id's `index` (`mig1` → slot 1). Empty slots (start == end) write blank strings instead of dates. Short-circuits with `PreventUpdate` when the new strings already match what's in migtime — avoids triggering an unnecessary map repaint on first render. The existing map callback already has `Input("store-migtime-table", "data")`, so the points repaint immediately as the slider moves.

**Files touched.** `app/assets/map_functions.js` (new middle-drag IIFE), `app/assets/style.css` (track cursor), `app/main.py` (new `slider_to_migtime` callback), `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 1 dropdowns: "Clear all" option on Recent dirs + Previous projects

**Why.** Both the **Recent working directories** dropdown (top of Tab 1) and the **Load previous project** dropdown accumulate entries over time with no way to reset them from the UI. The user wanted a one-click cleanup.

**What changed.**

- **Recent working directories.** `render_workdir_state` appends a synthetic option `{label: "— Clear all recent directories —", value: "__CLEAR_ALL__"}` whenever the list is non-empty. The `pick_workdir_from_recents` callback now also outputs to `workdir-recents.options` and `workdir-recents.value` (both `allow_duplicate=True`). When the user picks the sentinel, it deletes `app/session_data/recent_workdirs.json`, returns `[]` for the options and `None` for the value, and leaves `store-workdir` untouched (so the active workdir stays put — only the *recents list* is wiped).
- **Previous projects.** `refresh_project_list` similarly appends `{label: "— Clear all previous projects —", value: "__CLEAR_ALL__"}` when the list is non-empty. New callback `maybe_clear_all_projects` fires on `project-selector.value` change: if the sentinel is picked, it walks `app/session_data/` and `shutil.rmtree` every subdirectory that has a `processed_data.parquet` inside, then writes a status banner reporting how many were deleted. `load_project` also got a guard: clicking Load while the sentinel is selected is a no-op.

**Destructiveness.** The recents Clear only deletes the JSON list of paths — your actual workdirs and their contents are untouched. The previous-projects Clear *does* delete the per-project folders under `app/session_data/` (which hold the cached `processed_data.parquet`, `animal_notes.json`, `road_crossings.json`, `project_meta.json`). The user's working directory and its `ModelOutputs/` are not touched, so re-processing from `<workdir>/ModelInputs/` will rebuild any cleared project.

**Files touched.** `app/main.py` (dropdown option lists + clear callbacks + load_project guard), `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 2 bio-year start is honored end-to-end (NSD plots, migtime, map)

**Why.** The user observed that changing "Bio Year Start" to 2/15 on Tab 2 didn't actually shift the bio-year window — sliders, the migtime table, and point coloring all still acted as though the bio-year began on 2/1. Root cause: `id_bio_year` and `bio_year` were computed once at Tab 1 processing time and frozen into the parquet. Tab 2 then keyed everything off those frozen columns, so the UI's bio-year setting only affected slider tick labels — never the actual data slicing.

**What changed.** Three places now recompute `id_bio_year` on the fly from the UI's `bio_month`/`bio_day`:

1.  **`populate_animal_dropdown`** — added `seq-bio-year-month` and `seq-bio-year-day` as `Input` (so the dropdown rebuilds when the user changes them) and a `State` for the previously-selected animal (preserved across rebuilds if still valid). Options come from re-derived `<animal_id>_<bio_year>` keys, not the frozen column.

2.  **`update_nsd_plots`** — first thing after pulling the DataFrame, the local copy gets fresh `bio_year` and `id_bio_year` columns derived from the UI values. Everything downstream — animal_df filter, per-animal `detect_migrations_nsd`, full-DataFrame migtime population — keys off those re-derived columns. So per-animal slider suggestions, the migtime table, and the points-coloring lookup all run on the same UI-defined window.

3.  **`update_seq_map`** — added `seq-bio-year-month`/`day` as `State` and a new module-level `_MAP_CACHE_BIO_KEY` that tracks `(bio_month, bio_day)` the cache was built with. When it changes, `_MAP_CACHE` is wiped and rebuilt lazily by re-deriving `id_bio_year` from the UI values and calling `_ensure_animal_in_cache(df_with_redrived_keys, selected_animal)`. Avoids stale cached point arrays after a bio-year change.

Net result: setting Bio Year Start = 2/15 means *every* bio-year in the UI runs 2/15 → next year's 2/14 — for the slider date range, the auto-detected migration windows, the migtime export, and the colored points on the map. Tab 1 processing-time `bio_month`/`day` becomes irrelevant for Tab 2 display (it still affects the *frozen* columns in the parquet, which other code paths may reference, but Tab 2's UI no longer depends on them).

**Caveat.** Doesn't try to migrate existing migtime data when bio-year changes mid-session — the migtime is keyed on `id_bio_year`, so changing the bio start invalidates existing entries. The user will need to click Auto-detect All again (or rely on Clear Auto-Detect → manual entry) after changing the setting. Acceptable since this is a deliberate workflow choice, not a parameter to tweak on every animal.

**Files touched.** `app/main.py` (new module global, three callbacks updated), `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 2 map: brighter track line + consistent per-animal detection

**Two changes:**

**(1) Track line is now pale yellow instead of dim white.** `maplibre_map.html` `animal-line-layer` paint changed from `{line-color: #fff, line-width: 1.5, line-opacity: 0.35}` to `{line-color: #FFE680, line-width: 1.8, line-opacity: 0.7}`. Yellow stands out cleanly against the dark hillshaded basemap while still letting the colored points dominate when they're visible.

**(2) Auto-detect All no longer colors points on animals whose per-animal view found nothing.**

*Why.* Two separate calls into `detect_migrations_nsd` were operating on subtly different inputs: per-animal display used a timestamp-windowed slice built from the UI's `bio_month`/`bio_day` (`animal_df = df[(animal_id==X) & (timestamp in window)]`), while full-DataFrame migtime population grouped on the `id_bio_year` column (which was computed and frozen at *processing* time, possibly with different bio-year start values). If the two diverged for an animal, the per-animal slider could show "no detections" while the migtime carried windows from the full-DF call — and those windows then colored points on the map.

*Fix.* The per-animal slice now uses `df[df["id_bio_year"] == selected_animal]` directly, the same key the migtime build groups on. So both detection calls operate on identical rows, and per-animal display + migtime-driven map coloring stay consistent. Kept the old timestamp-window mask as a fallback in case `id_bio_year` is absent (shouldn't happen post-processing, but defensive).

**Files touched.** `app/assets/maplibre_map.html` (line color), `app/main.py` (`update_nsd_plots` animal-df filter), `INFORMATION.md` (this entry).

### 2026-05-19 — Manual Herd ID override on Tab 1

**Why.** The auto-derivation logic (joining unique DAU values, committed earlier today) still produced `0` for the user's dataset — likely because that dataset's DAU column actually contains numeric 0s alongside real DAU codes, or the DAU column has a name the candidate-list doesn't match. Rather than keep chasing edge cases in detection, give the user a manual escape hatch.

**What changed.**

- New text input "Herd ID (optional override)" sits between the bio-year row and the DOP/Min-Satellites row in Tab 1's processing-parameters card (`id="param-herd-id-override"`). Full-width, single line. Placeholder: `e.g. E18_E22 (leave blank to auto-derive from DAU column)`.
- `process_uploaded_data` takes the field as a new `State` (last arg of both the decorator list and the function signature). After `process_data(...)` returns, if the user typed something, it's stripped, whitespace-collapsed to `_`, and stripped of any non-`\w-` characters (same character set the auto-deriver uses for project tokens) — then written into `final_config["herd_id"]` with `herd_id_source_col = "user override"`. A line is appended to the processing log noting what the override replaced.
- Blank input means "do nothing" — auto-derivation result stands. So existing single-DAU workflows are unchanged.

The Processing Summary card already reads `final_config["herd_id"]` for its "Herd ID:" row, and the same value flows into output filenames (FlagsRemoved shapefile, MigLines, MigPoints, popUseMerged, footPrintsMerged), so the override propagates everywhere automatically without per-call-site changes.

**Files touched.** `app/main.py` (new input in Tab 1 layout, new State + handling in `process_uploaded_data`), `INFORMATION.md` (this entry).

### 2026-05-19 — Multi-DAU herd_id concatenates all distinct DAU codes

**Why.** A dataset spanning multiple Data Analysis Units (DAUs) was producing `Herd ID: 0` — the derivation just grabbed `non_null.iloc[0]` from the DAU column, which happened to be a numeric 0 for the first row. The whole point of the herd_id is to label outputs unambiguously; reducing a multi-DAU dataset to whichever DAU happens to sit at row index 0 is misleading and silently loses information.

**What changed.** In `data_ingestion.py`'s herd_id derivation block:

- Build `cleaned` = list of all non-blank stripped values from the chosen candidate column.
- `unique_values = sorted(set(cleaned))` — drops dupes, deterministic order so the same dataset always yields the same herd_id regardless of row order.
- `herd_id = "_".join(unique_values)` — single-DAU datasets are unchanged (length-1 list joins to itself), multi-DAU datasets get `A37_B12_C04` etc.
- Log line gains a `(joined N unique values …)` suffix when N \> 1, so the processing log makes the multi-DAU situation obvious.

Falls back to `"Herd"` only when *every* candidate column (`DAU`, `dau`, `CptrDAU`, `Project`, `project_name`) is missing or empty — that branch was already correct.

**Files touched.** `app/modules/data_ingestion.py` (herd_id derivation), `INFORMATION.md` (this entry).

### 2026-05-19 — Friendly error when a bare .shp is drag-and-dropped

**Why.** Dragging a `.shp` file directly into Tab 1's upload widget produced GDAL's stock "Unable to open .shx … Set SHAPE_RESTORE_SHX config option to YES" error. Root cause: the browser drag-and-drop API only transmits the single file the user dragged, so the `.shx`/`.dbf`/`.prj` sidecars never reach the server — GDAL then can't open the shapefile. The default error is unactionable for a non-technical user.

**What changed.** `handle_upload` (Tab 1) now short-circuits when `filename.suffix == ".shp"` *before* writing anything to disk, returning an error alert that explains the cause and gives two concrete fixes: zip the shapefile set in Windows Explorer (right-click → Send to → Compressed (zipped) folder) and drop the zip, or copy the full shapefile set into `<workdir>/ModelInputs/` and pick from the dropdown (which uses a real on-disk path, so sidecars beside the `.shp` are found normally). The existing `.zip` upload path already handled bundled shapefiles end-to-end, so no new file-format support was needed — just signposting.

**Deliberately not done.** Did *not* set `SHAPE_RESTORE_SHX=YES` to silently auto-rebuild the missing index. It would rebuild geometry but produce a shapefile with no attribute table (no `.dbf`), which is more confusing than failing loudly.

**Files touched.** `app/main.py` (`handle_upload` early-return for bare `.shp`), `INFORMATION.md` (this entry).

### 2026-05-19 — "Project Loaded" card shows the original input file path

**Why.** When a user opens an existing project (Load Project → Process Data), the summary card showed counts, date range, and enrichment columns — but not which raw file actually fed it. A user revisiting an old project a week later had no easy way to remember whether it came from `Herd_A_2023.csv` or `Herd_A_2024_revised.csv`.

**What changed.**

- New `_save_project_meta` / `_load_project_meta` helpers (in `app/main.py`, just above `_load_notes`) read/write a small `project_meta.json` inside `app/session_data/<project_name>/`. Fields: `input_source_path`, `wld_source_path`, `processed_at` (ISO timestamp), `workdir`.
- `process_uploaded_data` now writes that file right after `_save_processed_to_disk`, recording the `tmp_path` (the actual file the pipeline read from — usually `<workdir>/ModelInputs/<original_filename>` when a workdir is set, or a temp file otherwise) and the WLD path if one was used.
- `_build_loaded_project_summary` takes a new optional `meta` arg and renders three new rows when present: **Input file:**, **WLD file:**, and **Processed at:**. The path strings are wrapped in `html.Code(...)` with `wordBreak: break-all` so long Windows paths line-wrap inside the card instead of overflowing.
- The one existing call site in `process_uploaded_data` (the "already loaded — re-rendering summary" branch) now passes `_load_project_meta(...)` through.

**Files touched.** `app/main.py` (two new helpers, one new write in process_uploaded_data, signature + rendering updates in `_build_loaded_project_summary`, call-site update), `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 2 migtime: scaffold on first load, auto-detect only on explicit click

**Why.** After defaulting unassigned points to black (earlier today), user reported that *some* points were still colored on the very first animal — even with the confidence text saying "no migrations auto-detected" for that animal. Root cause: `update_nsd_plots` rebuilt the full migtime table the first time it ran (the `or not current_migtime_json` branch) and *also* ran `detect_migrations_nsd` over the entire DataFrame to populate it. Per-animal detection and full-DataFrame detection don't always agree (different filter context, grouping path), so the migtime could carry auto-detected windows for the current animal even though the per-animal pass found none — and those windows colored the points.

**What changed.** Split the build logic in two:

- `should_build_scaffold` = first-time-empty store OR Auto-detect All click → builds an *empty* migtime via `build_migtime_table` so the schema (one row per `id_bio_year` with NaT mig columns) exists. Export and the per-row notes population need this to work.
- `should_auto_populate` = Auto-detect All click *only* → runs `detect_migrations_nsd` over the full DataFrame and merges results in via `apply_auto_detections`.

So on a fresh open: scaffold exists, no detections committed, all points black. Per-animal slider cards still show real-time detection *suggestions* from the per-animal `detect_migrations_nsd` call (that path is unchanged) — they just don't enter the migtime until the user accepts via the button or by dragging.

**Files touched.** `app/main.py` (`update_nsd_plots` migtime build block), `INFORMATION.md` (this entry).

### 2026-05-19 — Tab 2 map: unassigned points default to black + Clear Auto-Detect button

**Why.** Two related complaints. (1) Even before the user defined any migrations, some points on the Tab 2 map appeared coloured. Reason: auto-detection populated `mig{i}_start/end` in the migtime store as soon as an animal was selected, and `_build_point_geojson` colours every point whose timestamp lands inside one of those windows. So the user saw "phantom" sequence colours from auto-detected ranges they hadn't yet reviewed. (2) No way to walk that back — a user who preferred manual definition had no button to wipe the auto-detected ranges.

**What changed.**

- Default point colour for unassigned (no-migration-window) points is now `#000000` instead of `#888888` — both in `_build_point_geojson` (`app/main.py`, around the `colors = np.full(...)` line) and as the MapLibre fallback in `app/assets/maplibre_map.html` (`circle-color` coalesce default `#888` → `#000`). The two layers were already in sync on the same default; both shifted together.
- New "Clear Auto-Detect" button below the existing "Auto-detect All" button in Tab 2's left sidebar. Outline-secondary style so it reads as a less-prominent counterpoint to the info-coloured Auto-detect button right above it.
- New callback `clear_autodetected_migrations` (sits with the other migtime mutators just above `_crossing_phrase`): on click, blanks every `mig{i}_start` / `mig{i}_end` cell in the migtime table for `i in 1..8`, sets `auto_detected=False`, and writes the table back to `store-migtime-table`. The Tab 2 map already listens to that store (`Input("store-migtime-table", "data")` on the map payload callback), so points immediately repaint to black with no extra wiring.
- Counts how many date cells it cleared and reports the number in the migtime-status banner.

**What was deliberately *not* changed.** The per-animal slider cards still display real-time auto-detection suggestions (from `detect_migrations_nsd` running on every animal selection in `update_nsd_plots`). Only the migtime-table-derived point colouring resets to black. So a user who clicks Clear Auto-Detect and then navigates to an animal still sees a *suggestion* of sequence ranges in the sliders, but those suggestions don't enter the migtime — and so don't colour the map — until they explicitly accept them (by dragging or hitting Auto-detect All again). This was a judgement call: leaving the slider suggestions visible keeps the workflow useful for users who want to skim and confirm rather than rebuild from scratch. If feedback says otherwise, we can add a sticky "disable auto-detect" flag in `dcc.Store(storage_type="local")` and gate `detect_migrations_nsd` on it.

**Files touched.** `app/main.py` (default colour, new button, new callback), `app/assets/maplibre_map.html` (fallback colour), `INFORMATION.md` (this entry).

### 2026-05-19 — Migtime export `notes` column auto-populated from per-animal notes + crossings

**Why.** Two pieces of per-animal context were being collected in the UI but lost on export. (1) The free-text *Notes* field next to the map (saved per-`id_bio_year` to `animal_notes.json`) — never made it into the migtime CSV. (2) The Crosses Road / Crosses Highway badges in Tab 2 — a useful one-line summary for downstream readers that wasn't being recorded anywhere structured. Goal: every time the user exports or overwrites the migtime table, the `notes` column should reflect the latest user note plus a single canonical crossing statement.

**What changed.** Two new helpers in `app/main.py`:

- `_crossing_phrase(crosses_road, crosses_highway)` → string. Highway supersedes road; if both are true, only `"Crosses highway."` is emitted. If neither, returns `""`. So every row gets at most one crossing statement.
- `_compose_notes(user_note, crosses_road, crosses_highway)` → string. Strips trailing whitespace from the user note, removes any previously-appended canonical crossing phrase (so re-exports don't double up), then appends the current crossing phrase. Idempotent on repeated exports.
- `_populate_migtime_notes(migtime, notes_store, road_store)` → fills the migtime DataFrame's `notes` column in place, keyed on `id_bio_year`.

The `Export Updated Table` and `Overwrite Table` callbacks now both take `store-animal-notes` and `store-road-crossings` as additional `State` and call `_populate_migtime_notes` immediately before writing the CSV.

**Keying.** All three stores (`store-migtime-table`, `store-animal-notes`, `store-road-crossings`) key on `id_bio_year`. Cast both sides to `str` because dict keys round-tripped through `dcc.Store` JSON serialisation come back as strings, while pandas may carry mixed types.

**Idempotency.** The compose step strips any trailing `"Crosses road."` or `"Crosses highway."` *before* appending the current phrase. So if the user types "Late departure, weak signal" + the row had `crosses_road=True` last export, then `crosses_highway` flips to `True`, the next export writes "Late departure, weak signal Crosses highway." — not "...Crosses road. Crosses highway."

**Files touched.** `app/main.py` (three new helpers + two callback signatures updated), `INFORMATION.md` (this entry).

### 2026-05-19 — Sequence sliders: tooltips now show dates, not day-of-bio-year integers

**Why.** Each per-sequence `dcc.RangeSlider` had two tooltip "boxes" above the handles that displayed the raw slider value — an integer in 0…365 representing the day-offset from the bio-year start. Useless to a user dragging the slider; they want to know *what calendar date* they just snapped to. Asked for: the date currently under each handle, always visible above the handle ends.

**What changed.**

- `app/assets/map_functions.js` — registered `window.dccFunctions.dayToDate(value)`. Dash's `dcc.RangeSlider` looks for transform functions on `window.dccFunctions` by name, calls them with the slider's numeric value, and renders the returned string in the tooltip. The function reads `window._sliderDateMin` (an ISO date string) and returns `value` days later as `YYYY-MM-DD`. Falls back to the raw value if `_sliderDateMin` is unset or the inputs are bad.
- `app/main.py`, sequence-card rendering — `RangeSlider(tooltip=…)` changed from `{placement: "bottom", always_visible: False}` to `{placement: "top", always_visible: True, transform: "dayToDate"}`. So the date label is permanently visible above each handle and updates live as the user drags.
- `app/main.py`, new clientside callback right before the model-progress visibility callback — mirrors `dcc.Store(id="store-slider-date-min").data` into `window._sliderDateMin` so the JS transform can see it. Output uses `allow_duplicate=True` so this doesn't conflict with the server-side write of the same store; the callback returns `no_update`, it's a pure side-effect.

**Why a clientside callback instead of writing date_min into a data attribute on each slider.** The transform receives only the numeric value, with no reference to the slider element, so per-element data attributes aren't reachable. A single global keeps the transform stateless and avoids re-rendering every slider every time the bio-year date_min changes.

**Files touched.** `app/assets/map_functions.js` (new `dayToDate` function), `app/main.py` (tooltip prop + one new clientside callback), `INFORMATION.md` (this entry).

### 2026-05-19 — `Start App.bat` waits for the server before opening the browser

**Why.** The previous script ran `start http://127.0.0.1:8050/` on line 6 and *then* started Python on line 7. The browser hit the URL before Dash was listening, got a "site can't be reached" page, and the user had to manually refresh. Bad first impression for a non-technical operator, who has no reason to know the page just needs a refresh.

**What changed.**

- Validates `C:\Program Files\Python313\python.exe` exists up front and bails with a clear "run Setup.bat" message if not.
- If port 8050 is already in `LISTENING` state (the app is already running in another window), just opens the browser to the existing instance and exits — no second Python process, no port conflict.
- Otherwise launches Python in a *separate* titled window ("Colorado Migration Mapper - Server"), then polls `curl http://127.0.0.1:8050/` once per second for up to 60 s. Browser opens only after curl gets a response.
- If the server doesn't come up in 60 s, prints a message pointing the user to the server window (which still shows the Python traceback) and pauses so the message is readable.

**Caveat.** `curl` is required; it ships with Windows 10 build 17063+ (April 2018) and Windows 11. Not a concern on this machine (Windows 11) but worth noting if we ever support Windows 8 or stripped-down corporate images.

**Files touched.** `Start App.bat` (full rewrite, \~50 lines), `INFORMATION.md` (this entry).

### 2026-05-19 — RUN_MODELS session log now records the full model configuration

**Why.** Previously `_log_action("RUN_MODELS", …)` only wrote `method`, `n_sequences`, and `cores` to `<workdir>/session_log.txt`. That's not enough to reproduce a run later — readers couldn't tell which `cell_size`, `contour`, `bm_var`, `time_step`, `max_lag`, `smooth_param`, `mult4buff`, `buff_distance`, etc. the run used. Goal: the project's session log alone should be sufficient to reconstruct the model parameters of any past run, including defaults that the user never touched.

**What changed.**

- `run_modeling` in `app/main.py` now expands every key from the in-memory `config` dict (the one returned by `get_model_config()` plus the cell-size override from the pop grid) into the `RUN_MODELS` log call. `ud_dir`, `footprint_dir`, and `method` are excluded — the first two are machine paths, the third is already logged explicitly.
- A new `fix_rate_hours=` field is also logged. It records the median GPS fix rate the config was generated from (or the literal token `auto` if the migtime DataFrame didn't carry that column). This matters because `get_model_config` flips `bm_var` from `None` (auto-estimate) to `5000.0` (fixed) when `fix_rate_hours > 12`, so without logging the input you can't always tell from `bm_var` alone whether the value was user-chosen or auto-set.
- Defaults are logged identically to explicitly chosen values — there's no "default vs. set" distinction in the line. If you want to know which were defaults, compare against `get_model_config()` in `app/modules/modeling.py` (section labelled "8. get_model_config", which lists every default with its R-equivalent name and units).

**Log line shape.** One line, space-separated `key=value` pairs, timestamped. Example for a Kernel UD run with all defaults:

```         
2026-05-19 14:32:01  RUN_MODELS  method=KERNEL n_sequences=12 cores=4 fix_rate_hours=2.0 num_cores=1 max_timeout=600 mult4buff=0.3 cell_size=500 time_step=5 bm_var=None location_error=20 max_lag=8 contour=99 dbbmm_margin=3 dbbmm_window=11 info_criteria=AIC smooth_param=None subsample=1 buff_distance=300
```

Some of those keys are no-ops for the chosen method (`buff_distance` is irrelevant to Kernel UD, `smooth_param` is irrelevant to BBMM, etc.), but they're all logged anyway — the cost is one extra line of text, and it makes the log self-describing without the reader needing to know which keys apply to which method.

**Files touched.** `app/main.py` (one block in `run_modeling`, around line 3812), `INFORMATION.md` (this entry).

### 2026-05-18 — Browser OOM on Process Data fixed: server-side DataFrame handles

**Symptom.** On 100k+ point datasets, clicking Process Data made the browser tab crash with "Out of Memory."

**Root cause.** `_df_to_json` serialised the full processed DataFrame to JSON and shoved it into `dcc.Store(id="store-processed-data")`. For a large herd with WLD env vars merged in, that payload was easily 50–200 MB. Dash transports it to the browser and parks it in tab memory; Chrome on Windows kills the tab around the same threshold.

**Fix.** Two-function surgical change in `app/main.py`:

- `_df_to_json` now caches the DataFrame in `_DF_CACHE` (already was) and returns only a tiny token `{"__cache_key": ..., "rows": N, "cols": M}`. The browser store holds kilobytes instead of megabytes.
- `_json_to_df` already preferred `_DF_CACHE` on a hit — added a token-aware cold-cache path: for `cache_key="processed"`, it rehydrates from `processed_data.parquet` on disk; for other keys it raises and asks the user to re-run the upstream step.

Every callback that round-trips data through `_df_to_json` / `_json_to_df` benefits automatically — no other code touched.

**Caveat.** If the Python process restarts, only the "processed" DataFrame survives (rehydrated from parquet). "migtime", "model_results", etc. live in memory and must be regenerated by re-running their upstream step. In practice that's already how the workflow flows.

### 2026-05-18 — Tab 1 no longer auto-loads the last working directory on page load

`dcc.Store(id="store-workdir", ...)` was created with `storage_type="local"`, which kept the chosen workdir in browser localStorage and silently re-activated it on every page refresh (the `render_workdir_state` callback synced `_ACTIVE_WORKDIR` from the restored store value). Per user request, removed `storage_type="local"` so the store is session-only — a fresh page load now starts with no active workdir. The recents dropdown still works (`recent_workdirs.json` on disk is unchanged), so re-picking is one click.

Only `app/main.py` line \~1723 changed.

### 2026-05-18 — Pre-flight run check: app boots cleanly

Before resuming the Tab 1 lazy-loading work, scanned for anything that would prevent the app from starting on this machine.

- **Syntax**: `py_compile` clean on `app/main.py` and all 7 modules under `app/modules/`.
- **Imports**: `import app.main` succeeds with no Dash callback/Store/ID mismatch errors. Dash app object instantiates; Flask `server` attribute present; `__main__` block + `.run()` present at bottom of `main.py` (\~4519 lines).
- **Dependencies**: all 16 packages from `requirements.txt` import (dash, dash-leaflet, dash-bootstrap-components, flask-caching, plotly, pandas, geopandas, numpy, scipy, shapely, pyproj, fiona, rasterio, scikit-learn, pyarrow, openpyxl).
- **Batch files**: `Setup.bat` and `Start App.bat` both reference the real `C:\Program Files\Python313\python.exe` (not the MS Store stub) — already fixed 2026-05-15.
- **Live boot**: launched `python app/main.py`, server came up on <http://127.0.0.1:8050/> within \~8 s, `GET /` returned HTTP 200. Left running for the lazy-loading session that follows.

**Conclusion.** No blockers. The app runs. Performance in the Data Import & Cleaning tab is the next thing to address.

### 2026-05-16 — Per-project working directory (Browse... → ModelInputs/ModelOutputs/session_log.txt)

**Why.** Up until now, every project's data was crammed into `app/session_data/<project_name>/` (one folder per project, three files). Outputs from Tab 5 went wherever the user typed in the "Output Directory" field. No way to tie raw inputs, processed data, and exports to a single folder per project. Design goal: each project gets its own folder, with inputs / outputs / log all inside.

**What changed.**

- **New "Working Directory" card at the top of Tab 1.** A *Browse...* button pops a native Windows folder-picker dialog. Selected path appears in a read-only text field next to it. Below: a *Recent working directories* dropdown that lists previously chosen folders (capped at 12, dedup'd, drops entries whose folder no longer exists).

- **Folder picker mechanism.** Python's `tkinter.filedialog.askdirectory()` doesn't play nicely with a long-running Flask thread, so the dialog runs in a one-off Python subprocess that prints the chosen path and exits. Implemented in `_pick_directory_native()` in `main.py`.

- **Working directory layout.** When you pick a folder, the app scaffolds:

  ```         
  <workdir>/
  ├── ModelInputs/    <- copies of uploaded CSV/.wld files
  ├── ModelOutputs/   <- processed_data.parquet, road_crossings.json, processing_log.txt, future exports
  └── session_log.txt <- append-only timestamped action log
  ```

- **Session log format.** Plain text, one action per line: `YYYY-MM-DD HH:MM:SS  ACTION  key1=value1 key2=value2`. Easy to grep, version-controllable, no parser required. Current actions logged: `WORKDIR_SET`, `UPLOAD_CSV`, `UPLOAD_WLD`, `PROCESS_DATA`, `EXPORT`.

- **Recents persistence.** Stored at `app/session_data/recent_workdirs.json` so they survive app restarts.

- **Browser persistence.** The active workdir is also kept in `dcc.Store(id="store-workdir", storage_type="local")` so a browser refresh remembers what was set.

- **Routing.**

  - `handle_upload`: still writes a temp file, but if a workdir is set, also copies the original to `ModelInputs/<filename>` and uses that as the processing source.
  - `handle_wld_upload`: same — mirrors `.wld` to `ModelInputs/`.
  - `process_uploaded_data`: writes `processed_data.parquet`, `road_crossings.json`, and `processing_log.txt` to `ModelOutputs/` (in addition to the existing legacy `session_data/` paths, which are kept by design — no forced migration).
  - `handle_export` (Tab 5): if the user leaves the Output Directory field empty AND a workdir is set, defaults to `<workdir>/ModelOutputs/`.

- **Legacy `app/session_data/` is left intact.** Existing projects still loadable via the original "Project" card dropdown. New code path is additive.

**Implementation locations.** - Backend helpers (`_ACTIVE_WORKDIR`, `_set_active_workdir`, `_workdir_inputs/outputs/log`, `_log_action`, `_recent_workdirs`, `_remember_workdir`, `_pick_directory_native`): immediately after `_save_notes` in `main.py`. - UI card: top of the Tab 1 left column, above the existing "Project" card. - Callbacks: in a new "Working directory" callbacks section just before "Project management". - Store: new `dcc.Store(id="store-workdir", storage_type="local")` in the top-level layout.

### 2026-05-16 — Git initialized + initial commit

- Git for Windows 2.54.0 installed at `C:\Users\<username>\AppData\Local\Programs\Git\cmd\git.exe` (per-user install, no admin needed). The user-local install path means `git` isn't on the system PATH until a shell restart; scripts that need git from a hot shell should call the full path or restart.
- Global identity configured for this machine.
- `git init` run at `Colorado Migration Mapping/`. Default branch = `main`. `core.autocrlf=true` (Windows convention) so LF↔CRLF conversion happens transparently.
- **Repo-root scope rationale (user-confirmed).** The repo root is *this* app folder, deliberately **not** the higher-level `MigrationFiles/` / `MigrationAnalyzer/` folders — those hold the ~66 MB merged roads shapefile and the ~3.9 GB SNODAS pickle, which don't belong in plain git. The existing `.gitignore` already covers `session_data/`, `__pycache__/`, `*.pyc`, and `*.zip`, so the initial commit was clean. (Install options considered before settling on Git for Windows: `winget install --id Git.Git -e --source winget`, the git-scm.com installer, or PortableGit.)
- First commit: `848ced2 Initial commit: Colorado Migration Corridor Mapper` — 20 files, 8822 insertions. Working tree clean.
- No remote configured; local-only by design. Adding a GitHub remote later just needs `git remote add origin <url>` + `git push -u origin main`.

### 2026-05-18 — Modeling backend ported from MAPP3.x R workflow

**Why.** The original `modeling.py` had real implementations only for Kernel UD and Line Buffer (and even those didn't match R's behaviour exactly — wrong bandwidth, wrong cutoff). BBMM/CTMM/dBBMM were stubs that all silently fell back to Kernel. The Tab 3 "Run Models" callback was *itself* a placeholder that built a fake results table without actually running anything. The R reference workflow (`WesternCorridorMappingTeam-main/MAPP3.x_code_workflow/`) is the canonical Wyoming Migration Initiative pipeline; goal is to track its behaviour as closely as we reasonably can in pure Python.

**Extraction.** `WesternCorridorMappingTeam-main.zip` extracted into the project root (gitignored). Layout: `MAPP3.x_code_workflow/code2run.R` (entry script) + `MAPP3.x_code_workflow/functions/Calc*.R` (one file per modelling backend + helpers).

**What changed in `app/modules/modeling.py`.**

- `create_population_grid` — now matches `CalcPopGrid.R` exactly: per-dimension `mult4buff` extension (previously used `max(width, height)*mult4buff` for all four sides, which was wrong).
- `calc_kernel_ud` — full rewrite. Uses **Silverman href bandwidth** (`h = sqrt((var(x)+var(y))/2) * n^(-1/6)`), matching `adehabitatHR::kernelUD(kern='bivnorm', h='href')`. Evaluates KDE directly on a subgrid (seq bbox + `mult4buff`), applies R's two-step normalisation (rescale to 1 → drop \< 99.99% tail → rescale again), writes UD (float32) and footprint (uint8) tifs to disk when `ud_dir` / `footprint_dir` are set. Returns `(ud_raster, footprint_polygon, metadata)`. Optional Julian-day subsampling matches R's `slice_sample(n=subsample)` per `yr_jul` group.
- `calc_line_buffer` — sorts by date, builds the linestring through consecutive points (previously took points in whatever order), writes uint8 tif when `footprint_dir` is given. Returns the same 3-tuple shape.
- `calc_bbmm` — real port, replacing the stub. Two modes:
  - **FMV** (`bm_var=<float>`): bridge integration along each segment with σ²(α) = `lag·α(1-α)·BMvar + (1-α)²·locerr² + α²·locerr²`, exactly the formula from R's custom `BrownianBridgeCustom()`. Steps in `time_step_min` (default 5). Time lags computed in minutes between consecutive fixes.
  - **EB** (`bm_var=None`): estimates motion variance via Horne (2007) likelihood — for each interior triplet `(i, i+1, i+2)`, the residual of the middle point from a straight-line interpolation is bivariate-normal with variance `coef·σ² + locerr_terms`. Minimised over σ² with `scipy.optimize.minimize_scalar`.
  - Pre-checks match R: skips with error metadata if `>1/3` of steps exceed `max_lag`, or if `<4` points.
- `calc_dbbmm_stub` — still a stub (no Python equivalent for `move::brownian.bridge.dyn`'s sliding-window change-point detection), but now falls back to **BBMM(EB)** rather than Kernel — closer in spirit.
- `calc_ctmm_stub` — still a stub (no Python equivalent for `ctmm::ctmm.select` over OU-family processes), falls back to Kernel.
- `calc_seq_distances` — new function. Pairwise distance matrix per sequence id, returns max distance (km) per sequence + aggregate (mean/sd/min/max) stats. Direct port of `CalcSeqDistances.R`.
- `run_model` dispatch updated to consume the new 3-tuple return shape and merge per-method metadata (kernel bandwidth, BMvar, runtime, error string) into the canonical metadata dict.

**Tab 3 callback wired up.** `run_modeling` in `main.py` used to be a placeholder. It now: builds a UTM-projected GeoDataFrame, creates the population grid once, extracts per-sequence sub-GeoDataFrames via `extract_sequences` (the existing helper in `sequencing.py`), composes the modelling config (calls `get_model_config` so the `fix_rate_hours > 12 → bm_var=5000` auto-logic still fires), runs `run_all_sequences`, and renders a real results table. If a working directory is set, UDs/Footprints get written to `<workdir>/ModelOutputs/UDs/` and `<workdir>/ModelOutputs/Footprints/` and the model results CSV to `<workdir>/ModelOutputs/model_results.csv`. Logs a `RUN_MODELS` action.

**Honest fidelity caveats.** - Kernel UD: differs from R by O(1e-4) because we evaluate the KDE on cell centres without `SpatialPixels` artifacts. - BBMM(FMV): bit-for-bit identical math to R's `BrownianBridgeCustom`. Should match output to within float32 rounding. - BBMM(EB): the maximum-likelihood variance estimator uses the standard Horne (2007) formulation. R's `BBMM::brownian.motion.variance` uses the same likelihood and `optimize()`; results should track to ≥3 significant digits. - dBBMM/CTMM: still stubs. To get real numbers, install R and run `code2run.R` directly, or wait until those are ported.

**Files touched.** `app/modules/modeling.py` (major refactor), `app/main.py` (`run_modeling` callback rewrite), `.gitignore` (add `WesternCorridorMappingTeam-main/`), `INFORMATION.md` (this entry).

### 2026-05-16 — env_data resolver fix + WLD upload wired into Tab 1

**`raster_sampler.py` and `road_crossings.py` — env_data path now self-heals** - Both modules previously hardcoded `_ENV_DATA = parent.parent.parent / "environment_data"`, which resolved to `Colorado Migration Mapping/environment_data/` — a folder that didn't exist on this machine. The actual DEM tiles, SNODAS pickle, and roads shapefile live two levels up under `MigrationFiles/MigrationAnalyzer/`. So Tab 1's elevation/snow checkboxes silently returned NaN/zeros and Tab 2's road-crossing badges were stuck at "—". - Replaced both constants with a `_resolve_env_data()` helper that tries the canonical location first, then falls back to `MigrationFiles/MigrationAnalyzer/`. Picks whichever location actually contains the expected files. - Verified: both resolvers now return the `MigrationAnalyzer/` parent folder on this machine.

**`.wld` upload wired into Tab 1 as an optional second uploader** - New "MigrationAnalyzer .wld File (optional)" card sits between the raster-variable checklist and the Process Data button. - Variable picker pre-selects `wld_reader.DEFAULT_SELECTED` (the 10 most-useful columns: elevation, temp, snow depth, snow density, EVT, canopy cover, canopy height, BpS, aspect range, habitat quality). - A "Show all 36 variables ▾" toggle expands a collapsible second checklist with the remaining 26 (kernel + extra environment vars), labelled with their group. - On drop, a new `handle_wld_upload` callback parses the WLD header via `read_wld_metadata()` and shows `population (N collars, N fixes)` as a status line. - `process_uploaded_data` now takes three new State inputs (`store-wld-upload-path`, `wld-var-checklist` value, `wld-var-advanced-checklist` value). After the raster sampling block, if a WLD path is set, it calls `read_wld_fast()` + `merge_wld_to_gps()`, attaches new columns to the GeoDataFrame, and appends per-variable status lines to the processing log. - `_precompute_animal_maps()` now also includes any WLD columns present in the data (alongside the 4 raster vars) in the per-animal map cache. - `update_seq_map` builds a combined `{column_name: human_label}` dict (raster defaults + merged WLD vars) and includes it in the `update-data` postMessage payload as `env_labels`.

**`maplibre_map.html` — popup labels are now dynamic** - The popup previously had a hardcoded `LABELS` const for the 4 raster vars. Now `LABELS` is `let` (not `const`) and the `update-data` message handler merges any incoming `env_labels` into it. - The popup loop iterates `feature.properties` (skipping reserved `c`/`d` keys) instead of iterating a fixed key list, so any new variable that flows in gets displayed — labelled from the merged `LABELS` dict, or falling back to the raw column name. - `formatVal()` got a sensible-default branch for unknown keys: picks precision based on magnitude (3 dp for small numbers, 1 dp for large), and stringifies non-numeric values rather than crashing.

**Verification** - `python -m py_compile` clean on `main.py`, `raster_sampler.py`, `road_crossings.py`. - `import app.main` succeeds with no Dash callback ID / Store mismatch errors. - Could not run the Dash app end-to-end from the sandbox; UI behaviour with a real `.wld` upload should be smoke-tested manually.

### 2026-05-16 — Comprehensive INFORMATION.md created (earlier same day)

- Created INFORMATION.md as a parallel companion to INFORMATION.md (kept the original intact). The K file is the comprehensive, plain-English + technical guide; INFORMATION.md remains the terser reference.

### 2026-05-15 — Initial setup on this machine

**Environment discovered** - Only Python installed: `C:\Program Files\Python313\python.exe` (Python 3.13, confirmed via `py --list-paths`). - `C:\Users\<username>\AppData\Local\Microsoft\WindowsApps\python.exe` exists but is the **Microsoft Store stub** — running it just prompts to install from the Store. NOT a real Python. - No `.git` repo at any folder level — project is loose files, no commit history available locally.

**`Setup.bat` and `Start App.bat` — Python path corrected** - Both batch files were hardcoded to the Microsoft Store stub path. Updated both to point to the real install: - `Setup.bat` line 10: `set PYTHON=C:\Program Files\Python313\python.exe` - `Start App.bat` line 7: `"C:\Program Files\Python313\python.exe" app\main.py`

**Dependencies installed** - `pip` upgraded to 26.1.1. - `pip install -r requirements.txt` succeeded for all packages (no conda-forge fallback needed for rasterio/geopandas/fiona on Python 3.13). - Pip warned that script shims landed in `C:\Users\<username>\AppData\Roaming\Python\Python313\Scripts` (not on PATH). Harmless — we invoke Python directly, never the shims.

**Dash app — `seqPointStyle` JS error fixed** - First launch loaded but the browser threw: `No match for [dashExtensions.default.seqPointStyle] in the global window object`. - Cause: `app/assets/map_functions.js.rename_me` was parked with a `.rename_me` suffix, so Dash wasn't serving it. `app/main.py:43-44` references `dashExtensions.default.seqPointStyle` / `seqLineStyle` which that file defines. - Fix: renamed `app/assets/map_functions.js.rename_me` → `app/assets/map_functions.js`. Confirmed Dash now serves it (HTTP 200, 546 bytes at `/assets/map_functions.js`).

------------------------------------------------------------------------

## 7. Module-by-module deep dive

Every module is in `app/modules/` and is plain Python (no Cython, no compiled extensions). All of them can be imported standalone and used from a Jupyter notebook without touching the Dash layer.

### 7.1 `data_ingestion.py` — load + clean + compute movement parameters

**Plain-English.** Takes a raw CSV (or shapefile, or zipped shapefile) of GPS collar fixes and turns it into a clean, standardised dataset with every column biologists need for migration analysis. Roughly: throw away bad GPS fixes, snap to a coordinate system that works in metres, figure out how far the animal walked between each fix and how fast, then compute *Net Squared Displacement* (NSD) which is the workhorse statistic for finding migrations.

**`DEFAULT_CONFIG`** at the top of the file is the canonical list of every tunable parameter and its default value. The UI populates form fields from this dict; any field the user changes flows through `process_data(config=...)` as an override.

**Key constants worth knowing:** - `tmax_seconds = 176_400` (49 h) — the gap that ends a "burst." If a collar misses fixes for \> 49 h, the next fix starts a new burst and movement parameters are NaN at the boundary. - `max_speed_kmh = 10.8` (≈ 3 m/s) — fixes that imply travel faster than this are flagged as problems. 10.8 km/h is the WMI convention; pronghorn can hit \> 50 km/h in sprints, but sustained \> 10.8 over a multi-hour fix interval almost always means a bad GPS fix, not real movement. - `n_ref_points = 20` — NSD reference location = the mean of an animal's first 20 fixes in a year. Using a 20-point average instead of the very first fix smooths out collar noise on day 1. - `bio_year_start_month/day = 2/1` (Feb 1) — biological year boundary. Pronghorn winter-range fidelity makes Feb a natural cutpoint; for elk/deer you might prefer Mar 1 or Apr 1.

**Function map.**

| Function | Plain-English | R-script ancestor |
|----|----|----|
| `detect_and_remap_columns()` | If the CSV looks like a CPW Wildlife Tracker export (has `animalIdLocal`, `mtReadable`, etc.), rename its columns to the MigrationMapper names automatically. Matches ≥ 3 known columns to trigger. | Legacy R prep script `transmute()` block |
| `quality_filter()` | Drop fixes with DOP \> 10, \< 6 satellites, positive longitude (Germany/test points), or NA coords. Returns a log of what got removed. | Legacy R prep script `filter()` block |
| `validate_for_migration_mapper()` | After filtering, double-check the data is sane: required columns exist, no NAs, all longitudes negative, lat/lon in reasonable range, timestamp format parseable, ≥ 100 records. Returns True/False + log. | Legacy R prep script validation block |
| `load_data()` | Read CSV/shp into a GeoDataFrame, rename to standard names (`animal_id`, `timestamp`, `lon`, `lat`, `x`, `y`). If UTM columns aren't present, auto-detect the UTM zone from the median longitude and project. | wmiScripts equivalent: `importShapefile()` |
| `calc_burst()` | Assign integer burst IDs: a new burst begins when the animal changes or `dt > tmax_seconds`. Vectorised with numpy `cumsum` of a boolean. | `wmiScripts/CalcBurst.R` |
| `calc_movement_params()` | Per-step distance (m), dt (s), speed (m/s), absolute bearing (degrees, N=0 clockwise), relative/turning angle (−180…180), fix rate (hours). NaN at burst boundaries. | `wmiScripts/CalcMovParams.R` |
| `calc_nsd()` | NSD (km²) and displacement (km) for a chosen grouping column. NSD = squared metres from reference location, scaled to km²; displacement = √NSD scaled to km. | The three NSD computations in `app1_calculateMovementParams.R` |
| `calc_bio_year()` | Add `bio_year` and `id_bio_year` columns. Fix before bio-year start day → previous bio year. | `app2_timeFunctions.R` `calcBioYearParams()` |
| `flag_problem_points()` | `problem = 1` if speed \> `max_speed_kmh`. | `wmiScripts/FindProblemPts.R` |
| `check_mortality()` | `mortality_flag = 1` for fixes where every subsequent fix in the next `mort_time_hours` is within `mort_distance_m`. O(n²) per animal — slow for very large datasets, fine for typical herd-scale workloads (a few hundred animals, \< 1M fixes). | `wmiScripts/Check4Morts.R` |
| `process_data()` | The full pipeline glue, in the exact order matching the R workflow. Returns `(gdf, config, log)`. | The R `app1_calculateMovementParams.R` main script |

**Processing order (matches R exactly):** 1. Load raw CSV 2. Auto-detect and remap app-download columns 3. Quality filter (DOP, sats, bad coords) 4. Sort by `(animal_id, timestamp)` 5. Validate (logs FAIL/PASS lines) 6. Load again into GeoDataFrame and re-apply quality filter 7. Drop duplicates on `(animal_id, timestamp)` 8. Burst assignment (49 h gap) 9. Movement parameters 10. `year`, `id_yr` 11. Bio year + `id_bio_year` 12. NSD computed 3 times: per `id_yr`, per `animal_id` (overall), per `id_bio_year` 13. Flag problem points 14. Mortality check

**Key formulas:** - **NSD**: `((mean_x_first20 − x)² + (mean_y_first20 − y)²) / 1,000,000` (km²) - **Displacement**: `√((mean_x_first20 − x)² + (mean_y_first20 − y)²) / 1,000` (km) - **Bearing (N=0, CW positive)**: `degrees(atan2(dx, dy)) mod 360` - **Relative angle**: wrap successive-bearing differences into `[−180, 180]` - **Bio year for date `(Y, M, D)`**: `Y − 1 if (M, D) < (start_month, start_day) else Y`

### 7.2 `sequencing.py` — auto-detect migrations from NSD

**Plain-English.** Migratory ungulates spend the winter in one place, the summer in another, and walk between them in spring/fall. Plot NSD (squared distance from where they started) against time and you get a characteristic "hump" — flat (winter range), rising (spring migration), flat at a new high (summer range), falling (fall migration), flat again. This module finds those rising and falling phases automatically.

**Why this matters.** In the R Migration Mapper, you sit with each animal-year, eyeball the NSD plot, and drag two sliders for spring start/end and two more for fall start/end. With 50 animals over 3 years that's 600 slider drags. This module gets the answer right \~70–80 % of the time in five seconds, and you only have to fix the edge cases (residents, partial migrations, dispersals).

**Algorithm (`detect_migrations_nsd`):** 1. Estimate the GPS fix rate (fixes per day). 2. Smooth the NSD curve with a rolling median; window ≈ 7 days of fixes (`max(3, round(7 × fixes_per_day))`, forced to odd). 3. Compute the first derivative (`np.gradient`). 4. Find "sustained" positive-derivative segments → outbound (spring) candidates; sustained negative → return (fall) candidates. A segment must last ≥ 5 days AND change NSD by ≥ 5 % of the year's NSD range. 5. Merge consecutive same-direction segments separated by gaps \< 20 % of the shorter segment. 6. Score each candidate: **0.6 × amplitude + 0.4 × directional consistency**. Amplitude = NSD change / year's NSD range; consistency = fraction of fixes in the segment with the expected sign. 7. Keep the top `max_sequences` (default 4) by score, then re-order chronologically and label `mig1, mig2, …`. 8. **Range-point extension** (when `ensure_range_points=True`): if the detected segment endpoints are \> 5 km from the animal's actual position right before/after the segment, extend by 2 days on each side so the corridor model doesn't miss the "joining" point on the seasonal range.

**Functions:**

| Function | What it does |
|----|----|
| `detect_migrations_nsd()` | The detector above. Returns one row per detected window with `id_bio_year`, `sequence_name`, `start_date`, `end_date`, `migration_type` (outbound/return), `confidence` (0–1). |
| `build_migtime_table()` | Build an empty migtime DataFrame — one row per `id_bio_year`, eight `migN_start`/`migN_end` slots, plus `auto_detected`/`reviewed` booleans and a `notes` field. |
| `apply_auto_detections()` | Fill the migtime table from a detections DataFrame. Sets `auto_detected = True` on any row that received dates. |
| `extract_sequences()` | After review, pull the GPS points that fall within each `migN_start`/`migN_end` window. Returns `{sequence_name: GeoDataFrame}`. Skips problem/mortality fixes if a `flag` column exists. |
| `calc_sequence_distances()` | Total cumulative path length per sequence (sum of step distances). Uses projected `x`/`y` if available, falls back to haversine on `lon`/`lat`. |
| `get_nsd_plot_data()` | Bundle dates, NSD, smoothed NSD, displacement, speed, and shaded migration regions for a single animal-year. Tab 2's review charts consume this. |

**Internal helpers:** - `_rolling_median(arr, window)` — `scipy.signal.medfilt` with `mode='reflect'` padding so the smoothed curve doesn't sag at the edges. - `_find_sustained_segments(...)` — the rise/fall hunter. - `_rle(arr)` — run-length encoder for the binary "is the derivative the right sign?" array. - `_merge_segments(...)` — combines same-direction segments separated by short gaps. - `_haversine_path_km(lats, lons)` — great-circle path distance fallback.

**R lineage (per function).** `detect_migrations_nsd` — NEW, no R equivalent (the R workflow, App 2, defined every sequence by fully manual slider adjustment). `build_migtime_table` — `app2.r buildMigtime()`. `apply_auto_detections` — NEW. `extract_sequences` — `app3_calcSequences.R calculateDefinedSequences()`. `calc_sequence_distances` — `CalcSeqDistances.R`. `get_nsd_plot_data` — `app2_plotting.R`.

### 7.3 `modeling.py` — corridor models (Kernel + BBMM stubs)

**Plain-English.** A "utilisation distribution" (UD) is a probability surface that says "if you dropped this animal randomly into a pixel during this migration, what's the probability it's that pixel?" Sum it across all pixels and you get 1.0. The 50 % isopleth is the smallest area containing 50 % of that probability — i.e., the animal's "core" migration area. We compute one UD per migration sequence, then stack them in the next module.

**What's actually implemented (post-2026-05-18 R port):**

| Method | Status | What it is |
|----|----|----|
| **Kernel UD** | ✅ Native port | Bivariate-normal KDE with **Silverman href bandwidth** (`h = sqrt((var(x)+var(y))/2) * n^(-1/6)` — matches `adehabitatHR::kernelUD(kern='bivnorm', h='href')`). Evaluated on a subgrid (seq bbox + `mult4buff` per dimension). Applies R's two-step normalisation: rescale to 1 → drop \< 99.99% tail → rescale again. Writes UD (float32) + footprint (uint8) tifs if directories provided. |
| **Line Buffer** | ✅ Native port | Sorts by date, builds linestring through consecutive points, buffers by `buff_distance` (default 300 m to match `code2run.R`), rasterises onto the pop grid as uint8. |
| **BBMM (FMV)** | ✅ Native port | Bridge integration along each segment with σ²(α) = `lag·α(1-α)·BMvar + (1-α)²·locerr² + α²·locerr²`. Bit-for-bit identical math to R's custom `BrownianBridgeCustom()`. Set `bm_var` to a float to engage this mode. |
| **BBMM (EB)** | ✅ Native port | Estimated Brownian motion variance via Horne (2007) likelihood: for each interior triplet, the residual of the middle point from straight-line interpolation is bivariate-normal with variance `coef·σ² + locerr_terms`. Minimised with `scipy.optimize.minimize_scalar`. Set `bm_var=None` (the default) to engage this mode. |
| **dBBMM** (dynamic) | ⚠️ Stub → BBMM(EB) | Real dBBMM needs R's `move::brownian.bridge.dyn` for sliding-window change-point detection over motion variance — no Python equivalent. Stub falls back to regular BBMM with estimated variance. |
| **CTMM** (continuous-time) | ⚠️ Stub → Kernel | Real CTMM needs R's `ctmm::ctmm.select` over OU-family stochastic processes. Stub falls back to Kernel UD. |

Future faithful dBBMM/CTMM support would need either an R bridge (`rpy2` or `subprocess Rscript`) or a non-trivial Python port. The stub config dicts preserve the full parameter interface so callers don't change.

**Functions:**

| Function | What it does |
|----|----|
| `create_population_grid(points_gdf, cell_size=500, buffer_mult=0.3)` | Build the empty raster every UD will be projected onto. Bounds = `points_gdf.total_bounds` expanded by `buffer_mult × max(width, height)`. Returns a dict of `{transform, shape, crs, cell_size, bounds}`. Optionally writes a zero-filled GeoTIFF. |
| `calc_kernel_ud(seq_gdf, seq_name, pop_grid, bandwidth=None, contour=99)` | Build a `gaussian_kde` from the sequence's x/y, evaluate it at every grid cell-centre, normalise to sum=1, extract the `contour`% probability polygon. |
| `calc_line_buffer(seq_gdf, seq_name, buff_distance=300, pop_grid=None)` | LineString through fixes → `.buffer()` → optionally rasterise to grid. Returns binary raster + polygon. |
| `calc_bbmm_stub`, `calc_ctmm_stub`, `calc_dbbmm_stub` | Warn + delegate to `calc_kernel_ud`. |
| `get_model_config(method, fix_rate_hours)` | Return a fully-populated config dict for the chosen method. **Auto-logic:** when `fix_rate_hours > 12`, sets `bm_var = 5000` (fixed) instead of `None` (auto-estimate). Coarse fix schedules make BBMM variance estimation unstable; this is a fixed design choice. |
| `run_model(seq_gdf, method, pop_grid, config, seq_name)` | Dispatch table: routes to the right calc function, captures warnings, returns `{ud_raster, footprint_polygon, metadata}`. |
| `_run_model_worker(args)` | Top-level worker for `ProcessPoolExecutor`. Reconstructs a GeoDataFrame from a `__geo_interface__` dict (avoids pickling Fiona file handles). |
| `run_all_sequences(sequences_dict, method, pop_grid, config, n_cores=1)` | Serial or parallel execution over all sequences. Catches per-sequence exceptions and stores `{error: str}` in the metadata so one bad sequence doesn't kill the run. Returns `(results_dict, metadata_gdf)`. |
| `save_ud_raster()` / `save_footprint()` | Write a single UD as float32 GeoTIFF (LZW-compressed) or a footprint to Shapefile/GeoPackage. |

**Internal helpers:** - `_write_raster()` — rasterio writer with `nodata=-9999`, LZW compression. - `_rasterize_polygon()` — `rasterio.features.rasterize` shim. - `_contour_polygon()` — for a given UD raster + percentage, sort cells by density descending, accumulate until cumulative sum ≥ `contour/100`, polygonise the mask with `rasterio.features.shapes`, union the polygons.

**R lineage (per function).** `create_population_grid` — `CalcPopGrid.R`. `calc_kernel_ud` — `CalcKernel.R`. `calc_line_buffer` — `CalcLineBuff.R`. `calc_bbmm_stub` / `calc_ctmm_stub` / `calc_dbbmm_stub` — the R-only `CalcBBMM.R` / `CalcCTMM.R` / `CalcDBBMM.R`. `get_model_config` — NEW (the auto-parameter logic has no R equivalent). `run_model` / `run_all_sequences` — `app4_runUd.R` (the parallel `runUdProcessing()` loop).

### 7.4 `population_outputs.py` — merge individuals into population products

**Plain-English.** One animal's UD shows where *that animal* went. A herd's "population use surface" needs to combine 30 animals into one map. This module does the stacking and contouring.

There are **two output products** that look similar but answer different questions:

- **Population Use** (built from UDs). At each pixel, either "what fraction of individuals had a non-zero UD here?" (*Area* contour type) or "what fraction of total UD volume sits in this pixel?" (*Volume* contour type, computed via cumulative-rank).
- **Population Footprint** (built from buffered polygons). Simpler: rasterise each individual's footprint to the common grid, count overlaps, divide by total individuals. "What fraction of the herd's individual corridor polygons cover this pixel?"

Both products then go through the same contour pipeline: optional Gaussian smoothing → mask at each level → polygonise → drop polygons smaller than `min_area_drop` m² → fill holes smaller than `min_area_fill` m² → return as a GeoDataFrame with `contour`, `geometry`, `area_km2`.

**Merge order matters.** If you have 5 animals × 3 years = 15 UDs, you can either: - `merge_order=['id', 'year']` — first average each animal across years (give each animal equal weight), then stack across animals. - `merge_order=['year', 'id']` — first average each year across animals (give each year equal weight), then stack across years.

The right choice depends on whether you care about over-representation by animals with long collar histories.

**Functions:**

| Function | What it does |
|----|----|
| `calc_population_use(ud_dict, grid_meta, merge_order, contour_type, contour_levels, ...)` | Stack UDs into a proportion grid (Area or Volume mode), contour at each level, clean. Returns `GeoDataFrame[contour, geometry, area_km2]`. |
| `calc_population_footprint(footprint_dict, grid_meta, contour_levels, ...)` | Rasterise each polygon, accumulate, contour at "% of individuals overlapping" levels. |
| `generate_metadata_summary(migtime_df, model_results, config)` | Build the nested-dict summary: `herd_info`, `data_summary`, `migration_timing` (median dates per season), `migration_distance` (mean/median/std), `model_parameters`. |
| `export_shapefiles(gdf, out_path, layer_name)` | Write a GeoDataFrame to `<out_path>/<layer_name>.shp`. |
| `export_geotiff(raster_array, grid_meta, out_path)` | Single-band float32 GeoTIFF with LZW compression and `nodata=-9999`. |
| `export_report(metadata_summary, out_path)` | Plain-text methodology report using `_REPORT_TEMPLATE`. Includes herd info, data summary, median timing, distance stats, model parameters, methodology notes, and an output-files map. |
| `export_all(...)` | The "Export All" button. Writes the Migration Mapper directory structure: `popUseMerged/`, `footPrintsMerged/`, `Metadata/`, `UDs/{season}/*.tif`, `Footprints/{season}/*.shp`. |

**Internal helpers:** - `_contours_from_grid(...)` — the contour-clean pipeline shared by both products. - `_fill_holes(geom, min_fill_area)` — drop interior rings smaller than `min_fill_area`. - `_build_geodataframe(rows, src_crs, out_crs)` — drop None geometries, reproject if needed, compute `area_km2`. For geographic CRSes, area is computed in ESRI:54009 (World Mollweide, equal-area).

**R lineage (per function).** `calc_population_use` — `CalcPopUse.R`. `calc_population_footprint` — `CalcPopFootprint.R`. `generate_metadata_summary` — done manually in R. `export_shapefiles` / `export_geotiff` — the App 5/6 `st_write()` / `terra::writeRaster()` calls. `export_report` — NEW. `export_all` — App 5 output-directory logic.

### 7.5 `raster_sampler.py` — sample environment at each GPS fix

**Plain-English.** "What was the elevation, snow depth, and snow density where this animal was, on the day it was there?" This module answers that for every fix in your dataset.

**Data sources:** - **DEM**: USGS 1/3-arc-second (\~10 m) GeoTIFFs (`USGS_13_*.tif`) covering Colorado in 1° × 1° tiles. - **SNODAS**: Daily 1 km snow product from NOAA NOHRSC, pre-extracted to a Colorado window (lat 36.5–41.5, lon −109.5 to −101.5, 658 × 903 cells) and serialised as a Python pickle for fast load.

**Caching strategy.** `_dem_tiles` and `_snodas_cache` are module-level globals, loaded lazily on first call. The DEM tiles stay open as rasterio dataset handles. The SNODAS pickle is \~3.7 GB; loading it on first sample takes \~30 s and then sampling is in-memory.

**Path resolution.** `_resolve_env_data()` checks two locations and picks whichever actually contains the data: 1. `Colorado Migration Mapping/environment_data/` (the canonical layout — what `.gitignore` already excludes) 2. `MigrationFiles/MigrationAnalyzer/` (where the tiles + pickle actually live in this repo)

So the app works whether the data has been moved into the project folder or stays where MigrationAnalyzer put it.

**Functions:**

| Function | What it does |
|----|----|
| `query_elevation(lat, lon)` | Single-point DEM read; finds the right tile by bounding box, reads a 1×1 window. Returns NaN if no tile covers the point or the cell is nodata. |
| `query_snow(lat, lon, date_str)` | Single-point SNODAS read for a `"YYYYMMDD"` date. Returns dict with `snow_depth_m`, `swe_m`, `snow_density_kgm3`. Density = SWE/depth × 1000 (kg/m³), only if depth \> 1 cm to avoid divide-by-zero. |
| `sample_rasters(df, variables, ...)` | **The batch entry point used by Tab 1.** Takes a DataFrame and a list of variable keys (`elevation_m`, `snow_depth_m`, `swe_m`, `snow_density_kgm3`), samples efficiently, and appends columns. Elevation uses `rasterio.sample()` grouped by tile (fast, batched). SNODAS uses vectorised row/col indexing per unique date. Optional `progress_callback(pct, msg)` for UI feedback. |

`AVAILABLE_VARIABLES` is the canonical dict used to populate the Tab 1 checklist. As of 2026-06-22 it contains only elevation (the three snow variables were removed from the UI — see Setup Log):

``` python
{
    "elevation_m": "DEM Elevation (m)",
}
```

The SNODAS sampling code in `raster_sampler.py` is retained and still callable; restoring snow in the UI is just a matter of re-adding the `snow_depth_m` / `swe_m` / `snow_density_kgm3` entries to this dict. Elevation now defaults to **checked** in the Tab 1 checklist.

### 7.6 `road_crossings.py` — did the animal cross a road?

**Plain-English.** For each animal-year, draw the path and check whether it intersects any TIGER road. Used in Tab 2 to flag animals that crossed highways during a migration window — useful for road-passage / wildlife-crossing planning.

**MTFCC codes** (TIGER Census road classification): - `S1100` — primary road (interstates and other limited-access freeways) → "highway" - `S1200` — secondary road (US/state highways) - `S1400` — local road

By default the module considers `S1100 + S1200` as "roads" and `S1100` alone as "highways" — so the answer to "crosses highway" implies "crosses road" but not vice versa.

**Path resolution.** Same `_resolve_env_data()` pattern as `raster_sampler.py` — tries `Colorado Migration Mapping/environment_data/` first, then `MigrationFiles/MigrationAnalyzer/`.

**Functions:**

| Function | What it does |
|----|----|
| `_load_roads(category)` | Load `all_roads_merged.shp`, filter to the right MTFCC codes, reproject to WGS-84, build a spatial index. Cached per category. |
| `detect_crossings(lon, lat)` | Build a LineString from the coordinate sequence, query the spatial index for intersecting roads, return `{crosses_road: bool, crosses_highway: bool}`. |
| `detect_crossings_batch(df, animal_col='id_bio_year', ...)` | Loop over `groupby(animal_col)` and run `detect_crossings` per animal-year. Returns `{animal_key: {road: bool, highway: bool}}`. Cached to `session_data/<project>/road_crossings.json` so it survives restarts. |

### 7.7 `wld_reader.py` — read MigrationAnalyzer .wld binary files

**Plain-English.** MigrationAnalyzer (a separate companion project) produces `.wld` files — a custom binary format that bundles GPS fixes alongside 36 derived movement-kernel variables (impedance, heat suppression, thermal load, etc.) and environmental snapshots (snow, EVT, BpS, canopy cover, habitat quality). This module parses those files and lets you merge them onto a regular GPS DataFrame.

**File format.** A `.wld` is a ZIP archive containing: - `population.json` — population/species/date-range metadata - `fixes_meta.json` — per-collar metadata (serial → local_id, etc.) - `fixes.bin` — binary blob, format: `b"ELK1"` magic + 4-byte header (n_collars, cols_per_row, total_fixes) + 32-byte per-collar index entries + packed `total × cols` array of `float64`.

**Functions:**

| Function | What it does |
|----|----|
| `WLD_COLUMNS` | The 36-column spec: `{index: (snake_case_name, human_label, group)}`. Three groups: Position & Time, Movement Kernel, Environment. |
| `DEFAULT_SELECTED` | The 10 most-useful columns by default: elevation, temp, snow depth, snow density, EVT, canopy cover, canopy height, BpS, aspect range, habitat quality. |
| `get_variable_options()` | UI checklist helper. |
| `read_wld_metadata()` | Read header + JSON metadata without parsing the blob. Quick. |
| `read_wld()` | Row-by-row parser. Slow on big files; correct. |
| `read_wld_fast()` | Vectorised — reads the entire `float64` block in one go, then attaches per-collar serial/local_id by slicing. **Use this for production.** |
| `merge_wld_to_gps(gps_df, wld_df, max_time_diff_seconds=1800)` | Match `gps[animal_id]` to `wld[wld_serial]` (string contains either way), then per-animal nearest-timestamp join with a 30-min default tolerance. Uses `np.searchsorted` for the lookup. |

**UI integration (as of 2026-05-16).** Tab 1 now has an optional ".wld File" upload card after the raster checklist:

- Drop a `.wld` file → `handle_wld_upload` parses the header and displays `population (N collars, N fixes)`.
- A variable checklist pre-selects `DEFAULT_SELECTED`; a "Show all 36 variables ▾" toggle expands the rest as an "advanced" picker.
- When you click Process Data, the merge happens after the raster sampling step: `read_wld_fast(wld_path, selected_columns=...)` → `merge_wld_to_gps(gdf_flat, wld_df, ...)`. Matched columns get appended to the processed GeoDataFrame and persisted in the per-project Parquet.
- Tab 2's MapLibre popup automatically shows the merged variables (the labels dict travels along with each map-payload `update-data` message; the iframe merges it into its `LABELS` map and iterates whatever properties the feature actually has).

### 7.8 `main.py` — the Dash application

**Plain-English.** This is the part you interact with in the browser. Everything above is logic; this file is the buttons, the tables, the charts, and the wiring that runs the logic when you click something.

**File anatomy** (line numbers approximate):

| Lines | What |
|----|----|
| 1–160 | Imports, `sys.path` shim so module imports work from any launch dir, graceful fallback stubs if any module fails to import (lets the UI still load). |
| 161–235 | App init (CYBORG dark theme), `flask_caching` SimpleCache, per-project disk persistence under `app/session_data/<project>/`. |
| 237–290 | Tiny helpers: `_err_alert`, `_ok_alert`, `_df_to_json` / `_json_to_df` with a server-side cache to avoid re-parsing JSON on every callback, `_make_preview_table`. |
| 297–605 | Tab 1 layout (upload, column mapping, processing params, raster variable checklist, preview pane). |
| 611–834 | Tab 2 layout (bio-year settings, animal navigation, sequence-name inputs, range sliders, three charts, MapLibre iframe map, notes + road-crossing badges). |
| 840–908 | Tab 3 layout (model dropdown, dynamic parameter panel, core slider, run button, results table). |
| 914–1034 | Tab 4 layout (season selection, merge order, contour type/levels, min-area thresholds, smoothing, generate button). |
| 1040–1165 | Tab 5 layout (layer toggles, base layer toggle, export buttons, Leaflet map with three GeoJSON layers). |
| 1171–1201 | Top-level layout: navbar, the 10+ `dcc.Store` components for state, the `dbc.Tabs` container. |
| 1208–1255 | Project management callbacks (refresh project list, load project). |
| 1262–1522 | Tab 1 callbacks (handle upload + preview, process data). |
| 1529–2196 | Tab 2 callbacks: populate animal dropdown, sequence-name inputs, NSD/displacement view toggle, the giant `update_nsd_plots` callback that builds three Plotly figures + range sliders + auto-detection on demand, prev/next navigation, slider→date sync, `_precompute_animal_maps` cache build, `_build_point_geojson`, MapLibre map update + road-crossing badge + notes load, notes save. |
| 2203–2401 | Tab 3 callbacks (model parameter panel that re-renders per method, the run_modeling pipeline). |
| 2407–2497 | Tab 4 callbacks (generate population outputs). |
| 2503–2655 | Tab 5 callbacks (layer toggles + map update, export dispatcher). |
| 2660–2662 | `if __name__ == "__main__": app.run(debug=True, host="127.0.0.1", port=8050)`. |

**State management.** Dash callbacks are stateless between requests. The app uses a layered approach:

1.  **`dcc.Store` components** — JSON-serialised state in the browser (visible to callbacks via `Input`/`State`). Used for the processed data, migtime table, model results, config, current animal index, NSD view mode, slider day-zero anchor, population outputs, upload temp path, animal notes (`storage_type='local'` so they survive a browser refresh), the MapLibre payload, and the road-crossings dict.
2.  **Server-side `_DF_CACHE`** — `{cache_key: DataFrame}` in process memory. `_df_to_json` writes to both the cache and the JSON; `_json_to_df` short-circuits when the key is in cache. Massively faster than re-parsing the JSON on every callback.
3.  **`_MAP_CACHE`** — pre-computed per-animal map arrays (line GeoJSON, raw lon/lat arrays, ISO date strings, env-var arrays). Built once by `_precompute_animal_maps()` right after processing. Tab 2's map update then just builds GeoJSON from arrays — milliseconds.
4.  **Disk persistence** — `_save_processed_to_disk(df, project_name)` writes Parquet to `app/session_data/<project>/processed_data.parquet`. The project dropdown re-populates from the contents of that directory.

**Key UX patterns:** - The Tab 2 "Auto-detect All" button triggers the same callback as animal selection but with `n_clicks` non-None — it's a single big callback that does both jobs. - The range sliders use Dash pattern-matching IDs (`{"type": "seq-range-slider", "index": i}`) so a `dash.MATCH` callback can sync slider → date inputs without one explicit callback per sequence. - Tab 2's right-pane map is a MapLibre GL canvas inside an `<iframe>` (see [Assets](#79-assets--maplibre-html-map_functionsjs-stylecss)), driven by `postMessage` from a clientside callback that reads `store-map-payload`. This decouples the map from the Python round-trip — re-colouring on slider drag is instant. - Tab 5's map uses `dash-leaflet` natively, with `dl.GeoJSON(options=dict(pointToLayer=...))` pointing at the `seqPointStyle` JS function registered via `dash_extensions`.

### 7.9 Assets — MapLibre HTML, map_functions.js, style.css

- **`app/assets/maplibre_map.html`** — full-page MapLibre GL JS map served at `/assets/maplibre_map.html` and embedded as an iframe in Tab 2. Esri World Imagery as the satellite basemap, OpenTopoMap as the alternate, 3D terrain from AWS Terrarium tiles with `exaggeration: 1.5`. Three sources: `terrain-dem`, `animal-line`, `animal-points`. Click handler builds a styled popup with date, lat, lon, and any environmental variables present in the feature properties. Listens for `message` events from the parent Dash app:
  - `{ type: 'update-data', points, line, center, zoom }` — replace the layers and `flyTo`.
  - `{ type: 'set-basemap', basemap: 'topo' | 'esri' }` — swap tile URLs.
- **`app/assets/map_functions.js`** — defines `window.dashExtensions.default.seqPointStyle` (a `L.circleMarker` styled by `feature.properties.c`) and `seqLineStyle` (a thin white dashed line). Used by Tab 5's Leaflet GeoJSON layers. The `|| {}` guard at the top is intentional — see the Pending Items note about the conflicting stub file in the top-level `assets/`.
- **`app/assets/style.css`** — small set of overrides for `rc-slider` (the range sliders) and `dash-dark-dropdown` (forces dropdown menus to render dark).

------------------------------------------------------------------------

## 8. Data dictionary

### 8.1 Input formats

#### Wildlife Tracker app-download CSV (auto-detected)

| Column | Renamed to | Meaning |
|----|----|----|
| `animalIdLocal` | `LoclAID` | Local animal identifier (e.g. `"PH_01_2020"`) |
| `animalTrackerId` | `TrakAID` | Tracker DB serial |
| `species` | `Species` | e.g. `"Pronghorn"` |
| `projectName` | `Project` | Study/herd name |
| `sex` | `Sex` | M/F |
| `captureAgeClass` | `AgeClass` | Calf / Yearling / Adult |
| `mtReadable` | `DT_MST` | `"YYYY-MM-DD HH:MM:SS"` |
| `speedCollar` | `Cllr_Spd` | Reported speed from collar |
| `dop` | `DOP` | Dilution of Precision (lower = better) |
| `numSats` | `NumSats` | Number of GPS satellites |
| `longitude` | `Long` | WGS-84 lon |
| `latitude` | `Lat` | WGS-84 lat |
| `utm_datum_and_zone` | `UTM_D_Z` | Datum + zone string |
| `utmZone` | `UTM_Zn` | UTM zone integer |
| `UTME` | `UTME` | UTM easting (m) |
| `UTMN` | `UTMN` | UTM northing (m) |
| `dau` | `DAU` | Data Analysis Unit (herd management unit) |
| `captureGmu` | `CptrGMU` | Game Management Unit at capture |
| `captureDau` | `CptrDAU` | DAU at capture |

#### Migration Mapper standard shapefile

Already-renamed columns (`LoclAID`, `DT_MST`, `Long`, `Lat`, `UTME`, `UTMN`, `UTM_Zn`, etc.).

### 8.2 Standardised columns after `process_data()`

| Column | Type | Meaning |
|----|----|----|
| `animal_id` | str | Standardised animal identifier |
| `timestamp` | datetime64 | Parsed fix time |
| `lon`, `lat` | float | WGS-84 decimal degrees |
| `x`, `y` | float | UTM easting / northing (m), auto-projected if absent |
| `utm_zone` | int | UTM zone number |
| `burst_id` | int | Burst grouping — new burst when animal changes or gap \> 49 h |
| `dist` | float | Step distance to *this* fix from the previous fix in the same burst (m) |
| `dt` | float | Time since previous fix (s); NaN at burst boundaries |
| `speed` | float | dist / dt (m/s); NaN at burst boundaries |
| `abs_angle` | float | Absolute bearing (degrees, N=0, clockwise) |
| `rel_angle` | float | Relative/turning angle (degrees, −180…180) |
| `fix_rate_hours` | float | dt / 3600 |
| `year` | int | Calendar year |
| `id_yr` | str | `"<animal>_<year>"` |
| `bio_year` | int | Biological year (animal's "annual cycle" anchor year) |
| `id_bio_year` | str | `"<animal>_<bio_year>"` |
| `ref_x_id_yr`, `ref_y_id_yr` | float | Mean of first 20 fixes per calendar year |
| `nsd_id_yr` | float | NSD (km²) per calendar year |
| `displacement_id_yr` | float | Displacement (km) per calendar year |
| `ref_x_animal_id`, `ref_y_animal_id` | float | Mean of first 20 fixes overall |
| `nsd_animal_id` | float | NSD (km²) overall |
| `displacement_animal_id` | float | Displacement (km) overall |
| `ref_x_id_bio_year`, `ref_y_id_bio_year` | float | Mean of first 20 fixes per bio year |
| `nsd_id_bio_year` | float | NSD (km²) per bio year |
| `displacement_id_bio_year` | float | Displacement (km) per bio year |
| `problem` | int | 1 if speed \> `max_speed_kmh` else 0 |
| `mortality_flag` | int | 1 if subsequent fixes within `mort_time_hours` stay within `mort_distance_m` |
| `elevation_m` (optional) | float | DEM elevation at fix (m), if raster sampling enabled |
| `snow_depth_m` (optional) | float | SNODAS snow depth at fix (m) |
| `swe_m` (optional) | float | Snow water equivalent (m) |
| `snow_density_kgm3` (optional) | float | Computed density (kg/m³) |

> Note: `sequencing.py` uses `nsd_bio` / `displacement_bio` as defaults. After `process_data()` the columns are actually named `nsd_id_bio_year` / `displacement_id_bio_year`. The Tab 2 callback in `main.py` handles the rename or sequencing is called with explicit `nsd_col=` / `displacement_col=` arguments. If you call `detect_migrations_nsd` directly from a notebook, pass `nsd_col='nsd_id_bio_year'` and `displacement_col='displacement_id_bio_year'`.

### 8.3 Migtime table

One row per `id_bio_year`. Columns:

- `id_bio_year` (str), `animal_id` (str), `bio_year` (str), `bio_year_full` (str)
- `mig1_start` … `mig8_start` (datetime), `mig1_end` … `mig8_end` (datetime)
- `notes` (str)
- `auto_detected` (bool) — set True when `apply_auto_detections` fills a row
- `reviewed` (bool) — set True when the user clicks Accept in Tab 2

This mirrors the R Migration Mapper `migtime` **SQLite table**; the `auto_detected` and `reviewed` booleans are Python-side additions (the R original had no auto-detection step to flag). The later `seq_cleared` boolean (see the 2026-05-22 and 2026-06-09 log entries) is also a Python addition.

------------------------------------------------------------------------

## 9. Configuration reference

Every parameter exposed in the UI maps to a key the modules accept. Defaults match Wyoming Migration Initiative conventions.

### 9.1 Data ingestion (`DEFAULT_CONFIG` in `data_ingestion.py`)

| Key | Default | Plain-English |
|----|----|----|
| `animal_id_col` | `LoclAID` | Source column for animal ID |
| `timestamp_col` | `DT_MST` | Source column for timestamp |
| `timestamp_format` | `%Y-%m-%d %H:%M:%S` | strptime format |
| `lon_col` / `lat_col` | `Long` / `Lat` | Source lon/lat columns |
| `utme_col` / `utmn_col` / `utm_zone_col` | `UTME` / `UTMN` / `UTM_Zn` | Source UTM cols (optional) |
| `tmax_seconds` | 176400 | Gap (s) that ends a burst (49 h) |
| `n_ref_points` | 20 | NSD reference = mean of first N fixes per group |
| `bio_year_start_month` / `_day` | 2 / 1 | Biological year starts Feb 1 |
| `max_speed_kmh` | 10.8 | Speed above this flags `problem=1` |
| `mort_distance_m` | 50 | Mortality if all subsequent fixes within this distance |
| `mort_time_hours` | 48 | …for this many hours |
| `dop_cutoff` | 10 | Drop fixes with DOP \> this |
| `sat_cutoff` | 6 | Drop fixes with \< this many satellites |

### 9.2 Sequencing (`detect_migrations_nsd`)

| Argument | Default | Meaning |
|----|----|----|
| `id_col` | `animal_id` | Animal identifier column |
| `bio_year_col` | `id_bio_year` | Grouping column for detection |
| `nsd_col` | `nsd_bio` | NSD column — see note in §8.2 about actual column name |
| `date_col` | `timestamp` | Timestamp column |
| `displacement_col` | `displacement_bio` | Displacement column |
| `max_sequences` | 4 | Max candidate windows kept per id_bio_year |
| `ensure_range_points` | True | Extend window endpoints up to 2 days if the animal was still \> 5 km away from its post-window range |

### 9.3 Modeling (`get_model_config`)

| Key | Default | Meaning |
|----|----|----|
| `method` | (required) | `BBMM` / `CTMM` / `DBBMM` / `LINEBUFF` / `KERNEL` |
| `num_cores` | 1 | Worker processes for `run_all_sequences` |
| `max_timeout` | 600 | Seconds per sequence before giving up (advisory) |
| `mult4buff` | 0.3 | Population grid buffer multiplier |
| `cell_size` | 500 | Raster cell size (m) |
| `time_step` | 5 | BBMM/dBBMM bridge step (min) |
| `bm_var` | `None` (auto) or `5000` if fix_rate \> 12h | Brownian motion variance |
| `location_error` | 20 | GPS error (m) |
| `max_lag` | 8 | Max lag between fixes for bridge computation (h) |
| `contour` | 99 | Probability contour for individual footprint (%) |
| `dbbmm_margin` | 3 | dBBMM margin (#fixes) |
| `dbbmm_window` | 11 | dBBMM sliding window (#fixes, odd, \> 2·margin) |
| `info_criteria` | `AIC` | CTMM model-selection criterion |
| `smooth_param` | `None` | Kernel UD bandwidth; `None` = Scott's rule |
| `subsample` | 1 | Take every Nth fix before KDE |
| `buff_distance` | 300 | Line buffer width (m) |

### 9.4 Population outputs (`calc_population_use`, `calc_population_footprint`)

| Key | Default | Meaning |
|----|----|----|
| `merge_order` | `('id', 'year')` | First avg across years per animal, then stack |
| `contour_type` | `Area` | `Area` (presence proportion) or `Volume` (cumulative UD) — use only applies |
| `contour_levels` | `(5,10,15,20,30,40,50,60,70,80,90)` for use; `(5,10,15,20,30)` for footprint | Percent isopleths |
| `min_area_drop` | 20000 m² | Polygons smaller than this are removed |
| `min_area_fill` | 20000 m² | Interior holes smaller than this are filled |
| `simplify` | True | Apply Gaussian smoothing before contouring |
| `smooth_bandwidth` | 2 cells | Gaussian σ |
| `out_crs` | grid CRS | Reproject output |

------------------------------------------------------------------------

## 10. Design decisions & rationale

**Why Dash and not Flask + Leaflet directly?** Dash gives us reactive callbacks, built-in state management via `dcc.Store`, dash-leaflet for maps, and Plotly charts — no hand-rolled JavaScript. The whole app is one Python process; deployment is "run a `.py` file." For a biologist on a laptop that's much better than juggling a Flask app + an HTMX/JS frontend.

**Why stub BBMM/CTMM/dBBMM instead of porting?** Real BBMM/CTMM use specialised maximum-likelihood estimation that would take weeks to faithfully port and would risk subtle numerical differences from the R packages. The stubs preserve the interface so future R-backend integration (rpy2 or subprocess) requires zero callsite changes. Kernel UD is what gets used 90 % of the time anyway.

**Why auto-detect + mandatory review (not "fully automatic" or "fully manual")?** Fully automatic is wrong on edge cases (residents, dispersers, partial migrations). Fully manual is the R workflow's biggest pain point. Auto-detect + review gets the best of both: the easy cases (a clean NSD hump) are handled in seconds; the user only thinks about the hard ones. The confidence score (0–1) also lets users prioritise where to spend review time.

**Why server-side `_DF_CACHE` on top of `dcc.Store`?** `dcc.Store` is JSON-serialised. Round-tripping a 100k-row GeoDataFrame through JSON on every callback was making the UI laggy. The server-side cache is keyed by a small ID; the JSON only carries the ID (and the data the browser actually needs to render). For long-running multi-user deployments this should move to Redis or filesystem with proper key expiry — see [Future Development](#12-future-development-directions).

**Why Parquet for `session_data/processed_data.parquet`?** Preserves dtypes (especially datetimes), much faster than CSV, smaller than JSON, and `pyarrow` is already a transitive dependency.

**Why MapLibre in an iframe (Tab 2) but dash-leaflet (Tab 5)?** The Tab 2 map needs to repaint on slider drag (re-colouring points by which migration window they fall into). Doing that round-trip through Dash callbacks felt sluggish on test datasets, so Tab 2 sends the entire payload through `postMessage` into an iframe and the JS swaps GeoJSON in place. Tab 5 has no slider interactions, so dash-leaflet's pure-Python ergonomics win.

**Why dark theme (CYBORG)?** GIS professionals tend to spend long sessions in dark-themed apps (ArcGIS Pro, QGIS). The CYBORG Bootstrap theme reduces eye strain and matches the satellite basemap.

**Why a per-project `session_data/<project>/` directory?** Biologists work on multiple herds in parallel. The project dropdown is the simplest possible persistence story: one folder per project, three files per project, no database, no migration scripts.

------------------------------------------------------------------------

## 11. Known gotchas & edge cases

- **NSD column names.** `sequencing.py` defaults are `nsd_bio` / `displacement_bio` but `process_data()` outputs `nsd_id_bio_year` / `displacement_id_bio_year`. The Tab 2 callbacks handle this; standalone notebook users must pass explicit `nsd_col=` and `displacement_col=` arguments. Worth aligning in a future cleanup pass.
- **Mortality detection is O(n²) per animal.** Fine for the typical herd-scale workload (≤ 1M fixes). For continent-scale datasets, replace the inner loop with a windowed `groupby` on a resampled time axis.
- **`scikit-learn` is in requirements.txt but unused.** Reserved for future modeling work. Safe to leave; safe to remove.
- **Single-process Dash dev server.** `debug=True` is convenient for development but is single-threaded. For more than a couple of users, deploy behind gunicorn or waitress.
- **`flag` column convention.** `extract_sequences` drops rows where `flag` is `'problem'` or `'mortality'`. But `process_data()` currently writes `problem` and `mortality_flag` as separate integer columns, not a single `flag` string. So in practice the filter is a no-op unless the caller derives a `flag` column first. Worth either (a) constructing `flag` in `process_data` or (b) changing `extract_sequences` to read the booleans directly.
- **`storage_type='local'` notes** live in the browser's localStorage. Switching browsers or clearing site data loses them. The disk-based `animal_notes.json` per project is the authoritative copy.

------------------------------------------------------------------------

## 12. Future development directions

Roughly in order of effort vs. payoff for a "more capable" version of Migration Mapper:

1.  **Explore R backend integration for CTMM/dBBMM** CTMM and dBBMM are very slow right now because they rely on R and WMI's methods for these models. We could update this by relying on python calculations instead. I just don't have the time right now and these models aren't used as much as BBMM for now.
2.  **Multi-user / server deployment.** Replace `_DF_CACHE` with Redis, replace per-process map cache with per-session, add a thin auth layer (Flask-Login or OIDC), and put it behind nginx/gunicorn. The architecture supports this — only the cache and the project dir lookup need to become session-scoped.
3.  **CLI / batch mode.** A `python -m app.batch <input.csv> <output_dir>` that runs the full pipeline without the UI — useful for nightly automated runs across many herds, or for piping into a larger data system.
4.  **Database backend.** Replace `processed_data.parquet` with SQLite/PostGIS so multiple animals can be loaded incrementally and querying by time/geom is fast.
5.  **Auto-detection improvements.** The current detector is amplitude+consistency scored. Adding (a) classification of resident vs. migratory animals before searching, (b) per-population priors on expected migration windows (e.g., "Colorado pronghorn typically migrate Apr 15–Jun 1"), and (c) handling of multi-stop migrations (stopover sites) would close most of the remaining manual-review gap.
6.  **Corridor analytics.** "Pinch point" detection (narrow places in the population use surface that ≥ X % of the herd traverses), road-crossing hotspot detection (Tab 2 already flags per-animal crossings; aggregate up), and bottleneck width analysis.
7.  **Spatial validation outputs.** Permutation-based "is this corridor real?" tests, jackknife stability per animal, sensitivity reports for bandwidth / contour level choices.
8.  **Integration with Wildlife Crossings planning data.** Overlay CDOT planned crossing structures, animal-vehicle collision hotspots from CDOT's CARS database, etc.
9. **Reverse path: export to the R Migration Mapper format.** So results from this app can be opened in the canonical R tool for cross-validation by collaborators who run that workflow.
10. **Language portability of the processing core.** The deliberate separation of data-processing modules from the Dash UI means the `modules/` layer could be re-ported to R, Julia, or JavaScript while keeping the same UI (or vice-versa) — useful if a future deployment target dictates a different processing runtime.
11. **INTEGRATION WITH TRACKER!!** This development is last in this list but first in importance. The end goal is to have a pipeline of Tracker data ==> Migration Analyzer ==> an auto-updating table of DAU's/collared herds modeled vs. not yet modeled along with model type that can be stored somewhere in Tracker or Tracker Tracker... TBD.
