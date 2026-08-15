import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image
from shiny import App, reactive, render, ui

import imaging

_WWW_DIR = Path(__file__).parent / "www"
# Cache-buster: browsers hold onto viewer.js aggressively, so a stale copy
# silently survives edits. Keying the URL to the file mtime avoids that.
_VIEWER_JS = f"viewer.js?v={int((_WWW_DIR / 'viewer.js').stat().st_mtime)}"

COLORMAP_CHOICES = {
    "turbo": "Turbo",
    "viridis": "Viridis",
    "plasma": "Plasma",
    "inferno": "Inferno",
    "magma": "Magma",
    "jet": "Jet",
    "rainbow": "Rainbow",
    "coolwarm": "Coolwarm",
}
FLAT_COLORS = {
    "magenta": (1.0, 0.0, 1.0),
    "green": (0.0, 1.0, 0.0),
    "cyan": (0.0, 1.0, 1.0),
    "yellow": (1.0, 1.0, 0.0),
}
FLAT_COLOR_CHOICES = {name: name.capitalize() for name in FLAT_COLORS}

# Largest value the "Sphere size" slider allows.
MAX_POINT_SIZE = 20.0
# How far below the lowest localization the image plane is placed, in world
# units (= image pixels, since positions are divided by the pixel size) - NOT
# nanometres; at 97 nm/px this is ~485 nm.
#
# Three.js point size is a world-space diameter, so this clears the radius of a
# size-10 sphere. Tuned by eye rather than to the slider maximum: full clearance
# for the largest sphere (10) held the plane far enough back that it read as a
# separate floating layer when the view was tilted. The trade-off is that sphere
# sizes above 10 will begin to intersect the plane again; the default size is 5.
#
# Deliberately a constant rather than a function of the live sphere size: making
# the plane depend on the current size would force a full scene rebuild on every
# drag of the size slider, which is what the lightweight point_size_update path
# exists to avoid.
IMAGE_CLEARANCE_PX = 5.0

FAVICON_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E"
    "%3Cstop offset='0' stop-color='%23F0C808'/%3E%3Cstop offset='1' stop-color='%2322d3ee'/%3E"
    "%3C/linearGradient%3E%3C/defs%3E%3Crect width='32' height='32' rx='8' fill='url(%23g)'/%3E%3C/svg%3E"
)

# A dark, glassmorphic theme (deep charcoal base, gold->cyan accent gradient,
# self-hosted Inter) layered on Shiny's modern "shiny" preset rather than
# plain Bootstrap, since it starts from softer corners/shadows already.
theme = (
    ui.Theme("shiny")
    .add_defaults(
        body_bg="#05060a",
        body_color="#eef0f4",
        primary="#F0C808",
        secondary="#22d3ee",
        border_radius="0.85rem",
        font_family_base="'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
        input_bg="rgba(255,255,255,0.05)",
        input_color="#eef0f4",
        input_border_color="rgba(255,255,255,0.14)",
    )
)

