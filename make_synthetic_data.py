"""Generate a half-size synthetic sample dataset for the Overlay Viewer.

Mirrors the structure and statistics of the real SAFE360 astigmatism sample
(1024x1024 TIFF + 82k-row localization table) at half the linear/row size:
a 512x512 image and ~41k localizations.

The widefield image is rendered as a blurred version of the same emitter set
the localizations are sampled from, so the point cloud traces the image
structures exactly the way real correlative SMLM data does.

Run:  python make_synthetic_data.py
"""
import numpy as np
import pandas as pd
import tifffile
from scipy.interpolate import CubicSpline
from scipy.ndimage import gaussian_filter

SEED = 20260812
PIXEL_SIZE_NM = 97.0
IMG_PX = 512                      # half of the real 1024
FOV_NM = IMG_PX * PIXEL_SIZE_NM    # 49,664 nm
N_LOCS = 41_180                    # half of the real 82,361

OUT_TIF = "Synthetic_Snapshot_ROI-T.tif"
OUT_CSV = "Synthetic_CoordTable_3D_ASTIGMATISM.csv"

# Astigmatism calibration: sigma_x/sigma_y diverge either side of focus, which
# is what encodes z (real data: corr(z, log(sx/sy)) = 0.95).
AST_W0_NM = 180.0
AST_C_NM = 280.0
AST_D_NM = 330.0
# Fit-to-fit scatter on the PSF widths. Kept small: it competes directly with
# the z-driven width change, and too much of it washes out the calibration.
AST_JITTER = 0.09

rng = np.random.default_rng(SEED)


def _smooth_curve(p0, p1, n_ctrl=5, wobble=2200.0):
    """Random smooth 2D curve between two points, as a dense polyline.

    Cubic-splined rather than linearly interpolated, so filaments read as
    continuous curves instead of zigzagging between control points.
    """
    t = np.linspace(0, 1, n_ctrl)
    ctrl = np.outer(1 - t, p0) + np.outer(t, p1)
    ctrl[1:-1] += rng.normal(0, wobble, size=(n_ctrl - 2, 2))
    tt = np.linspace(0, 1, 300)
    spline = CubicSpline(t, ctrl, axis=0)
    return spline(tt)


