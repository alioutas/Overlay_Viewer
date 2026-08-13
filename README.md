Link to webapp: https://alioutas-overlay-viewer.share.connect.posit.cloud/

# Overlay Viewer

A minimal Shiny (Python) app for overlaying single-molecule localization microscopy point clouds on a reference image, rendered live in 3D in the browser.

## Features

- Upload a `.tif` image and a `.csv` localization table (2D or 3D)
- Adjustable pixel size (nm/px) to align localizations to the image
- Interactive 3D rendering (Three.js) — orbit, pan, zoom
- Depth-based colormaps or flat colors
- Adjustable point size, opacity, and an optional scale bar
- Dark, glassmorphic UI with a resizable toolbar

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

## Run

```bash
shiny run app.py
```

Then open the URL Shiny prints (typically `http://localhost:8000`).

## Project structure

```
app.py          Shiny UI and server logic
imaging.py      Image/localization loading and processing
www/            Static assets (Three.js, fonts, viewer.js, point sprite)
```

`CoordTable_SAFE360_3D_ASTIGMATISM.csv` and `Snap_Snapshot#14_ROI-T.tif` are sample files for testing the app.
