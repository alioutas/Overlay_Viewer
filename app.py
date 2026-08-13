import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image
from shiny import App, reactive, render, ui

import imaging

_WWW_DIR = Path(__file__).parent / "www"

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

        :root {
            --accent-1: #F0C808;
            --accent-1-rgb: 240, 200, 8;
            --accent-2: #22d3ee;
            --surface-glass: rgba(18, 20, 28, 0.55);
            --border-subtle: rgba(255, 255, 255, 0.09);
            --text-primary: #eef0f4;
            --text-muted: #9aa1b1;
        }

        html, body {
            height: 100%; margin: 0; padding: 0; overflow: hidden;
            background: #05060a;
            font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
            color: var(--text-primary);
        }

        #viewer-canvas { position: absolute; inset: 0; }
        #viewer-canvas canvas { display: block; }

        .topbar {
            position: fixed; top: 16px; left: 16px; right: 16px; z-index: 10;
            display: flex; align-items: center; gap: 22px; flex-wrap: wrap;
            padding: 12px 22px;
            background: var(--surface-glass);
            backdrop-filter: blur(18px) saturate(160%);
            -webkit-backdrop-filter: blur(18px) saturate(160%);
            border: 1px solid var(--border-subtle);
            border-radius: 18px;
            box-shadow:
                0 12px 40px rgba(0, 0, 0, 0.55),
                inset 0 1px 0 rgba(255, 255, 255, 0.05),
                0 -1px 24px rgba(var(--accent-1-rgb), 0.10),
                0 4px 30px rgba(34, 211, 238, 0.08);
            font-size: 13px;
        }

        .brand-block { display: flex; flex-direction: column; gap: 4px; }
        .brand { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 1.08em; letter-spacing: 0.2px; }
        .brand-mark { width: 20px; height: 20px; border-radius: 6px; flex: 0 0 auto;
            background: linear-gradient(135deg, var(--accent-1), var(--accent-2)); }
        .brand-divider { width: 1px; align-self: stretch; background: var(--border-subtle); margin: -12px 0; }

        .topbar-controls { display: flex; align-items: center; gap: 22px; flex-wrap: wrap; }
        .topbar-actions { display: flex; flex-direction: column; align-items: center; gap: 6px; margin-left: auto; flex: 0 0 auto; }

        .topbar-btn {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--border-subtle);
            color: var(--text-primary);
            border-radius: 8px;
            min-width: 2.3em; height: 2.3em; padding: 0 0.6em;
            display: flex; align-items: center; justify-content: center;
            font-family: inherit; font-size: 1em; font-weight: 600;
            cursor: pointer; transition: background 0.15s ease, transform 0.15s ease;
        }
        .topbar-btn:hover { background: rgba(255, 255, 255, 0.13); }
        .topbar-btn:active { transform: scale(0.92); }

        .topbar .shiny-input-container { margin-bottom: 0; }
        .topbar label { color: var(--text-muted); margin-bottom: 3px; font-weight: 500; font-size: 0.92em; letter-spacing: 0.2px; }

        .topbar .form-control, .topbar select.form-select {
            background: rgba(255, 255, 255, 0.05) !important;
            border: 1px solid var(--border-subtle) !important;
            color: var(--text-primary) !important;
            border-radius: 10px !important;
            font-size: 1em !important;
        }
        .topbar .input-group-text, .topbar .btn-default, .topbar .btn-secondary, .topbar .btn-file {
            background: rgba(255, 255, 255, 0.06) !important;
            border: 1px solid var(--border-subtle) !important;
            color: var(--text-primary) !important;
            border-radius: 10px !important;
        }
        .slider-stack, .scalebar-stack { display: flex; flex-direction: column; gap: 6px; }

        /* ui.input_switch already renders Bootstrap's real switch component,
           which picks up our theme's primary/border-radius automatically -
           just align its spacing with the rest of the topbar. */
        .topbar .form-check.form-switch { margin: 0; display: flex; align-items: center; gap: 9px; padding-left: 0; }
        .topbar .form-check.form-switch .form-check-input { margin: 0; flex: 0 0 auto; cursor: pointer; }
        .topbar .form-check-label { cursor: pointer; }

        .irs--shiny { font-size: 1em !important; }
        .irs--shiny .irs-line { background: rgba(255, 255, 255, 0.08); border-radius: 6px; }
        .irs--shiny .irs-bar { background: linear-gradient(90deg, var(--accent-1), var(--accent-2)) !important; }
        .irs--shiny .irs-single, .irs--shiny .irs-from, .irs--shiny .irs-to {
            background: var(--accent-1) !important;
            color: #14110a !important; /* dark text for legibility on the bright gold badge */
        }
        .irs--shiny .irs-handle { box-shadow: 0 0 0 3px rgba(var(--accent-1-rgb), 0.35), 0 2px 6px rgba(0, 0, 0, 0.4); }
        .irs--shiny .irs-min, .irs--shiny .irs-max { color: var(--text-muted); background: transparent; }

        #status { color: var(--text-muted); white-space: pre-line; font-size: 0.92em; }
    """),
    ui.tags.script(
        ui.HTML('{"imports": {"three": "/vendor/three.module.js"}}'),
        type="importmap",
    ),
    ui.div(
        ui.div(
            ui.div(ui.div(class_="brand-mark"), "Overlay Viewer", class_="brand"),
            ui.output_text("status"),
            class_="brand-block",
        ),
        ui.div(class_="brand-divider"),
        ui.div(
            ui.input_file("image_file", "Image (.tif)", accept=[".tif", ".tiff"], width="220px"),
            ui.input_file("loc_file", "Localizations (.csv)", accept=[".csv"], width="220px"),
            ui.input_numeric("pixel_size", "Pixel size (nm/px)", value=97, min=0.1, step=0.1, width="150px"),
            ui.input_select("colormap", "Color", choices=FLAT_COLOR_CHOICES, selected="magenta", width="140px"),
            ui.div(
                ui.input_slider("point_size", "Sphere size", min=1, max=20, value=5, step=0.5, width="150px"),
                ui.input_slider("point_opacity", "Opacity", min=0.1, max=1, value=0.9, step=0.1, width="150px"),
                class_="slider-stack",
            ),
            ui.div(
                ui.input_switch("show_scale_bar", "Scale bar", value=False),
                ui.panel_conditional(
                    "input.show_scale_bar",
                    ui.input_numeric("scale_bar_um", "Size (µm)", value=5, min=1, step=1, width="100px"),
                ),
                class_="scalebar-stack",
            ),
            class_="topbar-controls",
        ),
        ui.div(
            ui.tags.button("XY", id="btn-reset-view", class_="topbar-btn", title="Reset view", type="button"),
            ui.tags.button("+", id="btn-font-inc", class_="topbar-btn", title="Increase toolbar text size", type="button"),
            ui.tags.button("−", id="btn-font-dec", class_="topbar-btn", title="Decrease toolbar text size", type="button"),
            class_="topbar-actions",
        ),
        class_="topbar",
    ),
    ui.div(id="viewer-canvas"),
    ui.tags.script(src="viewer.js", type="module"),
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
        if img is not None:
            parts.append(f"image {img.shape[1]}×{img.shape[0]} px")
        df, is_3d = loc_data()
        if df is not None:
            parts.append(f"{len(df):,} localizations ({'3D' if is_3d else '2D'})")
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
        image_z_px = 0.0

        if df is not None and len(df):
            x_px = df["x"].to_numpy() / pixel_size
            y_px = -df["y"].to_numpy() / pixel_size
            z_px = df["z"].to_numpy() / pixel_size if is_3d else np.zeros(len(df))
            colors = _compute_point_colors(df, is_3d, color_choice)
            if is_3d:
                # Placed a nanometer below the lowest localization so the whole
                # point cloud renders above the image rather than through it.
                image_z_px = (float(df["z"].to_numpy().min()) - 1.0) / pixel_size
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