def build_emitters():
    """Two elongated cells with filaments + puncta, plus sparse background."""
    xs, ys, zs, bright = [], [], [], []

    # Cell centres/orientations, laid out on a diagonal like the real sample.
    cells = [
        dict(cx=0.34 * FOV_NM, cy=0.60 * FOV_NM, ang=np.deg2rad(-33), rx=0.20 * FOV_NM, ry=0.085 * FOV_NM),
        dict(cx=0.66 * FOV_NM, cy=0.40 * FOV_NM, ang=np.deg2rad(-33), rx=0.22 * FOV_NM, ry=0.095 * FOV_NM),
    ]

    for cell in cells:
        ca, sa = np.cos(cell["ang"]), np.sin(cell["ang"])

        def to_world(u, v):
            return cell["cx"] + u * ca - v * sa, cell["cy"] + u * sa + v * ca

        # Filament network spanning the cell body.
        for _ in range(14):
            u0, v0 = rng.uniform(-cell["rx"], cell["rx"]), rng.uniform(-cell["ry"], cell["ry"])
            u1, v1 = rng.uniform(-cell["rx"], cell["rx"]), rng.uniform(-cell["ry"], cell["ry"])
            pts = _smooth_curve(np.array(to_world(u0, v0)), np.array(to_world(u1, v1)), wobble=0.05 * FOV_NM)
            n = rng.integers(900, 1700)
            idx = rng.integers(0, len(pts), n)
            xs.append(pts[idx, 0] + rng.normal(0, 90, n))
            ys.append(pts[idx, 1] + rng.normal(0, 90, n))
            zs.append(rng.normal(-120, 175, n))
            bright.append(rng.lognormal(0.0, 0.4, n))

        # Bright puncta (clusters), like the intense foci in the real image.
        for _ in range(rng.integers(5, 9)):
            u, v = rng.uniform(-0.7 * cell["rx"], 0.7 * cell["rx"]), rng.uniform(-0.6 * cell["ry"], 0.6 * cell["ry"])
            px_, py_ = to_world(u, v)
            n = rng.integers(700, 1500)
            xs.append(rng.normal(px_, 380, n))
            ys.append(rng.normal(py_, 380, n))
            zs.append(rng.normal(rng.uniform(-260, 60), 90, n))
            bright.append(rng.lognormal(1.1, 0.45, n))

        # Diffuse cytoplasmic haze filling the cell outline.
        n = 5200
        r = np.sqrt(rng.uniform(0, 1, n))
        th = rng.uniform(0, 2 * np.pi, n)
        wx, wy = to_world(r * np.cos(th) * cell["rx"], r * np.sin(th) * cell["ry"])
        xs.append(wx)
        ys.append(wy)
        zs.append(rng.normal(-90, 205, n))
        bright.append(rng.lognormal(-0.5, 0.4, n))

    # Sparse single molecules scattered over the whole field. These are dim
    # enough to stay invisible in the widefield frame but still blink and get
    # localized, which is why real data has plenty of off-structure points.
    n = 36000
    xs.append(rng.uniform(0.01 * FOV_NM, 0.99 * FOV_NM, n))
    ys.append(rng.uniform(0.01 * FOV_NM, 0.99 * FOV_NM, n))
    zs.append(rng.normal(-100, 215, n))
    bright.append(rng.lognormal(-0.7, 0.45, n))

    x = np.concatenate(xs)
    y = np.concatenate(ys)
    z = np.concatenate(zs)
    b = np.concatenate(bright)

    inside = (x > 0) & (x < FOV_NM) & (y > 0) & (y < FOV_NM)
    return x[inside], y[inside], z[inside], b[inside]


def render_image(x, y, b):
    """Widefield frame = diffraction-limited (blurred) emitter density + camera noise."""
    edges = np.arange(IMG_PX + 1) * PIXEL_SIZE_NM
    dens, _, _ = np.histogram2d(y, x, bins=[edges, edges], weights=b)
    signal = gaussian_filter(dens, sigma=1.6)  # ~PSF width in pixels

    signal = signal / signal.max() * 8500.0
    offset = 112.0
    img = offset + signal + rng.normal(0, 7, signal.shape) + rng.poisson(signal * 0.03)
    return np.clip(img, 62, 65535).astype(np.uint16)


