import * as THREE from "three";
import { OrbitControls } from "/vendor/OrbitControls.js";

const container = document.getElementById("viewer-canvas");

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1e6);
const renderer = new THREE.WebGLRenderer({ antialias: true });
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 0.01;
controls.maxDistance = 1e7;

// OrbitControls' built-in wheel zoom scales its zoom factor directly off the
// raw wheel deltaY. Trackpad pinch-to-zoom fires deltaY spikes far larger than
// a physical mouse wheel's discrete ~100-unit notches, which collapses that
// formula toward zero and snaps the camera to the target in one gesture. We
// handle wheel zoom ourselves with a delta cap so every input device dollies
// by a bounded, predictable step instead.
controls.enableZoom = false;

function onWheelZoom(event) {
    event.preventDefault();
    // Capped at +/-100 to match a single physical mouse-wheel notch; deltaY < 0
    // (scroll/pinch "up") zooms in, matching the convention OrbitControls itself uses.
    const cappedDelta = Math.max(-100, Math.min(100, event.deltaY));
    const factor = Math.pow(0.95, -cappedDelta / 100);
    const offset = camera.position.clone().sub(controls.target);
    const newLength = Math.min(controls.maxDistance, Math.max(controls.minDistance, offset.length() * factor));
    offset.setLength(newLength);
    camera.position.copy(controls.target).add(offset);
}
renderer.domElement.addEventListener("wheel", onWheelZoom, { passive: false });

let imagePlane = null;
let pointCloud = null;

// Loaded once and reused across scene reloads (e.g. every pixel-size tweak),
// rather than refetched each time loadScene() runs. Left null if the asset is
// missing/fails to load, so the point cloud falls back to plain colored dots
// instead of going fully invisible (a texture-driven `map` with transparent:true
// samples alpha=0 for a never-loaded texture).
let sphereSpriteTexture = null;
new THREE.TextureLoader().load(
    "/sphere.png",
    (tex) => {
        sphereSpriteTexture = tex;
        if (pointCloud) {
            pointCloud.material.map = tex;
            pointCloud.material.needsUpdate = true;
        }
    },
    undefined,
    () => console.warn("viewer.js: /sphere.png failed to load; point cloud will render as plain dots"),
);

// Persists across scene reloads so a re-uploaded file or pixel-size tweak
// keeps whatever size the user last dialed in on the slider.
let currentPointSize = 5;
let currentPointOpacity = 0.9;

// Untransformed image dimensions, kept so the alignment controls can be
// re-applied from scratch rather than accumulating rounding on each nudge.
let imageBase = null;
let imageTransform = { scale: 1, dx_px: 0, dy_px: 0 };

function applyImageTransform() {
    if (!imagePlane || !imageBase) return;
    const { width, height, z } = imageBase;
    const s = imageTransform.scale || 1;
    imagePlane.scale.set(s, s, 1);
    // PlaneGeometry is centred on its own origin, so half the *scaled* size puts
    // image pixel (0,0) at world (0,0); rows then run downward (-Y) to match the
    // localization convention. The offsets shift from there: +X right, +Y down.
    imagePlane.position.set(
        (width * s) / 2 + imageTransform.dx_px,
        -(height * s) / 2 - imageTransform.dy_px,
        z,
    );
}

const scaleBarEl = document.createElement("div");
scaleBarEl.style.cssText =
    "display:none; position:absolute; bottom:16px; right:16px; pointer-events:none; " +
    "text-align:center; color:#fff; font-family:sans-serif; font-size:12px; text-shadow:0 0 3px #000;";
const scaleBarLine = document.createElement("div");
scaleBarLine.style.cssText = "height:3px; background:#fff; margin:0 auto 4px;";
const scaleBarLabel = document.createElement("div");
scaleBarEl.appendChild(scaleBarLine);
scaleBarEl.appendChild(scaleBarLabel);
container.appendChild(scaleBarEl);

let scaleBar = { show: false, lengthWorld: 0, label: "" };

// Z-depth color legend, pinned to the top-right of the canvas (the control
// panel is on the left, so the two never collide).
const legendEl = document.createElement("div");
legendEl.style.cssText =
    "display:none; position:fixed; right:16px; z-index:9; pointer-events:none; " +
    "flex-direction:column; align-items:center; gap:6px; color:#fff; " +
    "font-family:sans-serif; font-size:12px; text-shadow:0 0 3px #000;";
const legendMaxLabel = document.createElement("div");
const legendBar = document.createElement("div");
legendBar.style.cssText = "width:14px; height:120px; border-radius:7px; border:1px solid rgba(255,255,255,0.3);";
const legendMinLabel = document.createElement("div");
legendEl.appendChild(legendMaxLabel);
legendEl.appendChild(legendBar);
legendEl.appendChild(legendMinLabel);
document.body.appendChild(legendEl);

