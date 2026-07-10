# ctmm_bridge.R — Called by Python via Rscript to run a real CTMM model.
# Matches CalcCTMM.R from WMI MAPP3.x as closely as possible.
#
# Usage:
#   Rscript ctmm_bridge.R <input_csv> <popgrid_tif> <ud_out_tif> <fp_out_tif> \
#       <info_criteria> <contour> <mult4buff> <max_timeout> <meta_out_json>

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 9) {
  stop("Usage: Rscript ctmm_bridge.R input_csv popgrid_tif ud_out fp_out info_criteria contour mult4buff max_timeout meta_out_json")
}

input_csv      <- args[1]
popgrid_tif    <- args[2]
ud_out_tif     <- args[3]
fp_out_tif     <- args[4]
info_criteria  <- args[5]
contour        <- as.numeric(args[6])
mult4buff      <- as.numeric(args[7])
max_timeout    <- as.numeric(args[8])
meta_out_json  <- args[9]

# Check required packages
required <- c("sf", "terra", "ctmm", "R.utils", "move", "jsonlite")
missing <- required[!required %in% installed.packages()[, 1]]
if (length(missing) > 0) {
  cat(paste0("MISSING_PACKAGES:", paste(missing, collapse = ",")), "\n")
  quit(status = 2)
}

suppressPackageStartupMessages({
  library(sf)
  library(terra)
  library(ctmm)
  library(R.utils)
  library(move)
  library(jsonlite)
})

start_time <- Sys.time()

# Read input data
pts <- read.csv(input_csv, stringsAsFactors = FALSE)
pts$timestamp <- as.POSIXct(pts$timestamp, tz = "UTC")

# Load population grid
grd <- terra::rast(popgrid_tif)

# Build sf object in the grid's CRS
pts_sf <- st_as_sf(pts, coords = c("x_proj", "y_proj"), crs = st_crs(grd))

# Minimum points check
n_locs <- nrow(pts_sf)
jul <- as.numeric(strftime(pts$timestamp, format = "%j", tz = "UTC"))

if (n_locs < 4) {
  meta <- list(
    ctmm_model = NA,
    n_locs = n_locs,
    n_days = length(unique(jul)),
    execution_time_s = as.numeric(difftime(Sys.time(), start_time, units = "secs")),
    error = "Less than 4 points"
  )
  writeLines(toJSON(meta, auto_unbox = TRUE), meta_out_json)
  quit(status = 1)
}

# Prepare subgrid (matching R CalcCTMM: crop pop grid to sequence extent + buffer)
ext2 <- terra::ext(pts_sf)
multipliers <- c(
  (ext2[2] - ext2[1]) * mult4buff,
  (ext2[4] - ext2[3]) * mult4buff
)
ext2 <- terra::extend(ext2, multipliers)
cels <- terra::cells(grd, ext2)
grd2 <- terra::crop(grd, ext2)

# Order by timestamp
pts_sf <- pts_sf[order(pts$timestamp), ]

# Create telemetry object (matching CalcCTMM: move -> as.telemetry)
telem <- move::move(
  x = pts$x_proj,
  y = pts$y_proj,
  time = pts$timestamp,
  proj = sp::CRS(st_crs(grd)$proj4string)
)
telem <- ctmm::as.telemetry(telem)

# Guess initial parameters
GUESS <- ctmm::ctmm.guess(telem, interactive = FALSE)

# Model selection with timeout
FITS <- R.utils::withTimeout({
  try(ctmm::ctmm.select(
    telem,
    CTMM = GUESS,
    IC = info_criteria,
    verbose = TRUE,
    method = "pHREML"
  ), silent = TRUE)
}, envir = environment(), timeout = max_timeout, onTimeout = "warning")

if ("try-error" %in% class(FITS)) {
  meta <- list(
    ctmm_model = NA,
    n_locs = n_locs,
    n_days = length(unique(jul)),
    execution_time_s = as.numeric(difftime(Sys.time(), start_time, units = "secs")),
    error = paste0("ctmm.select failed: ", attr(FITS, "condition")$message)
  )
  writeLines(toJSON(meta, auto_unbox = TRUE), meta_out_json)
  quit(status = 1)
}

# Extract top model
best_fit <- FITS[[1]]
model_name <- summary(best_fit)$name

# Compute occurrence distribution on the population subgrid
rkrig <- R.utils::withTimeout({
  try(ctmm::occurrence(
    telem,
    CTMM = best_fit,
    grid = list(
      list(
        x = terra::crds(grd2)[, 1],
        y = terra::crds(grd2)[, 2]
      ),
      dr = terra::res(grd2),
      align.to.origin = FALSE,
      extent = ctmm::extent(raster::raster(grd2))
    )
  ), silent = TRUE)
}, envir = environment(), timeout = max_timeout, onTimeout = "warning")

if ("try-error" %in% class(rkrig)) {
  meta <- list(
    ctmm_model = model_name,
    n_locs = n_locs,
    n_days = length(unique(jul)),
    execution_time_s = as.numeric(difftime(Sys.time(), start_time, units = "secs")),
    error = paste0("occurrence() failed: ", attr(rkrig, "condition")$message)
  )
  writeLines(toJSON(meta, auto_unbox = TRUE), meta_out_json)
  quit(status = 1)
}

# Extract PDF values
rkrig <- raster::values(raster::raster(rkrig, DF = "PDF", values = TRUE))
rkrig[is.na(rkrig)] <- 0

# 99.99% tail cutoff + renormalize (matches CalcCTMM.R exactly)
rkrig <- rkrig / sum(rkrig)
cutoff <- sort(rkrig, decreasing = TRUE)
vlscsum <- cumsum(cutoff)
cutoff <- cutoff[vlscsum > 0.9999][1]
rkrig[rkrig < cutoff] <- 0
rkrig <- rkrig / sum(rkrig)

# Write UD raster
grd_ud <- grd
grd_ud[cels] <- rkrig
terra::writeRaster(grd_ud, filename = ud_out_tif,
                   filetype = "GTiff", overwrite = TRUE, datatype = "FLT4S")

# Build footprint at the requested contour
cutoff_fp <- sort(rkrig, decreasing = TRUE)
vlscsum_fp <- cumsum(cutoff_fp)
cutoff_fp <- cutoff_fp[vlscsum_fp > (contour / 100)][1]
rkrig_fp <- ifelse(rkrig < cutoff_fp, 0, 1)
grd_fp <- grd
grd_fp[cels] <- rkrig_fp
terra::writeRaster(grd_fp, filename = fp_out_tif,
                   filetype = "GTiff", overwrite = TRUE, datatype = "INT1U")

# Write metadata
meta <- list(
  ctmm_model = model_name,
  n_locs = n_locs,
  n_days = length(unique(jul)),
  grid_size = length(rkrig),
  grid_cell_size = terra::res(grd)[1],
  execution_time_s = as.numeric(difftime(Sys.time(), start_time, units = "secs")),
  error = "None"
)
writeLines(toJSON(meta, auto_unbox = TRUE), meta_out_json)

cat("CTMM_SUCCESS\n")
