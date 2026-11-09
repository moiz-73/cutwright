"""A small, deterministic 3D layer for the compositor.

Real perspective projection, depth sorting, flat-shaded meshes and textured
planes warped through Skia's projective matrix. No GL context, no browser, no
GPU: ~1-3 ms per plane and a few ms per mesh at 1080p.

This is what gives the films camera parallax that a 2D `scale()` cannot fake.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import skia


# --------------------------------------------------------------------- maths
def mat_identity() -> np.ndarray:
    return np.eye(4, dtype=np.float64)


def mat_translate(x: float, y: float, z: float) -> np.ndarray:
    m = mat_identity()
    m[:3, 3] = (x, y, z)
    return m


def mat_scale(x: float, y: float | None = None, z: float | None = None) -> np.ndarray:
    m = mat_identity()
    m[0, 0], m[1, 1], m[2, 2] = x, x if y is None else y, x if z is None else z
    return m


def mat_rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    m = mat_identity()
    m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c
    return m


def mat_rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    m = mat_identity()
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def mat_rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    m = mat_identity()
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c
    return m


def look_at(eye, target, up=(0, 1, 0)) -> np.ndarray:
    eye = np.asarray(eye, np.float64)
    target = np.asarray(target, np.float64)
    up = np.asarray(up, np.float64)
    f = target - eye
    f /= np.linalg.norm(f) + 1e-12
    s = np.cross(f, up)
    s /= np.linalg.norm(s) + 1e-12
    u = np.cross(s, f)
    m = mat_identity()
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def perspective(fov_y_deg: float, aspect: float, near=0.1, far=100.0) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_y_deg) / 2)
    m = np.zeros((4, 4), np.float64)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1
    return m


@dataclass
class Camera:
    width: int
    height: int
    pos: tuple = (0.0, 0.0, 6.0)
    target: tuple = (0.0, 0.0, 0.0)
    up: tuple = (0.0, 1.0, 0.0)
    fov: float = 38.0
    near: float = 0.1
    far: float = 120.0

    def __post_init__(self):
        self._vp = self._build_vp()

    def _build_vp(self) -> np.ndarray:
        aspect = self.width / self.height
        return perspective(self.fov, aspect, self.near, self.far) @ look_at(self.pos, self.target, self.up)

    def view_proj(self) -> np.ndarray:
        return self._vp

    def project(self, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (screen_xy, depth, valid) for Nx3 world points."""
        pts = np.atleast_2d(np.asarray(pts, np.float64))
        homo = np.concatenate([pts, np.ones((len(pts), 1))], axis=1)
        clip = homo @ self.view_proj().T
        w = clip[:, 3]
        valid = w > 1e-6
        ndc = np.zeros((len(pts), 3))
        ndc[valid] = clip[valid, :3] / w[valid, None]
        x = (ndc[:, 0] + 1) * 0.5 * self.width
        y = (1 - ndc[:, 1]) * 0.5 * self.height
        return np.stack([x, y], 1), w, valid  # depth = positive camera distance


# ------------------------------------------------------------------- objects
@dataclass
class Plane:
    """A textured or solid quad in 3D."""

    w: float
    h: float
    model: np.ndarray = field(default_factory=mat_identity)
    image: np.ndarray | None = None  # HxWx3/4 uint8
    color: tuple = (1, 1, 1)
    alpha: float = 1.0
    shadow: float = 0.0
    draw: object = None  # callable(raster) drawing in local px, origin top-left
    units: float = 200.0  # local pixels per world unit, for \`draw\` planes

    def corners(self) -> np.ndarray:
        hw, hh = self.w / 2, self.h / 2
        local = np.array(
            [[-hw, -hh, 0], [hw, -hh, 0], [hw, hh, 0], [-hw, hh, 0]], np.float64
        )
        return (local @ self.model[:3, :3].T) + self.model[:3, 3]

    def center(self) -> np.ndarray:
        return self.model[:3, 3]


def box(w: float, h: float, d: float, color=(0.16, 0.17, 0.2)) -> tuple[np.ndarray, list]:
    hw, hh, hd = w / 2, h / 2, d / 2
    v = np.array(
        [
            [-hw, -hh, -hd], [hw, -hh, -hd], [hw, hh, -hd], [-hw, hh, -hd],
            [-hw, -hh, hd], [hw, -hh, hd], [hw, hh, hd], [-hw, hh, hd],
        ],
        np.float64,
    )
    faces = [
        ([0, 1, 2, 3], color, 0.85),  # back
        ([4, 5, 6, 7], color, 1.15),  # front
        ([0, 1, 5, 4], color, 0.7),   # bottom
        ([3, 2, 6, 7], color, 0.92),  # top
        ([0, 3, 7, 4], color, 0.62),  # left
        ([1, 2, 6, 5], color, 0.78),  # right
    ]
    return v, faces


