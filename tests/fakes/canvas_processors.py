"""Deterministic, thread-safe Product Canvas processor fakes for E2E."""

from __future__ import annotations

import hashlib
from collections import Counter
from threading import Lock

from PIL import Image


FAIL_ONCE_SENTINEL_RGB = (255, 0, 255)


class FakeMaskerFirstAttemptError(RuntimeError):
    """Raised once for each sentinel input digest so retry behavior is observable."""


class FakeMasker:
    """Create a stable foreground mask and expose digest-keyed call accounting."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._calls_by_digest: Counter[str] = Counter()

    @staticmethod
    def input_digest(image: Image.Image) -> str:
        if not isinstance(image, Image.Image):
            raise TypeError("image must be a Pillow Image")
        normalized = image.convert("RGBA")
        try:
            digest = hashlib.sha256()
            digest.update(b"facai-canvas-fake-masker-v1\0")
            digest.update(image.mode.encode("ascii", errors="strict"))
            digest.update(b"\0")
            digest.update(image.width.to_bytes(4, "big"))
            digest.update(image.height.to_bytes(4, "big"))
            digest.update(normalized.tobytes())
            return digest.hexdigest()
        finally:
            normalized.close()

    def create_mask(self, image: Image.Image) -> Image.Image:
        if not isinstance(image, Image.Image):
            raise TypeError("image must be a Pillow Image")
        if image.width <= 0 or image.height <= 0:
            raise ValueError("image dimensions must be positive")
        digest = self.input_digest(image)
        rgb = image.convert("RGB")
        try:
            sentinel = rgb.getpixel((0, 0)) == FAIL_ONCE_SENTINEL_RGB
            with self._lock:
                self._calls_by_digest[digest] += 1
                digest_calls = self._calls_by_digest[digest]
            if sentinel and digest_calls == 1:
                raise FakeMaskerFirstAttemptError(
                    "sentinel input intentionally fails on its first attempt"
                )

            left = rgb.width // 4
            right = rgb.width - left
            top = rgb.height // 4
            bottom = rgb.height - top
            mask = Image.new("L", rgb.size, 0)
            mask.putdata(
                [
                    255 if left <= x < right and top <= y < bottom else 0
                    for y in range(rgb.height)
                    for x in range(rgb.width)
                ]
            )
            return mask
        finally:
            rgb.close()

    def audit_snapshot(self) -> dict[str, object]:
        with self._lock:
            calls = dict(sorted(self._calls_by_digest.items()))
        return {
            "totalCalls": sum(calls.values()),
            "callsByDigest": calls,
        }

    def reset_audit(self) -> None:
        with self._lock:
            self._calls_by_digest.clear()


__all__ = [
    "FAIL_ONCE_SENTINEL_RGB",
    "FakeMasker",
    "FakeMaskerFirstAttemptError",
]
