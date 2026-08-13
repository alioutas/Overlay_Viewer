"""Core data-handling helpers for the overlay viewer.

Kept separate from app.py (the Shiny wiring) so they can be unit-tested
without spinning up a Shiny session.
"""
import re

import numpy as np
import pandas as pd
import tifffile

import colormaps

# Leading identifier before any unit suffix, e.g. "x [nm]" -> "x", "x_AST [nm]" -> "x_ast".
_COLUMN_TOKEN_RE = re.compile(r"^\s*([A-Za-z_]+)")


def load_image(path):
    """Read a (grayscale) TIFF into a 2D numpy array, taking the first frame/page."""
    arr = tifffile.imread(path)
    if arr.ndim == 3:
        # Multi-frame stack: use the first frame. Drop a trailing RGB(A) channel axis instead.
        if arr.shape[-1] in (3, 4):
            arr = arr[..., :3].mean(axis=-1)
        else:
            arr = arr[0]
    return arr.astype(np.float64)


def to_display_uint8(arr, low_pct=1.0, high_pct=99.5):
    """Contrast-stretch an arbitrary-range image array to uint8 for display only."""
    lo, hi = np.percentile(arr, [low_pct, high_pct])
    if hi <= lo:
        hi = lo + 1.0
    scaled = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    return (scaled * 255).astype(np.uint8)


def find_xyz_columns(columns):
    """Map 'x'/'y'/'z' to the first matching column name, ignoring unit suffixes like '[nm]'."""
    mapping = {}
    for col in columns:
        m = _COLUMN_TOKEN_RE.match(str(col))
        if not m:
            continue
        key = m.group(1).strip().lower()
        if key in ("x", "y", "z") and key not in mapping:
            mapping[key] = col
    return mapping


def load_localizations(path):
    """Read a localization CSV and return (dataframe with plain 'x'/'y'[/'z'] columns in nm, is_3d)."""
    df = pd.read_csv(path)
    cols = find_xyz_columns(df.columns)
    if "x" not in cols or "y" not in cols:
        raise ValueError("Could not find x/y columns in the localization file.")
    out = pd.DataFrame({"x": df[cols["x"]].to_numpy(dtype=np.float64),
                         "y": df[cols["y"]].to_numpy(dtype=np.float64)})
    is_3d = "z" in cols
    if is_3d:
        out["z"] = df[cols["z"]].to_numpy(dtype=np.float64)
    return out, is_3d


def colorize_by_depth(z, cmap="turbo", alpha=0.7):
    """Map a z array to RGBA colors (0..1 floats) for depth-coded point coloring."""
    zmin, zmax = z.min(), z.max()
    span = zmax - zmin if zmax > zmin else 1.0
    rgb = colormaps.sample(cmap, (z - zmin) / span)
    colors = np.empty((len(rgb), 4), dtype=np.float64)
    colors[:, :3] = rgb
    colors[:, 3] = alpha
    return colors


def colormap_css_gradient(cmap, n_stops=12):
    """CSS linear-gradient string for a colormap, low value at 0% and high at 100%."""
    rgb = colormaps.sample(cmap, np.linspace(0, 1, n_stops))
    stops = [f"rgb({round(r * 255)},{round(g * 255)},{round(b * 255)})" for r, g, b in rgb]
    return "linear-gradient(to top, " + ", ".join(stops) + ")"