app_ui = ui.page_fluid(
    ui.tags.link(rel="icon", href=FAVICON_SVG),
    ui.tags.style("""
        @font-face { font-family:'Inter'; font-weight:400; font-style:normal; font-display:swap; src:url('/fonts/inter-400.woff2') format('woff2'); }
        @font-face { font-family:'Inter'; font-weight:500; font-style:normal; font-display:swap; src:url('/fonts/inter-500.woff2') format('woff2'); }
        @font-face { font-family:'Inter'; font-weight:600; font-style:normal; font-display:swap; src:url('/fonts/inter-600.woff2') format('woff2'); }
        @font-face { font-family:'Inter'; font-weight:700; font-style:normal; font-display:swap; src:url('/fonts/inter-700.woff2') format('woff2'); }
        @font-face { font-family:'JetBrains Mono'; font-weight:400; font-style:normal; font-display:swap; src:url('/fonts/jetbrains-mono-400.woff2') format('woff2'); }
        @font-face { font-family:'JetBrains Mono'; font-weight:500; font-style:normal; font-display:swap; src:url('/fonts/jetbrains-mono-500.woff2') format('woff2'); }

        :root {
            --accent-1: #F0C808;
            --accent-1-rgb: 240, 200, 8;
            --accent-2: #7bd1a8;
            --panel-bg: rgba(20, 21, 24, 0.86);
            --panel-border: rgba(255, 255, 255, 0.08);
            --hairline: rgba(255, 255, 255, 0.07);
            --text-primary: rgba(255, 255, 255, 0.94);
            --text-label: rgba(255, 255, 255, 0.72);
            --text-muted: rgba(255, 255, 255, 0.42);
            --text-section: rgba(255, 255, 255, 0.38);
            --field-bg: rgba(255, 255, 255, 0.04);
            --field-border: rgba(255, 255, 255, 0.10);
            --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
        }

        html, body {
            height: 100%; margin: 0; padding: 0; overflow: hidden;
            background: #0b0c0e;
            font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
            color: var(--text-primary);
        }

        #viewer-canvas { position: absolute; inset: 0; }
        #viewer-canvas canvas { display: block; }

        /* ---------- side panel ---------- */
        .sidepanel {
            position: fixed; top: 20px; left: 20px; bottom: 20px; width: 308px; z-index: 10;
            display: flex; flex-direction: column;
            background: var(--panel-bg);
            backdrop-filter: blur(20px) saturate(1.1);
            -webkit-backdrop-filter: blur(20px) saturate(1.1);
            border: 1px solid var(--panel-border);
            border-radius: 16px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
            overflow: hidden;
            font-size: 13px;
        }
        body.panel-collapsed .sidepanel { display: none; }

        .rail-btn {
            position: fixed; top: 20px; left: 20px; z-index: 11;
            width: 44px; height: 44px; border-radius: 11px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: rgba(22, 23, 26, 0.82);
            backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
            display: none; align-items: center; justify-content: center; cursor: pointer;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
        }
        body.panel-collapsed .rail-btn { display: flex; }
        .rail-btn > span {
            width: 16px; height: 16px; border-radius: 5px;
            background: linear-gradient(135deg, var(--accent-1), var(--accent-2));
        }

        .panel-header {
            display: flex; align-items: flex-start; gap: 11px;
            padding: 18px 16px 16px; border-bottom: 1px solid var(--hairline);
        }
        .brand-mark {
            width: 26px; height: 26px; border-radius: 8px; flex: none; margin-top: 1px;
            background: linear-gradient(135deg, var(--accent-1), var(--accent-2));
        }
        .brand-text { flex: 1; min-width: 0; }
        .brand-title { font-weight: 600; font-size: 1.115em; color: var(--text-primary); }
        #status {
            margin-top: 4px; font-family: var(--mono); font-weight: 400;
            font-size: 0.885em; line-height: 1.5; color: var(--text-muted);
            white-space: pre-line;
        }
        .icon-btn {
            flex: none; width: 26px; height: 26px; border-radius: 7px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: rgba(255, 255, 255, 0.04);
            color: rgba(255, 255, 255, 0.6);
            cursor: pointer; font: 14px system-ui; line-height: 1;
            display: flex; align-items: center; justify-content: center;
        }
        .icon-btn:hover { background: rgba(255, 255, 255, 0.1); }

        .panel-body {
            flex: 1; overflow-y: auto; padding: 16px;
            display: flex; flex-direction: column; gap: 20px;
        }
        .panel-body::-webkit-scrollbar { width: 8px; }
        .panel-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 4px; }

        .panel-section { display: flex; flex-direction: column; gap: 11px; }
        .section-title {
            font-weight: 600; font-size: 0.808em; letter-spacing: 0.08em;
            text-transform: uppercase; color: var(--text-section);
        }
        .section-head { display: flex; align-items: center; justify-content: space-between; }
        .hairline { height: 1px; background: var(--hairline); }
        .field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

        /* View buttons (XY / + / -) grouped in the Display header */
        .view-btns {
            display: flex; gap: 1px; border-radius: 8px; overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.1); background: rgba(255, 255, 255, 0.1);
        }
        .view-btns button {
            height: 26px; border: none; background: rgba(255, 255, 255, 0.04);
            color: rgba(255, 255, 255, 0.72); cursor: pointer; padding: 0 8px;
        }
        .view-btns button:hover { background: rgba(255, 255, 255, 0.12); }
        #btn-reset-view { font-family: var(--mono); font-weight: 600; font-size: 0.77em; letter-spacing: 0.02em; }
        #btn-font-inc, #btn-font-dec { font: 500 14px system-ui; min-width: 26px; }

        /* ---------- Shiny input restyling ---------- */
        .sidepanel .shiny-input-container { margin-bottom: 0; width: 100% !important; }
        .sidepanel label, .sidepanel .control-label {
            font-weight: 500; font-size: 0.923em; color: var(--text-label); margin-bottom: 6px;
        }
        .sidepanel .form-control, .sidepanel select.form-select {
            height: 36px; border-radius: 9px;
            background: var(--field-bg) !important;
            border: 1px solid var(--field-border) !important;
            color: rgba(255, 255, 255, 0.9) !important;
            font-family: var(--mono); font-weight: 500; font-size: 0.96em !important;
            padding: 0 10px;
        }
        .sidepanel select.form-select { font-family: 'Inter', sans-serif; }
        .sidepanel .form-control:focus, .sidepanel select.form-select:focus {
            border-color: rgba(var(--accent-1-rgb), 0.5) !important;
            box-shadow: 0 0 0 3px rgba(var(--accent-1-rgb), 0.15) !important;
        }

        /* File inputs: collapse Shiny's button+textbox group into one dashed field */
        .sidepanel .input-group {
            border: 1px dashed rgba(255, 255, 255, 0.18); border-radius: 9px;
            background: rgba(255, 255, 255, 0.03); overflow: hidden; height: 38px; flex-wrap: nowrap;
        }
        .sidepanel .input-group .btn-file {
            background: transparent !important; border: none !important;
            color: rgba(255, 255, 255, 0.55) !important;
            font-weight: 500; font-size: 0.96em; padding: 0 12px; height: 36px;
            display: flex; align-items: center;
        }
        .sidepanel .input-group .form-control {
            border: none !important; background: transparent !important; height: 36px;
            font-family: 'Inter', sans-serif; font-size: 0.9em;
            color: rgba(255, 255, 255, 0.75) !important; padding-left: 0; min-width: 0;
        }
        .sidepanel .input-group .form-control:focus { box-shadow: none !important; }
        .sidepanel .progress { display: none; }

        /* Toggles */
        .sidepanel .form-check.form-switch {
            margin: 0; padding: 0; display: flex; align-items: center;
            justify-content: space-between; width: 100%;
        }
        .sidepanel .form-check.form-switch .form-check-input {
            margin: 0; flex: none; width: 36px; height: 20px; cursor: pointer;
            background-color: rgba(255, 255, 255, 0.14); border-color: transparent;
        }
        .sidepanel .form-check-input:checked {
            background-color: var(--accent-1) !important; border-color: var(--accent-1) !important;
        }
        .sidepanel .form-check-input:focus {
            border-color: transparent; box-shadow: 0 0 0 3px rgba(var(--accent-1-rgb), 0.2);
        }
        .sidepanel .form-check-label { order: -1; margin: 0; cursor: pointer; }

        /* Sliders */
        .sidepanel .irs--shiny { font-size: 1em !important; }
        .sidepanel .irs--shiny .irs-line { background: rgba(255, 255, 255, 0.14); border-radius: 2px; top: 27px; height: 4px; }
        .sidepanel .irs--shiny .irs-bar { background: var(--accent-1) !important; top: 27px; height: 4px; }
        .sidepanel .irs--shiny .irs-handle {
            width: 16px; height: 16px; top: 21px; border: 2px solid #17181b; background: var(--accent-1);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
        }
        .sidepanel .irs--shiny .irs-single {
            background: var(--accent-1) !important; color: #0b0c0e !important;
            font-family: var(--mono); font-weight: 600; font-size: 0.92em;
            border-radius: 6px; padding: 2px 8px;
        }
        .sidepanel .irs--shiny .irs-single:before { display: none; }
        .sidepanel .irs--shiny .irs-min, .sidepanel .irs--shiny .irs-max {
            background: transparent; color: rgba(255, 255, 255, 0.32);
            font-family: var(--mono); font-size: 0.807em; visibility: visible !important;
        }

        /* Buttons */
        .sidepanel .btn-default, .sidepanel .btn-secondary, .sidepanel .action-button {
            background: rgba(255, 255, 255, 0.06) !important;
            border: 1px solid var(--field-border) !important;
            color: var(--text-label) !important;
            border-radius: 8px !important; font-size: 0.9em; white-space: nowrap;
        }
        .sidepanel .action-button:hover { background: rgba(255, 255, 255, 0.12) !important; }

        .align-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 4px; }
        .align-grid .shiny-input-container { width: 100% !important; }
        .align-grid .action-button { grid-column: 1 / -1; }
    """),
    ui.tags.script(
        ui.HTML('{"imports": {"three": "/vendor/three.module.js"}}'),
        type="importmap",
    ),
    ui.tags.button(ui.tags.span(), id="panel-expand", class_="rail-btn",
                   title="Expand panel", type="button"),
    ui.tags.aside(
        ui.div(
            ui.div(class_="brand-mark"),
            ui.div(
                ui.div("Overlay Viewer", class_="brand-title"),
                ui.output_text("status"),
                class_="brand-text",
            ),
            ui.tags.button("‹", id="btn-collapse", class_="icon-btn",
                           title="Collapse panel", type="button"),
            class_="panel-header",
        ),
        ui.div(
            # --- Data -------------------------------------------------------
            ui.tags.section(
                ui.div("Data", class_="section-title"),
                ui.input_file("image_file", "Image (.tif)", accept=[".tif", ".tiff"]),
                ui.input_file("loc_file", "Localizations (.csv)", accept=[".csv"]),
                ui.input_switch("show_image_adjust", "Align image", value=False),
                ui.panel_conditional(
                    "input.show_image_adjust",
                    ui.div(
                        ui.input_numeric("image_scale", "Scale", value=1, min=0.01, step=0.05),
                        ui.input_numeric("image_dx", "X (nm)", value=0, step=100),
                        ui.input_numeric("image_dy", "Y (nm)", value=0, step=100),
                        ui.input_action_button("fit_image", "Fit to data"),
                        class_="align-grid",
                    ),
                ),
                class_="panel-section",
            ),
            ui.div(class_="hairline"),
            # --- Display ----------------------------------------------------
            ui.tags.section(
                ui.div(
                    ui.div("Display", class_="section-title"),
                    ui.div(
                        ui.tags.button("XY", id="btn-reset-view", title="Reset to XY view", type="button"),
                        ui.tags.button("+", id="btn-font-inc", title="Increase panel text size", type="button"),
                        ui.tags.button("−", id="btn-font-dec", title="Decrease panel text size", type="button"),
                        class_="view-btns",
                    ),
                    class_="section-head",
                ),
                ui.div(
                    ui.input_numeric("pixel_size", "Pixel size (nm/px)", value=97, min=0.1, step=0.1),
                    ui.input_select("colormap", "Color", choices=FLAT_COLOR_CHOICES, selected="magenta"),
                    class_="field-grid",
                ),
                class_="panel-section",
            ),
            ui.div(class_="hairline"),
            # --- Overlay style ----------------------------------------------
            ui.tags.section(
                ui.div("Overlay style", class_="section-title"),
                ui.input_slider("point_size", "Sphere size", min=1, max=MAX_POINT_SIZE, value=5, step=0.5),
                ui.input_slider("point_opacity", "Opacity", min=0.1, max=1, value=0.9, step=0.1),
                ui.input_switch("show_scale_bar", "Scale bar", value=False),
                ui.panel_conditional(
                    "input.show_scale_bar",
                    ui.input_numeric("scale_bar_um", "Size (µm)", value=5, min=1, step=1),
                ),
                class_="panel-section",
            ),
            class_="panel-body",
        ),
        class_="sidepanel",
    ),
    ui.div(id="viewer-canvas"),
    ui.tags.script(src=_VIEWER_JS, type="module"),
    title="Overlay Viewer",
    theme=theme,
)


