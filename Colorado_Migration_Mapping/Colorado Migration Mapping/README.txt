Colorado Migration Corridor Mapper
===================================

A desktop web-app for mapping wildlife migration corridors from GPS
collar data. Drop in a CSV of fixes, auto-detect migrations, draw
corridors, and export shapefiles / GeoTIFFs — all in a browser tab
on your own machine. No cloud, no account.


Which One Do I Run?
-------------------

  Never installed this before ......  Setup.bat    (see A below)
  Already have it installed .......   Update.bat   (see B below)

You can run this folder from anywhere — Downloads is fine. Update.bat
finds your existing install and copies the new code into it.


A. First-Time Install
---------------------

1. DOWNLOAD THE EXTERNAL DATA

   The environmental reference files (elevation DEMs, SNODAS snow
   data, and road layers — ~19 GB zipped) are too large to include
   here. Download them from the Dropbox link you were given:

       Ext_FilesForMigrationAnalyzer.zip

   Place the zip file in THIS folder (next to Setup.bat).

2. RUN SETUP

   Double-click  Setup.bat

   This will:
     - Extract the environmental data (~10-20 min)
     - Install pip into the bundled Python
     - Install required Python packages
     - Create a desktop shortcut

   Internet connection required for the pip install step.

3. LAUNCH THE APP

   Double-click the elk icon, "Migration Corridor Mapper", on your
   Desktop
   — or —
   Double-click  Start App.bat  in this folder

   The app opens in your default browser at http://127.0.0.1:8050


B. Updating an Existing Install
-------------------------------

1. Close the app if it is running.

2. Double-click  Update.bat

   It will:
     - Find your current install (via your desktop shortcut, or it
       will ask you for the folder)
     - Show you what it is about to do and wait for you to confirm
     - Back up your current app/ folder to _backup_<date>/
     - Copy in the new code

3. Launch as usual. Nothing else to do.

   You do NOT need to re-download the 19 GB data, and you do NOT
   need to re-run Setup.bat.

Your environment_data/ folder and your saved sessions in
app/session_data/ are never touched by an update. Once the new
version looks good, you can delete the _backup_<date>/ folder.


What's in This Folder
---------------------

  Setup.bat             First-time setup
  Update.bat            Update an install you already have
  Start App.bat         Launches the app
  README.txt            This file
  requirements.txt      Python package list
  app/                  Application source code
  python-3.13/          Bundled Python interpreter (no install needed)
  environment_data/     Environmental data (created by Setup)


Notes
-----

- After setup you can delete Ext_FilesForMigrationAnalyzer.zip to
  reclaim ~19 GB. The extracted environment_data/ folder is all the
  app needs.

- The app works without the environmental data — elevation, snow
  depth, and road-crossing features just won't be available.

- If you move your install folder, re-run Setup.bat to fix the
  desktop shortcut. Everything else is portable (all paths are
  relative).

- Questions? Contact Bryan Leavelle (bryanleavelle@gmail.com).