def build_table(x, y, z, b):
    """Sample blinking events off the emitters and derive all fitted columns."""
    # Brighter emitters blink more often, but only sub-linearly: widefield
    # intensity integrates over all emitters, whereas localization counts are
    # far flatter, so a compressive exponent keeps the off-structure population
    # represented instead of every point piling onto the bright structures.
    w = b ** 0.22
    pick = rng.choice(len(x), size=N_LOCS, p=w / w.sum(), replace=True)

    intensity = np.clip(rng.lognormal(6.85, 0.52, N_LOCS), 32.94, 11250.92)
    sigma = np.clip(rng.lognormal(5.06, 0.24, N_LOCS), 55.01, 917.82)

    # Thompson-like: precision improves with photon count, degrades with PSF width.
    uncertainty = np.clip(sigma / np.sqrt(intensity) * 3.6 * rng.lognormal(0, 0.35, N_LOCS), 2.62, 99.93)

    x_nm = np.clip(x[pick] + rng.normal(0, 1, N_LOCS) * uncertainty, 0.5 * PIXEL_SIZE_NM, FOV_NM - 0.5 * PIXEL_SIZE_NM)
    y_nm = np.clip(y[pick] + rng.normal(0, 1, N_LOCS) * uncertainty, 0.5 * PIXEL_SIZE_NM, FOV_NM - 0.5 * PIXEL_SIZE_NM)
    z_nm = np.clip(z[pick] + rng.normal(0, 45, N_LOCS), -530.99, 287.41)

    # Astigmatic PSF widths: this is the relationship that encodes z.
    sigma_x = AST_W0_NM * np.sqrt(1 + ((z_nm + AST_C_NM) / AST_D_NM) ** 2) * rng.lognormal(0, AST_JITTER, N_LOCS)
    sigma_y = AST_W0_NM * np.sqrt(1 + ((z_nm - AST_C_NM) / AST_D_NM) ** 2) * rng.lognormal(0, AST_JITTER, N_LOCS)
    sigma_x = np.clip(sigma_x, 48.93, 868.82)
    sigma_y = np.clip(sigma_y, 50.27, 868.44)

    sigma_ast = np.clip(np.sqrt(sigma_x * sigma_y) * rng.lognormal(0, 0.10, N_LOCS), 73.62, 813.27)
    intensity_ast = np.clip(intensity * 1.66 * rng.lognormal(0, 0.30, N_LOCS), 89.30, 15405.16)
    uncertainty_ast = np.clip(sigma_ast / np.sqrt(intensity_ast) * 4.6 * rng.lognormal(0, 0.35, N_LOCS), 1.82, 99.95)

    # The two fits localize the same molecule slightly differently.
    x_ast = np.clip(x_nm + rng.normal(0, 100, N_LOCS), 0.0, FOV_NM)
    y_ast = np.clip(y_nm + rng.normal(0, 100, N_LOCS), 0.0, FOV_NM)

    frames = np.sort(rng.integers(54, 6863, N_LOCS))

    df = pd.DataFrame({
        "id": np.arange(1, N_LOCS + 1),
        "frame": frames,
        "x [nm]": x_nm,
        "y [nm]": y_nm,
        "z [nm]": z_nm,
        "sigma [nm]": sigma,
        "intensity [photon]": intensity,
        "amplitude [photon]": np.clip(intensity / 21.0 * rng.lognormal(0, 0.42, N_LOCS), 10.50, 506.52),
        "offset [photon]": np.clip(rng.normal(97.15, 4.79, N_LOCS), 58.61, 123.78),
        "bkgstd [photon]": np.clip(rng.lognormal(2.27, 0.17, N_LOCS), 5.64, 52.72),
        "uncertainty_xy [nm]": uncertainty,
        "x_AST [nm]": x_ast,
        "y_AST [nm]": y_ast,
        "sigma_AST [nm]": sigma_ast,
        "intensity_AST [photon]": intensity_ast,
        "amplitude_AST [photon]": np.clip(intensity_ast / 51.8 * rng.lognormal(0, 0.42, N_LOCS), 9.07, 278.05),
        "offset_AST [photon]": np.clip(rng.normal(90.63, 4.20, N_LOCS), 64.36, 117.25),
        "bkgstd_AST [photon]": np.clip(rng.lognormal(2.29, 0.17, N_LOCS), 6.82, 51.34),
        "uncertainty_xy_AST [nm]": uncertainty_ast,
        "sigma_x_AST [nm]": sigma_x,
        "sigma_y_AST [nm]": sigma_y,
    })
    return df.round(3)


def main():
    x, y, z, b = build_emitters()
    img = render_image(x, y, b)
    tifffile.imwrite(OUT_TIF, img)

    df = build_table(x, y, z, b)
    # The real file has a quoted header over a bare numeric body at a fixed 3
    # decimals. float_format alone can't do that (it stringifies the floats, so
    # QUOTE_NONNUMERIC would then quote them too), so the header is written
    # explicitly and the body appended unquoted.
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        fh.write(",".join(f'"{c}"' for c in df.columns) + "\n")
        df.to_csv(fh, index=False, header=False, float_format="%.3f")

    print(f"{OUT_TIF}: {img.shape} {img.dtype}  min={img.min()} max={img.max()}")
    print(f"{OUT_CSV}: {len(df):,} rows x {len(df.columns)} cols")


if __name__ == "__main__":
    main()
