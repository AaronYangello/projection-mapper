"""Projective mapping in top-left-origin normalized coordinates."""

import numpy as np


def homography(corners: list | tuple) -> np.ndarray:
    """Map the unit rectangle's TL, TR, BR, BL to a convex quadrilateral."""
    rows, values = [], []
    for (u, v), (x, y) in zip(((0, 0), (1, 0), (1, 1), (0, 1)), corners, strict=True):
        rows.extend(([u, v, 1, 0, 0, 0, -x * u, -x * v], [0, 0, 0, u, v, 1, -y * u, -y * v]))
        values.extend((x, y))
    return np.append(np.linalg.solve(rows, values), 1).reshape(3, 3)


def color_rgb(hex_color: str) -> tuple[float, float, float]:
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
