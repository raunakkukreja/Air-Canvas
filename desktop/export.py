# export.py — Save images, export 3D models, generate Three.js viewer

import cv2
import numpy as np
import datetime
import os
from config import *

_brick_img = None
_white_brick_img = None

def _get_brick(h, w, light=False):
    global _brick_img, _white_brick_img
    # look for assets next to this file, or in parent dir
    base = os.path.dirname(os.path.abspath(__file__))
    if light:
        if _white_brick_img is None:
            for p in [os.path.join(base, 'assets', 'white_brick.jpg'),
                      os.path.join(base, '..', 'white_brick.jpg')]:
                if os.path.exists(p):
                    _white_brick_img = cv2.imread(p)
                    break
        img = _white_brick_img
    else:
        if _brick_img is None:
            for p in [os.path.join(base, 'assets', 'brick.jpg'),
                      os.path.join(base, '..', 'brick.jpg')]:
                if os.path.exists(p):
                    _brick_img = cv2.imread(p)
                    break
        img = _brick_img
    if img is None:
        return np.zeros((h, w, 3), dtype=np.uint8)
    return cv2.resize(img, (w, h))


def save_canvas_2d(canvas, glow_canvas, h, w, mode):
    """Save 2D canvas with chosen background. Returns filename."""
    mask = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
    mask_inv = cv2.bitwise_not(mask)

    if mode == 'raw':
        bg = np.zeros((h, w, 3), dtype=np.uint8)
    elif mode == 'white':
        bg = np.full((h, w, 3), 255, dtype=np.uint8)
    elif mode == 'white_brick':
        bg = _get_brick(h, w, light=True)
    else:
        bg = _get_brick(h, w, light=False)

    background = cv2.bitwise_and(bg, bg, mask=mask_inv)
    foreground = cv2.bitwise_and(canvas, canvas, mask=mask)
    out = cv2.add(background, foreground)

    # Composite glow drawing (always composite it with glow!)
    g_mask = cv2.cvtColor(glow_canvas, cv2.COLOR_BGR2GRAY)
    _, g_mask = cv2.threshold(g_mask, 1, 255, cv2.THRESH_BINARY)
    g_mask_inv = cv2.bitwise_not(g_mask)
    
    out_bg = cv2.bitwise_and(out, out, mask=g_mask_inv)
    out_fg = cv2.bitwise_and(glow_canvas, glow_canvas, mask=g_mask)
    out = cv2.add(out_bg, out_fg)

    # Apply soft glow bloom using effects helper
    from effects import apply_glow_layer
    glow_layer = apply_glow_layer(glow_canvas)
    out = cv2.add(out, glow_layer)

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = f'graffiti_{mode}_{ts}.png'
    cv2.imwrite(fname, out)
    return fname


def export_obj(strokes_3d, filename=None):
    """Export 3D strokes as an OBJ file with line elements."""
    if filename is None:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'air_canvas_3d_{ts}.obj'
    with open(filename, 'w') as f:
        f.write('# Air Canvas 3D Export\n')
        vi = 1
        for stroke in strokes_3d:
            pts = stroke['points']
            for p in pts:
                f.write(f'v {p[0]:.4f} {-p[1]:.4f} {p[2]:.4f}\n')
            idx_str = ' '.join(str(vi + i) for i in range(len(pts)))
            if stroke.get('spray', False):
                f.write(f'p {idx_str}\n')
            else:
                f.write(f'l {idx_str}\n')
            vi += len(pts)
    return filename


def export_threejs_html(strokes_3d, filename=None, bg_color='black'):
    """Generate a standalone HTML file with Three.js to view 3D drawing interactively."""
    if filename is None:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'air_canvas_3d_{bg_color}_{ts}.html'

    lines_js = []
    for stroke in strokes_3d:
        pts = stroke['points']
        col = stroke['color']
        # BGR → hex
        hex_col = '#{:02x}{:02x}{:02x}'.format(col[2], col[1], col[0])
        # If background is black and stroke is black, make it white for visibility; or vice versa
        if bg_color == 'black' and col[0] < 30 and col[1] < 30 and col[2] < 30:
            hex_col = '#ffffff'
        elif bg_color == 'white' and col[0] > 220 and col[1] > 220 and col[2] > 220:
            hex_col = '#000000'
        coords = ', '.join(f'{p[0]:.3f}, {-p[1]:.3f}, {p[2]:.3f}' for p in pts)
        if stroke.get('spray', False):
            lines_js.append(f'addPoints([{coords}], "{hex_col}", {stroke["thickness"]});')
        else:
            lines_js.append(f'addLine([{coords}], "{hex_col}", {stroke["thickness"]});')

    lines_block = '\n        '.join(lines_js)

    bg_hex = "0x111111" if bg_color == 'black' else "0xffffff"
    body_bg = "#111" if bg_color == 'black' else "#fff"
    grid_col1 = "0x555555" if bg_color == 'black' else "0xaaaaaa"
    grid_col2 = "0x333333" if bg_color == 'black' else "0xdddddd"

    html = f'''<!DOCTYPE html>
<html><head>
<title>Air Canvas 3D Viewer</title>
<style>body{{margin:0;background:{body_bg};overflow:hidden}}canvas{{display:block}}</style>
</head><body>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
const scene = new THREE.Scene();
scene.background = new THREE.Color({bg_hex});
const camera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 0.1, 1000);
camera.position.set(0, 2, 5);
const renderer = new THREE.WebGLRenderer({{antialias:true}});
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

// grid
const grid = new THREE.GridHelper(10, 20, {grid_col1}, {grid_col2});
scene.add(grid);

// axes
const axes = new THREE.AxesHelper(3);
scene.add(axes);

function addLine(coords, color, width) {{
    const points = [];
    for (let i = 0; i < coords.length; i += 3) {{
        points.push(new THREE.Vector3(coords[i], coords[i+1], coords[i+2]));
    }}
    const geom = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({{color: color, linewidth: width}});
    scene.add(new THREE.Line(geom, mat));
}}

function addPoints(coords, color, size) {{
    const points = [];
    for (let i = 0; i < coords.length; i += 3) {{
        points.push(new THREE.Vector3(coords[i], coords[i+1], coords[i+2]));
    }}
    const geom = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.PointsMaterial({{color: color, size: size * 0.015, sizeAttenuation: true}});
    scene.add(new THREE.Points(geom, mat));
}}

{lines_block}

function animate() {{
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}}
animate();
window.addEventListener('resize', () => {{
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
}});
</script></body></html>'''

    with open(filename, 'w') as f:
        f.write(html)
    return filename