function worldToScreen(point) {
    const ndc = point.clone().project(camera);
    if (Math.abs(ndc.z) > 1) return null; // behind camera / outside clip range
    return {
        x: (ndc.x * 0.5 + 0.5) * renderer.domElement.clientWidth,
        y: (-ndc.y * 0.5 + 0.5) * renderer.domElement.clientHeight,
    };
}

function updateScaleBar() {
    if (!scaleBar.show || scaleBar.lengthWorld <= 0) {
        scaleBarEl.style.display = "none";
        return;
    }
    // Measured at the current orbit target's depth, since that's the plane the
    // user is focused on; accurate for the top-down view this is designed for.
    const p1 = controls.target.clone();
    const p2 = p1.clone();
    p2.x += scaleBar.lengthWorld;
    const s1 = worldToScreen(p1);
    const s2 = worldToScreen(p2);
    const pxLength = s1 && s2 ? Math.hypot(s2.x - s1.x, s2.y - s1.y) : 0;
    if (!isFinite(pxLength) || pxLength <= 0) {
        scaleBarEl.style.display = "none";
        return;
    }
    scaleBarEl.style.display = "block";
    scaleBarLine.style.width = Math.max(1, pxLength) + "px";
    scaleBarLabel.textContent = scaleBar.label;
}

function resize() {
    const w = container.clientWidth || 1;
    const h = container.clientHeight || 1;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);
resize();

function resetView() {
    const box = new THREE.Box3();
    let haveContent = false;
    if (imagePlane) {
        box.expandByObject(imagePlane);
        haveContent = true;
    }
    if (pointCloud) {
        pointCloud.geometry.computeBoundingBox();
        box.union(pointCloud.geometry.boundingBox);
        haveContent = true;
    }
    if (haveContent) fitCameraToBounds(box);
}

const panelEl = document.querySelector(".sidepanel");
let panelFontSize = 13;
function applyPanelFontSize() {
    if (panelEl) panelEl.style.fontSize = panelFontSize + "px";
}

// The legend sits top-right, clear of the left-hand panel, so unlike the old
// top bar there is nothing to measure against - a fixed offset is enough.
function repositionLegend() {
    legendEl.style.top = "20px";
}
repositionLegend();

function setPanelCollapsed(collapsed) {
    document.body.classList.toggle("panel-collapsed", collapsed);
}
document.getElementById("btn-collapse")?.addEventListener("click", () => setPanelCollapsed(true));
document.getElementById("panel-expand")?.addEventListener("click", () => setPanelCollapsed(false));

document.getElementById("btn-reset-view")?.addEventListener("click", resetView);
document.getElementById("btn-font-inc")?.addEventListener("click", () => {
    panelFontSize = Math.min(20, panelFontSize + 1);
    applyPanelFontSize();
});
document.getElementById("btn-font-dec")?.addEventListener("click", () => {
    panelFontSize = Math.max(10, panelFontSize - 1);
    applyPanelFontSize();
});

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    // Near/far are re-derived from the current zoom distance every frame (rather
    // than fixed once at load time), otherwise the near plane can end up beyond
    // the geometry after zooming in far enough and everything clips away.
    const dist = controls.getDistance();
    camera.near = Math.max(dist / 1000, 0.001);
    camera.far = Math.max(dist * 1000, 10);
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
    updateScaleBar();
}
animate();

function base64ToFloat32Array(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Float32Array(bytes.buffer);
}

function disposeObject(obj, disposeMap = false) {
    if (!obj) return;
    scene.remove(obj);
    obj.geometry?.dispose();
    // The point cloud's map is the shared, reused sphereSpriteTexture and must
    // survive scene reloads; only the image plane's per-load texture is disposable.
    if (disposeMap && obj.material?.map) obj.material.map.dispose();
    obj.material?.dispose();
}

function fitCameraToBounds(box) {
    const center = new THREE.Vector3();
    box.getCenter(center);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z, 1);
    const distance = maxDim / (2 * Math.tan((Math.PI * camera.fov) / 360)) * 1.2;

    controls.target.copy(center);
    camera.position.set(center.x, center.y, center.z + distance);
    controls.update();
}

