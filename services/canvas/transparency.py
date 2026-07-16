"""Versioned effective-background transparency detection."""
from __future__ import annotations

import math
from collections import deque
from fractions import Fraction

from PIL import Image


TRANSPARENCY_PROCESSOR_VERSION = "edge-alpha-v1"


def has_effective_transparent_background(
    image: Image.Image,
    *,
    alpha_threshold: int = 250,
    min_edge_fraction: float = 0.005,
) -> bool:
    """Return whether enough alpha-qualified pixels connect to an image edge."""
    if type(alpha_threshold) is not int or not 0 <= alpha_threshold <= 255:
        raise ValueError("alpha_threshold must be an integer from 0 through 255")
    if (
        isinstance(min_edge_fraction, bool)
        or not isinstance(min_edge_fraction, (int, float))
        or not math.isfinite(min_edge_fraction)
        or not 0 < min_edge_fraction <= 1
    ):
        raise ValueError("min_edge_fraction must be finite and greater than 0 through 1")
    minimum_fraction = Fraction(str(min_edge_fraction))

    width, height = image.size
    total_pixels = width * height
    if total_pixels <= 0:
        return False

    if "A" in image.getbands():
        alpha = image.getchannel("A")
    elif "transparency" in image.info:
        alpha = image.convert("RGBA").getchannel("A")
    else:
        return False
    alpha_values = alpha.tobytes()

    visited = bytearray(total_pixels)
    pending: deque[int] = deque()
    connected_count = 0

    def add_if_qualified(index: int) -> bool:
        nonlocal connected_count
        if not visited[index] and alpha_values[index] <= alpha_threshold:
            visited[index] = 1
            pending.append(index)
            connected_count += 1
            return (
                connected_count * minimum_fraction.denominator
                >= total_pixels * minimum_fraction.numerator
            )
        return False

    last_row = (height - 1) * width
    for x in range(width):
        if add_if_qualified(x) or add_if_qualified(last_row + x):
            return True
    for y in range(height):
        row = y * width
        if add_if_qualified(row) or add_if_qualified(row + width - 1):
            return True

    while pending:
        index = pending.popleft()
        x = index % width
        y = index // width
        for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
            row = neighbor_y * width
            for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                neighbor_index = row + neighbor_x
                if neighbor_index != index:
                    if add_if_qualified(neighbor_index):
                        return True

    return False
