# Colorado Migration Corridor Mapper — User Guide

This guide walks you through every step of using the Migration Corridor Mapper, from first-time setup to exporting your final corridor maps.

---

## First-Time Setup

### Step 1: Run Setup.bat

Double-click **Setup.bat** in the app folder. A black terminal window will open and display progress through four steps:

1. **Environmental data** — If you placed Ext\_FilesForMigrationAnalyzer.zip in the app folder, Setup will extract it (\~19 GB, takes 10–20 minutes). If you don't have the zip file, the app will still work but environmental sampling (elevation, snow depth) won't be available. You can always re-run Setup later after adding the zip.  
2. **Python check** — Confirms the bundled Python is present. You don't need to install Python yourself.  
3. **Package install** — Installs required Python libraries. You'll see package names scrolling by — this is normal.  
4. **Desktop shortcut** — Creates a "Migration Corridor Mapper" shortcut on your Desktop with the elk icon.

When you see **"Setup complete\!"** at the bottom, setup is finished. Press any key to close the window.

You only need to run Setup.bat once per computer. After that, use the desktop shortcut or Start App.bat to launch the app.

---

## Launching the App

### Step 2: Start the App

Double-click the **Migration Corridor Mapper** shortcut on your Desktop, or double-click **Start App.bat** in the app folder.

A terminal window will open showing "Starting Colorado Migration Corridor Mapper..." — leave this window open. After a few seconds your web browser will automatically open to the app. The app runs locally on your computer; no internet connection or VPN is needed (except for map tiles).

**Important:** Don't close the black terminal window while you're using the app — that's the server. When you're done, just close the terminal and the browser tab.

---

## Using the App

The app has five tabs that you work through from left to right. Each tab builds on the previous one.

### Tab 1: Data Import & Cleaning

This is where you load your GPS collar data and set processing parameters.

1. **Set your Working Directory** — Click "Browse" and choose or create a folder for this project. The app will create ModelInputs/ and ModelOutputs/ subfolders here to store your data.  
2. **Load or Upload Data** — The app accepts **.csv** files or **zipped shapefiles** (.zip containing .shp, .shx, .dbf, .prj). Either:  
   * Place your file in the ModelInputs/ subfolder and select it from the dropdown, or  
   * Drag and drop the file directly into the upload area.  
3. If you upload a zipped shapefile, the app will extract it and read the attribute table the same way it reads a CSV. Use whichever format your GPS data is already in.  
4. **Map Your Columns** — The app will auto-detect common column names. Verify that the dropdowns are set correctly:  
   * **Animal ID** — the column identifying individual animals (often TrakAID in Tracker downloads)  
   * **Timestamp** — the date/time column for each GPS fix  
   * **Longitude / Latitude** — your coordinate columns  
   * If your data is in UTM rather than lat/lon, check the UTM box and map the easting/northing columns.  
5. **Set Processing Parameters** — Review the filtering thresholds. Hover over the ⓘ icons next to each parameter for a description and recommended values:  
   * **DOP threshold** — filters out low-accuracy GPS fixes. Look into the specific collar vendor's recommended DOP thresholds.  
   * **Minimum satellites** — minimum satellite count to keep a fix. Look into the specific collar vendor's recommended minimum satellites.  
   * **Mortality filter** — flags collars that stopped moving  
   * **Speed filter** — removes fixes that imply unrealistic travel speeds  
   * **Mig-year start** — the month/day your migration year begins (e.g., February 1 for deer, February 15 for elk)  
6. **Environmental Variables (optional)** — Toggle on elevation and if you installed the environmental data during setup. You can also enable road crossing detection if you would like your data to flag when an animal crosses a road or highway.  
7. **Process Data** — Click the blue "Process Data" button. The right side of the screen will show progress, then display a summary of your cleaned dataset and a preview table. Problem points (flagged by the filters) are noted but kept available — you can review and unflag them in Tab 2\. Once you see the green bar at the top of the screen telling you that the data has been successfully processed, move on to tab 2\. After you process the data for the first time, if you have defined a project name, then in later sessions you can quickly reload the same project without going through the steps above.

---

### Tab 2: Migration Sequencing

This tab helps you identify and label migration sequences for each animal-year.