function loadScene(msg) {
    disposeObject(imagePlane, true);
    disposeObject(pointCloud, false);
    imagePlane = null;
    pointCloud = null;

    const box = new THREE.Box3();
    let haveContent = false;

    if (msg.image) {
        const { b64png, width, height, z } = msg.image;
        const tex = new THREE.TextureLoader().load("data:image/png;base64," + b64png);
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.minFilter = THREE.LinearFilter;
        const geo = new THREE.PlaneGeometry(width, height);
        const mat = new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide });
        imagePlane = new THREE.Mesh(geo, mat);
        imageBase = { width, height, z: z || 0 };
        applyImageTransform();
        scene.add(imagePlane);
        box.expandByObject(imagePlane);
        haveContent = true;
    }

    if (msg.points) {
        const positions = base64ToFloat32Array(msg.points.positions_b64);
        const colors = base64ToFloat32Array(msg.points.colors_b64);
        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        const mat = new THREE.PointsMaterial({
            size: currentPointSize,
            map: sphereSpriteTexture,
            sizeAttenuation: true,
            vertexColors: true,
            transparent: true,
            opacity: currentPointOpacity,
            depthWrite: false,
        });
        pointCloud = new THREE.Points(geo, mat);
        scene.add(pointCloud);
        geo.computeBoundingBox();
        box.union(geo.boundingBox);
        haveContent = true;
    }

    if (haveContent) fitCameraToBounds(box);
    repositionLegend();
}

function applyScaleBarUpdate(msg) {
    scaleBar = { show: !!msg.show, lengthWorld: msg.length_world || 0, label: msg.label || "" };
}

function applyPointSizeUpdate(msg) {
    currentPointSize = msg.size || 5;
    // Update the live material directly for instant slider feedback, without
    // waiting on a full scene reload (and without touching its shared texture).
    if (pointCloud) pointCloud.material.size = currentPointSize;
}

function applyPointOpacityUpdate(msg) {
    // 0 is a valid, meaningful opacity (fully transparent) so it must not be
    // treated as "missing" and replaced with the default via `|| 0.9`.
    currentPointOpacity = typeof msg.opacity === "number" ? msg.opacity : 0.9;
    if (pointCloud) pointCloud.material.opacity = currentPointOpacity;
}

function applyPointColorsUpdate(msg) {
    // Recolors the existing point cloud in place - no geometry rebuild, no
    // texture reload, no camera refit - so switching colormaps stays instant
    // instead of looking like the whole scene reloaded.
    if (!pointCloud) return;
    const colors = base64ToFloat32Array(msg.colors_b64);
    const attr = pointCloud.geometry.getAttribute("color");
    if (attr && attr.array.length === colors.length) {
        attr.array.set(colors);
        attr.needsUpdate = true;
    } else {
        console.warn("viewer.js: point_colors_update size mismatch, ignoring (a scene_update is likely in flight)");
    }
}

function applyLegendUpdate(msg) {
    if (!msg.show) {
        legendEl.style.display = "none";
        return;
    }
    legendBar.style.background = msg.gradient;
    legendMaxLabel.textContent = Math.round(msg.max) + " nm";
    legendMinLabel.textContent = Math.round(msg.min) + " nm";
    legendEl.style.display = "flex";
    repositionLegend();
}

function applyImageTransformUpdate(msg) {
    imageTransform = {
        scale: typeof msg.scale === "number" ? msg.scale : 1,
        dx_px: typeof msg.dx_px === "number" ? msg.dx_px : 0,
        dy_px: typeof msg.dy_px === "number" ? msg.dy_px : 0,
    };
    applyImageTransform();
}

function registerHandlers() {
    Shiny.addCustomMessageHandler("scene_update", loadScene);
    Shiny.addCustomMessageHandler("image_transform_update", applyImageTransformUpdate);
    Shiny.addCustomMessageHandler("scale_bar_update", applyScaleBarUpdate);
    Shiny.addCustomMessageHandler("point_size_update", applyPointSizeUpdate);
    Shiny.addCustomMessageHandler("point_opacity_update", applyPointOpacityUpdate);
    Shiny.addCustomMessageHandler("point_colors_update", applyPointColorsUpdate);
    Shiny.addCustomMessageHandler("legend_update", applyLegendUpdate);
}

window.__overlayViewerReady = new Promise((resolve) => {
    if (window.Shiny) {
        registerHandlers();
        resolve();
    } else {
        document.addEventListener("shiny:connected", () => {
            registerHandlers();
            resolve();
        });
    }
});

// Debug/testing hook only; not used by the app itself.
window.__overlayViewerDebug = {
    scene, camera, controls, loadScene, applyScaleBarUpdate, applyPointSizeUpdate,
    applyPointOpacityUpdate, applyPointColorsUpdate, applyLegendUpdate,
    applyImageTransformUpdate, resetView,
    getScaleBarState: () => scaleBar, getPointSize: () => currentPointSize,
    getPointOpacity: () => currentPointOpacity, getPanelFontSize: () => panelFontSize,
    getImageTransform: () => imageTransform, applyImageTransform,
    updateScaleBar, scaleBarEl, panelEl, setPanelCollapsed, legendEl, legendBar, legendMaxLabel, legendMinLabel,
    repositionLegend,
};