def _encode_image_png(image_uint8):
    rgb = np.stack([image_uint8] * 3, axis=-1)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _encode_f32(arr):
    return base64.b64encode(np.ascontiguousarray(arr, dtype=np.float32).tobytes()).decode("ascii")


def _compute_point_colors(df, is_3d, color_choice):
    """Colors never depend on pixel_size (colorize_by_depth's min/max normalization
    is scale-invariant), so this only needs df/is_3d/color_choice."""
    if is_3d:
        if color_choice in FLAT_COLORS:
            return np.tile(FLAT_COLORS[color_choice], (len(df), 1))
        cmap_name = color_choice if color_choice in COLORMAP_CHOICES else "turbo"
        return imaging.colorize_by_depth(df["z"].to_numpy(), cmap=cmap_name)[:, :3]
    color_name = color_choice if color_choice in FLAT_COLORS else "magenta"
    return np.tile(FLAT_COLORS[color_name], (len(df), 1))


def server(input, output, session):

    @reactive.calc
    def image_arr():
        f = input.image_file()
        if not f:
            return None
        try:
            return imaging.load_image(f[0]["datapath"])
        except Exception as e:
            ui.notification_show(f"Could not read image: {e}", type="error", duration=8)
            return None

    @reactive.calc
    def loc_data():
        f = input.loc_file()
        if not f:
            return None, False
        try:
            return imaging.load_localizations(f[0]["datapath"])
        except Exception as e:
            ui.notification_show(f"Could not read localizations: {e}", type="error", duration=8)
            return None, False

    @reactive.effect
    def _update_colormap_choices():
        _, is_3d = loc_data()
        if is_3d:
            ui.update_select("colormap", choices=COLORMAP_CHOICES, selected=next(iter(COLORMAP_CHOICES)))
        else:
            ui.update_select("colormap", choices=FLAT_COLOR_CHOICES, selected="magenta")

    @render.text
    def status():
        parts = []
        img = image_arr()
        pixel_size = input.pixel_size() or 97.0
        scale = input.image_scale() or 1.0
        if img is not None:
            w_um = img.shape[1] * pixel_size * scale / 1000.0
            h_um = img.shape[0] * pixel_size * scale / 1000.0
            parts.append(f"image {img.shape[1]}×{img.shape[0]} px = {w_um:.1f}×{h_um:.1f} µm")
        df, is_3d = loc_data()
        if df is not None:
            # Shown next to the image extent so a scale mismatch is obvious:
            # if these two spans disagree, the overlay cannot line up.
            dx_um = (df["x"].max() - df["x"].min()) / 1000.0
            dy_um = (df["y"].max() - df["y"].min()) / 1000.0
            parts.append(
                f"{len(df):,} locs ({'3D' if is_3d else '2D'}) span {dx_um:.1f}×{dy_um:.1f} µm"
            )
        return "\n".join(parts)

    @reactive.effect
    async def _push_scene_update():
        img = image_arr()
        df, is_3d = loc_data()
        pixel_size = input.pixel_size() or 97.0
        # Isolated: colormap changes alone shouldn't trigger a full geometry/texture
        # rebuild (and the camera refit that comes with it) - _push_point_colors
        # handles those with a lightweight in-place update instead. This effect
        # only needs *a* valid starting color for the initial geometry attribute.
        with reactive.isolate():
            color_choice = input.colormap()

        msg = {"image": None, "points": None}
        # 2D data sits at z = 0, so the plane drops by the full clearance.
        image_z_px = -IMAGE_CLEARANCE_PX

        if df is not None and len(df):
            x_px = df["x"].to_numpy() / pixel_size
            y_px = -df["y"].to_numpy() / pixel_size
            z_px = df["z"].to_numpy() / pixel_size if is_3d else np.zeros(len(df))
            colors = _compute_point_colors(df, is_3d, color_choice)
            if is_3d:
                image_z_px = float(df["z"].to_numpy().min()) / pixel_size - IMAGE_CLEARANCE_PX
            positions = np.column_stack([x_px, y_px, z_px])
            msg["points"] = {
                "positions_b64": _encode_f32(positions),
                "colors_b64": _encode_f32(colors),
                "count": int(len(df)),
            }

        if img is not None:
            img_u8 = imaging.to_display_uint8(img)
            msg["image"] = {
                "b64png": _encode_image_png(img_u8),
                "width": int(img.shape[1]),
                "height": int(img.shape[0]),
                "z": image_z_px,
            }

        await session.send_custom_message("scene_update", msg)

    @reactive.effect
    async def _push_image_transform():
        # Independent of _push_scene_update so nudging the image does not rebuild
        # the geometry or re-upload the texture - it just moves the existing plane.
        pixel_size = input.pixel_size() or 97.0
        await session.send_custom_message("image_transform_update", {
            "scale": input.image_scale() or 1.0,
            "dx_px": (input.image_dx() or 0.0) / pixel_size,
            "dy_px": (input.image_dy() or 0.0) / pixel_size,
        })

    @reactive.effect
    @reactive.event(input.fit_image)
    def _fit_image_to_data():
        """Scale/offset the image so its extent matches the localization bounding box."""
        img = image_arr()
        df, _ = loc_data()
        if img is None or df is None or not len(df):
            ui.notification_show("Load both an image and localizations first.", type="warning")
            return
        pixel_size = input.pixel_size() or 97.0
        # Image spans width*pixel_size nm at scale 1; pick the scale that makes it
        # cover the data's larger dimension, so aspect ratio is never distorted.
        span_x, span_y = float(df["x"].max() - df["x"].min()), float(df["y"].max() - df["y"].min())
        img_w_nm, img_h_nm = img.shape[1] * pixel_size, img.shape[0] * pixel_size
        scale = max(span_x / img_w_nm, span_y / img_h_nm)
        ui.update_numeric("image_scale", value=round(scale, 4))
        ui.update_numeric("image_dx", value=round(float(df["x"].min()), 1))
        ui.update_numeric("image_dy", value=round(float(df["y"].min()), 1))

    @reactive.effect
    async def _push_point_colors():
        # Runs independently of _push_scene_update so picking a new colormap
        # only re-colors the existing points in place, no rebuild/camera reset.
        df, is_3d = loc_data()
        color_choice = input.colormap()
        if df is None or not len(df):
            return
        colors = _compute_point_colors(df, is_3d, color_choice)
        await session.send_custom_message("point_colors_update", {"colors_b64": _encode_f32(colors)})

    @reactive.effect
    async def _push_legend():
        # Only meaningful when Z is present and a continuous colormap (not a
        # flat color) is actually driving the point colors.
        df, is_3d = loc_data()
        color_choice = input.colormap()
        if df is not None and len(df) and is_3d and color_choice not in FLAT_COLORS:
            z_nm = df["z"].to_numpy()
            cmap_name = color_choice if color_choice in COLORMAP_CHOICES else "turbo"
            await session.send_custom_message("legend_update", {
                "show": True,
                "min": float(z_nm.min()),
                "max": float(z_nm.max()),
                "gradient": imaging.colormap_css_gradient(cmap_name),
            })
        else:
            await session.send_custom_message("legend_update", {"show": False})

    @reactive.effect
    async def _push_point_size():
        await session.send_custom_message("point_size_update", {"size": input.point_size() or 5.0})

    @reactive.effect
    async def _push_point_opacity():
        opacity = input.point_opacity()
        await session.send_custom_message("point_opacity_update", {"opacity": 0.9 if opacity is None else opacity})

    @reactive.effect
    async def _push_scale_bar():
        show = bool(input.show_scale_bar())
        # Coerced to a whole number: the input's step/min only constrain the
        # spinner arrows, a typed-in decimal still arrives as a float.
        length_um = max(1, round(input.scale_bar_um() or 5))
        pixel_size = input.pixel_size() or 97.0
        length_world = (length_um * 1000.0) / pixel_size  # um -> nm -> world/pixel units
        label = f"{length_um} µm"
        await session.send_custom_message("scale_bar_update", {
            "show": show,
            "length_world": length_world,
            "label": label,
        })


app = App(app_ui, server, static_assets=_WWW_DIR)

if __name__ == "__main__":
    app.run()
