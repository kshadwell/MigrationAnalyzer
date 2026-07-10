# dbbmm_bridge.R — Called by Python via Rscript to run a dynamic BBMM.
# Matches CalcDBBMM.R from WMI MAPP3.x as closely as possible.
#
# Usage:
#   Rscript dbbmm_bridge.R <input_csv> <popgrid_tif> <ud_out_tif> <fp_out_tif> \
#       <location_error> <max_lag> <contour> <dbbmm_margin> <dbbmm_window> \
#       <mult4buff> <max_timeout> <meta_out_json>

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 12) {
  stop("Usage: Rscript dbbmm_bridge.R input_csv popgrid_tif ud_out fp_out location_error max_lag contour dbbmm_margin dbbmm_window mult4buff max_timeout meta_out_json")
}

input_csv      <- args[1]
popgrid_tif    <- args[2]
ud_out_tif     <- args[3]
fp_out_tif     <- args[4]
location_error <- as.numeric(args[5])
max_lag        <- as.numeric(args[6])
contour        <- as.numeric(args[7])
dbbmm_margin   <- as.integer(args[8])
dbbmm_window   <- as.integer(args[9])
mult4buff      <- as.numeric(args[10])
max_timeout    <- as.numeric(args[11])
meta_out_json  <- args[12]

# Check required packages
required <- c("sf", "terra", "move", "R.utils", "jsonlite")
missing <- required[!required %in% installed.packages()[, 1]]
if (length(missing) > 0) {
  cat(paste0("MISSING_PACKAGES:", paste(missing, collapse = ",")), "\n")
  quit(status = 2)
}

suppressPackageStartupMessages({
  library(sf)
  library(terra)
  library(move)
  library(R.utils)
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

n_locs <- nrow(pts_sf)
jul <- as.numeric(strftime(pts$timestamp, format = "%j", tz = "UTC"))

# Minimum points check
if (n_locs < 4) {
  meta <- list(
    dbb_mean_motion_variance = NA,
    n_locs = n_locs,
    n_days = length(unique(jul)),
    execution_time_s = as.numeric(difftime(Sys.time(), start_time, units = "secs")),
    error = "Less than 4 points"
  )
  writeLines(toJSON(meta, auto_unbox = TRUE), meta_out_json)
  quit(status = 1)
}

# Prepare subgrid (matching CalcDBBMM: crop pop grid to sequence extent + buffer)
ext2 <- terra::ext(pts_sf)
multipliers <- c(
  (ext2[2] - ext2[1]) * mult4buff,
  (ext2[4] - ext2[3]) * mult4buff
)
ext2 <- terra::extend(ext2, multipliers)
cels <- terra::cells(grd, ext2)
grd2 <- terra::crop(grd, ext2)

# Order by timestamp
pts <- pts[order(pts$timestamp), ]

# Compute connectivity (max.lag check)
dt_hours <- c(as.numeric(diff(as.numeric(pts$timestamp))), 0) / 3600
connect <- ifelse(dt_hours > max_lag, "no", "yes")

# >1/3 max-lag bail (matches CalcDBBMM.R)
if (mean(dt_hours[1:(n_locs - 1)] > max_lag) > 0.33) {
  meta <- list(
    dbb_mean_motion_variance = NA,
    n_locs = n_locs,
    n_days = length(unique(jul)),
    execution_time_s = as.numeric(difftime(Sys.time(), start_time, units = "secs")),
    error = "More than 1/3 of steps exceed max.lag"
  )
  writeLines(toJSON(meta, auto_unbox = TRUE), meta_out_json)
  quit(status = 1)
}

# Create move object and burst by connectivity
mov <- move::move(
  x = pts$x_proj,
  y = pts$y_proj,
  time = pts$timestamp,
  animal = "seq",
  proj = sp::CRS(st_crs(grd)$proj4string)
)
mov <- move::burst(mov, connect[1:(n_locs - 1)])

# Run dynamic Brownian Bridge with timeout
bb <- R.utils::withTimeout({
  try(move::brownian.bridge.dyn(
    mov,
    location.error = location_error,
    raster = raster::raster(grd2),
    margin = dbbmm_margin,
    window.size = dbbmm_window,
    burstType = "yes"
  ), silent = TRUE)
}, envir = environment(), timeout = max_timeout, onTimeout = "warning")

if ("try-error" %in% class(bb)) {
  meta <- list(
    dbb_mean_motion_variance = NA,
    n_locs = n_locs,
    n_days = length(unique(jul)),
    execution_time_s = as.numeric(difftime(Sys.time(), start_time, units = "secs")),
    error = paste0("brownian.bridge.dyn failed: ", attr(bb, "condition")$message)
  )
  writeLines(toJSON(meta, auto_unbox = TRUE), meta_out_json)
  quit(status = 1)
}

# Extract mean motion variance
mean_motion_var <- mean(na.omit(bb@DBMvar@means))

# Collapse multi-layer result (matches CalcDBBMM.R)
if (length(bb@layers) > 1) {
  bb <- sum(bb)
} else {
  bb <- bb[[1]]
}
bb <- terra::rast(bb)

# 99.99% tail cutoff + renormalize (matches CalcDBBMM.R exactly)
mxx <- terra::global(bb, "sum")[1, 1]
bb <- terra::app(bb, function(xxy) { xxy / mxx })

cutoff <- sort(terra::values(bb, mat = FALSE), decreasing = TRUE)
vlscsum <- cumsum(cutoff)
cutoff <- cutoff[vlscsum > 0.9999][1]
bb[bb < cutoff] <- 0

mxx <- terra::global(bb, "sum")[1, 1]
bb <- terra::app(bb, function(xxy) { xxy / mxx })

# Write UD raster
grd[cels] <- terra::values(bb, mat = FALSE)
terra::writeRaster(grd, filename = ud_out_tif,
                   filetype = "GTiff", overwrite = TRUE, datatype = "FLT4S")

# Build footprint at the requested contour
grd <- terra::rast(ud_out_tif)
cutoff_fp <- sort(terra::values(grd, mat = FALSE), decreasing = TRUE)
vlscsum_fp <- cumsum(cutoff_fp)
cutoff_fp <- cutoff_fp[vlscsum_fp > (contour / 100)][1]
grd <- terra::classify(grd, rcl = matrix(c(-Inf, cutoff_fp, 0,
                                            cutoff_fp, Inf, 1),
                                          ncol = 3, byrow = TRUE))
terra::writeRaster(grd, filename = fp_out_tif,
                   filetype = "GTiff", overwrite = TRUE, datatype = "INT1U")

# Write metadata
meta <- list(
  dbb_mean_motion_variance = mean_motion_var,
  n_locs = n_locs,
  n_days = length(unique(jul)),
  grid_size = terra::ncell(bb),
  grid_cell_size = terra::res(bb)[1],
  execution_time_s = as.numeric(difftime(Sys.time(), start_time, units = "secs")),
  error = "None"
)
writeLines(toJSON(meta, auto_unbox = TRUE), meta_out_json)

cat("DBBMM_SUCCESS\n")