def draw_mesh(r, cam: Camera, verts: np.ndarray, faces: list, model: np.ndarray, alpha: float = 1.0) -> None:
    world = (verts @ model[:3, :3].T) + model[:3, 3]
    scr, depth, valid = cam.project(world)
    if not valid.all():
        return
    order = sorted(range(len(faces)), key=lambda i: -np.mean([depth[j] for j in faces[i][0]]))
    for fi in order:
        idx, color, shade = faces[fi]
        poly = scr[idx]
        # backface cull via signed area
        area = 0.0
        for k in range(len(idx)):
            x1, y1 = poly[k]
            x2, y2 = poly[(k + 1) % len(idx)]
            area += x1 * y2 - x2 * y1
        if area >= 0:
            continue
        path = skia.Path()
        path.moveTo(float(poly[0][0]), float(poly[0][1]))
        for p in poly[1:]:
            path.lineTo(float(p[0]), float(p[1]))
        path.close()
        p = skia.Paint(AntiAlias=True)
        c = [min(1.0, v * shade) for v in color]
        p.setColor4f(skia.Color4f(c[0], c[1], c[2], alpha))
        r.canvas.drawPath(path, p)


def draw_plane(r, cam: Camera, plane: Plane) -> None:
    pts, depth, valid = cam.project(plane.corners())
    if not valid.all() or np.any(depth <= cam.near):
        return
    if plane.shadow > 0:
        # cheap contact shadow: the same quad, blurred and offset down
        path = skia.Path()
        path.moveTo(float(pts[0][0]), float(pts[0][1]))
        for p in pts[1:]:
            path.lineTo(float(p[0]), float(p[1]))
        path.close()
        p = skia.Paint(AntiAlias=True)
        p.setColor4f(skia.Color4f(0, 0, 0, 0.55 * plane.shadow))
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 26))
        c = r.canvas.save()
        r.canvas.translate(0, 18)
        r.canvas.drawPath(path, p)
        r.canvas.restoreToCount(c)

    m = skia.Matrix()
    if plane.draw is not None:
        iw, ih = plane.w * plane.units, plane.h * plane.units
        src = [skia.Point(0, 0), skia.Point(iw, 0), skia.Point(iw, ih), skia.Point(0, ih)]
        dst = [skia.Point(float(x), float(y)) for x, y in pts]
        if not m.setPolyToPoly(src, dst):
            return
        r.canvas.save()
        r.canvas.concat(m)
        with r.alpha(plane.alpha):
            plane.draw(r)
        r.canvas.restore()
        return

    if plane.image is None:
        path = skia.Path()
        path.moveTo(float(pts[0][0]), float(pts[0][1]))
        for p in pts[1:]:
            path.lineTo(float(p[0]), float(p[1]))
        path.close()
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(*plane.color, plane.alpha))
        r.canvas.drawPath(path, paint)
        return

    img = r._img_for(plane.image)
    iw, ih = img.width(), img.height()
    src = [
        skia.Point(0, 0), skia.Point(iw, 0), skia.Point(iw, ih), skia.Point(0, ih)
    ]
    dst = [skia.Point(float(x), float(y)) for x, y in pts]
    if not m.setPolyToPoly(src, dst):
        return
    paint = skia.Paint(AntiAlias=True)
    paint.setAlphaf(plane.alpha)
    r.canvas.save()
    r.canvas.concat(m)
    # the matrix maps the image rect; drawing at origin paints exactly the quad
    r.canvas.drawImage(img, 0, 0, skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear), paint)
    r.canvas.restore()


def draw_scene(r, cam: Camera, planes: list[Plane], meshes: list[tuple] | None = None) -> None:
    """Painter's algorithm: far to near."""
    items = []
    for pl in planes:
        items.append((cam.project(pl.center()[None, :])[1][0], "plane", pl))
    for verts, faces, model, alpha in meshes or []:
        c = model[:3, 3]
        items.append((cam.project(c[None, :])[1][0], "mesh", (verts, faces, model, alpha)))
    for _, kind, obj in sorted(items, key=lambda t: -t[0]):  # farthest (largest depth) first
        if kind == "plane":
            draw_plane(r, cam, obj)
        else:
            draw_mesh(r, cam, *obj)


def grid_lines(cam: Camera, z0: float, z1: float, step: float, half_width: float, y: float = 0.0) -> list[tuple]:
    """Return screen segments for a receding floor grid."""
    segs: list[tuple] = []
    z = z0
    while z >= z1:
        pts = np.array([[-half_width, y, z], [half_width, y, z]])
        scr, depth, valid = cam.project(pts)
        if valid.all():
            segs.append((scr[0], scr[1], 1.0 - (z0 - z) / max(1e-6, z0 - z1)))
        z -= step
    for x in np.linspace(-half_width, half_width, 9):
        pts = np.array([[x, y, z0], [x, y, z1]])
        scr, depth, valid = cam.project(pts)
        if valid.all():
            segs.append((scr[0], scr[1], 0.55))
    return segs
