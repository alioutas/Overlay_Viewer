Link to webapp: https://alioutas-overlay-viewer.share.connect.posit.cloud/

# Overlay Viewer

A minimal Shiny (Python) app for overlaying single-molecule localization microscopy point clouds on a reference image, rendered live in 3D in the browser.

> The same source runs either as a normal Shiny server app *or* fully in the
> browser via WebAssembly, with no Python server at all. See
> [Shinylive build](#shinylive-build) below.

## Features

- Upload a `.tif` image and a `.csv` localization table (2D or 3D)
- Adjustable pixel size (nm/px) to align localizations to the image
- Interactive 3D rendering (Three.js) — orbit, pan, zoom
- Depth-based colormaps or flat colors, with a z-depth legend
- Adjustable point size, opacity, and an optional scale bar
- Dark, glassmorphic UI with a resizable toolbar

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

## Run

```bash
shiny run app/app.py
```

Then open the URL Shiny prints (typically `http://localhost:8000`).

## Shinylive build

Build a static, serverless site — no Python on the server, and uploaded data never
leaves the browser:

```bash
pip install shinylive
shinylive export app _site
python -m http.server --directory _site 8008
```

Then open `http://localhost:8008`. The output in `_site/` is plain static files, so it
can be hosted on GitHub Pages or any static host.

Two things to know:

- It **must** be served over `http(s)` (localhost is fine). Shinylive routes requests
  through a service worker, which browsers refuse to register from a `file://` page —
  opening `_site/index.html` directly will not work.
- First visit downloads the Python runtime (~30–45 MB, mostly Pyodide + numpy +
  pandas). It is cached afterwards, so subsequent loads are fast.

### What makes the same code work in both modes

| Change | Why |
|---|---|
| Theme is an unmodified `ui.Theme("shiny")` preset | Customizing it invokes libsass, a C extension that cannot be installed in Pyodide. An untouched preset uses precompiled CSS. The look is reproduced in the app's own stylesheet. |
| No matplotlib — colormaps are embedded in `colormaps.py` | matplotlib was used only for colormap lookups and costs ~11.5 MB of download |
| Minified `three.module.min.js` | Halves the largest asset (1.21 MB → 655 KB) |
| Asset paths are relative, not root-absolute | An exported site is served from a subpath, so `/vendor/...` would escape the app's base |
| App lives in `app/`, data and dev scripts do not | `shinylive export` bundles *every* file under the app directory into a single `app.json`; keeping sample data out avoids shipping megabytes to every visitor |
| `tifffile` pinned in `app/requirements.txt` | Newer releases require `numpy>=2.1`, but the Shinylive runtime ships numpy 2.0.2 |

Note that without tifffile's optional `imagecodecs` extra (a C extension, unavailable
in Pyodide), TIFF reading is limited to uncompressed / zlib-style files.

## Project structure

```
app/
  app.py            Shiny UI and server logic
  imaging.py        Image/localization loading and processing
  colormaps.py      Generated colormap tables (replaces matplotlib)
  requirements.txt  Extra packages for the Shinylive build only
  www/              Static assets (Three.js, fonts, viewer.js, point sprite)

gen_colormaps.py       Regenerates app/colormaps.py (needs matplotlib)
make_synthetic_data.py Regenerates the synthetic sample data (needs matplotlib, scipy)
requirements.txt       Dependencies for local/server use
```

`Synthetic_CoordTable_3D_ASTIGMATISM.csv` and `Synthetic_Snapshot_ROI-T.tif` are
synthetic sample files (512×512 image, ~41k localizations) for testing the app. They
sit outside `app/` so they are not bundled into the Shinylive build.