1. **Select an Animal-Year** — The app automatically separates animal-years based on the bio-start date set in tab 1, but you can change the start date on this tab as well. The app will automatically show the first animal-year in the dataset.   
2. **Review the NSD Chart** — The main chart shows Net Squared Displacement over time. Migration events appear as rising or falling ramps in the NSD curve. Use the sub-tabs to also view Displacement and Speed charts for additional context. On the left tab, set the number of migrations you would like to identify, and rename the migrations (e.g., from mig1/mig2/mig3/mig4 to Spring/Summer/Fall/Winter).  
3. **Adjust Manually** — Use the sliders at the top to set migration dates:  
   * On the map in the right, the points that have been included in sequences should light up with the corresponding sequence color. Generally, when identifying migrations, you would want to include at least one point from the starting range in the beginning of the sequence and at least one point in the ending range at the end of the sequence.  
   * You can adjust the size of the sequences card to view multiple sequences at once, and adjust the size of the map box using the grabber at the bottom right corner.  
   * Add comments for each animal-year in the Notes box. You can automatically add comments in the notes box using the Migratory/Resident/Nomadic/Insufficient Data buttons in this box. Animal-years marked Resident, Nomadic, or Insufficient Data are excluded from the analysis (removed from the migtime table on export and documented in AnimalYearsRemoved.csv).  
4. **Migtime Table** — The table at the bottom summarizes all sequences across all animals. You can:  
   * **Export** the table to save your work \- this is usually the best option. It creates an updated migtime table using your sequence dates and notes while still keeping older migtimes tables.  
   * **Load** a previously exported table to resume where you left off

Review each animal-year before moving to Tab 3\. The quality of your corridor maps depends on accurate sequence boundaries.

---

### Tab 3: Modeling

This tab runs movement models on each migration sequence to generate utilization distributions (UDs).

1. **Choose a Model** — Select from the dropdown:  
   * **Kernel UD** — simple kernel density; fast, always available  
   * **BBMM** (Brownian Bridge Movement Model) — RECOMMENDED. Accounts for movement between fixes; good general choice  
   * **dBBMM** (dynamic BBMM) — adapts to changing movement behavior; requires R  
   * **CTMM** (Continuous-Time Movement Model) — statistically rigorous; requires R  
2. **Set Parameters** — The parameter panel updates based on your model choice. The app may auto-adjust some settings based on your data's fix rate (shown in the "Auto Logic" note).  
   * Note that as it currently stands, the BBMM (Brownian bridge movement model) is the most robust and built-out model. Other model types will be built out in the future.  
   * Here are the parameters that are often used for the BBMM:  
     1. Fixed motion variance: 1000 for deer/bighorn, 1400 for elk.  
     2. Conditional FMV by fix-rate threshold: ON  
     3. Hrs between points: 3 for elk, 5 for deer  
     4. Location error: 20 m  
     5. Max lag: 27 hours  
     6. Time step: 5 min  
     7. Contour: 99%  
     8. Grid buffer: 0.2  
3. **CPU Cores** — Adjust the slider to control how many cores to use. More cores \= faster, but leaves fewer resources for other work on your computer.  
4. **Run Models** — Click "Run Models" after choosing which outputs you would like to see (e.g., per-year summaries, per-individual UDs). A progress bar will show completion across all sequences. Results appear in the table on the right. Each row shows one sequence and whether the model ran successfully. Once you see the green bar at the top of the page telling you that the models ran, move on to tab 4\.

Models that require R (dBBMM, CTMM) will automatically fall back to their non-R equivalents if R or required R packages aren't installed.

---

### Tab 4: Population Outputs

This tab combines individual UDs into population-level corridor maps.

1. **Select Seasons** — Check which seasons to include (e.g., Spring, Fall). These correspond to the sequence labels you assigned in Tab 2\.  
2. **Set Merge Order** — Choose whether to merge across years per animal first, or across animals per year first. This affects how individual variation is weighted. It's generally recommended to us ID, then Year.  
3. **Contour Settings** —  
   * **Contour type** — "Area" (proportion of individuals overlapping) or "Volume" (cumulative UD volume). Area is generally more common.  
   * **Contour levels** — Comma-separated percentages (e.g., 5, 10, 20, 50). Lower numbers \= broader corridors; higher numbers \= core-use bottlenecks. The app will also automatically calculate min2 and min3 animals using areas, so once you run the population outputs, you may see additional contour levels, like 1.345%.  
4. **Cleanup** — Set minimum polygon size to drop (removes tiny fragments) and minimum hole size to fill. This is usually 10000 dropped, 5000 filled. Other common drop/fill levels are 20000 dropped, 20000 filled, or 0 dropped, 0 filled.  
5. **Generate** — Click "Generate Population Outputs." Once you see the summary pop up, move on to tab 5 to view your outputs.

---

### Tab 5: Map & Export

This tab lets you visualize everything on an interactive map and export your results.

1. **Layer Controls** — Toggle visibility of:  
   * Raw GPS points (colored by sequence)  
   * Movement tracks  
   * Individual footprints (per-sequence UDs)  
   * Population corridor contours  
2. **Base Map** — Switch between OpenStreetMap and Esri satellite imagery.  
3. **Raster & Vector Overlays** — Load and overlay any raster (.tif) or vector (.shp, .geojson) files from your ModelOutputs folder. Use the opacity slider and choose symbology (black and white or viridis) to blend layers.  
4. **Export** — The export panel lists all population outputs generated in Tab 4\. Select the ones you want and click "Export Selected" (or "Export All", or "Export Recommended for Bios" which only exports the high-level population outputs with metadata). Files are written to your working directory's ModelOutputs/ folder as shapefiles and GeoJSON.

---

## Loading a Previous Session

If you've already processed data and want to pick up where you left off:

1. Launch the app (Step 2 above).  
2. On **Tab 1**, look for the **Project** card on the left side.  
3. Select your saved project from the dropdown, then scroll down to "Process Data". The app will reload your processed data, and you can jump to any tab, like tab 5 to view the previously created outputs from this project. If you want to rerun a certain part of the workflow with different parameters, the new outputs will be placed into a V2\_\[Date\] folder and will document the parameters used in this version. The version folders can stand alone, which means if you prefer the V2 outputs to V1, it's safe to delete the V1 folder.

---

## Updating the App \- This process may be changed soon.

When you receive a new version of the app:

1. Double-click **Update.bat** in the **new** folder (not your existing install).  
2. It will find your current install automatically (via the desktop shortcut) and copy the updated files over.  
3. Your environmental data and saved sessions are preserved — only the app code is replaced.  
4. A backup of your previous version is saved in a \_backup\_ folder inside your install directory.

---

## Troubleshooting

| Problem | Solution |
| ----- | ----- |
| **Setup.bat says "Python not found"** | Make sure the python-3.13 folder exists next to Setup.bat. Re-download the app if it's missing. |
| **Browser doesn't open after starting** | Wait up to 60 seconds. If you see a timeout error in the terminal, check the server window for error messages. |
| **Environmental sampling is grayed out** | You need to run Setup.bat with Ext\_FilesForMigrationAnalyzer.zip in the app folder. |
| **dBBMM/CTMM falls back to simpler model** | R or required R packages aren't installed. The fallback model still produces valid results. |
| **"App is already running"** | The app is already open in another browser tab. The terminal message will open a new tab to it. |
| **App feels slow with many animals** | Reduce CPU cores on Tab 3 if your machine is struggling, or process fewer animal-years at a time. |

---

## Other Resources

This app is primarily a Python translation of the Wyoming Migration Initiative's [Migration Mapper](https://migrationinitiative.org/projects/migration-mapper/). It was created by Keana Shadwell with lots of help and ideas from Bryan Leavelle and Michelle Cowardin, with many others at Colorado Parks & Wildlife contributing to testing, design, and development.

Below are some extra ungulate migration modeling resources if you're interested:

- [USGS Western Migrations](https://apps.usgs.gov/western-migrations/)
- Gelzer et al. 2025, [How sampling design of GPS collar deployment influences consistency of mapped migration corridors over time](https://doi.org/10.1002/jwmg.70009)
- Beaupre et al. 2025, [Sample size guidelines for mapping migration corridors and population distributions using tracking data](https://doi.org/10.1002/2688-8319.70073)
- Horne et al. 2007, [Analyzing animal movement using Brownian bridges](https://doi.org/10.1890/06-0957.1)
- McKee et al. 2024, [Estimating ungulate migration corridors from sparse movement data](https://doi.org/10.1002/ecs2.4983)
- Paterson et al. 2023, [Hidden Markov movement models reveal diverse seasonal movement patterns in two North American ungulates](https://doi.org/10.1002/ece3.10282)
- John et al. 2024, [Pursuit and escape drive fine-scale movement variation during migration in a temperate alpine ungulate](https://doi.org/10.1038/s41598-024-65948-8)
- Nuñez et al. 2022, [A statistical framework for modelling migration corridors](https://doi.org/10.1111/2041-210X.13969)
- Kauffman et al. 2026, [Ungulate Migrations of the Western United States, Volume 6](https://doi.org/10.3133/sir20265123)

*This list should be updated over time.*
