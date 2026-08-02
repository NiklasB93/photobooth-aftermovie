"""Face detection used to steer the vertical-crop pan so it follows people
instead of blindly center-cropping (or panning across empty background).

Uses OpenCV's bundled-with-this-repo Haar cascade — fast, no model download,
no GPU needed. Works best on frontal, reasonably well-lit faces, which
covers the common photobooth case (posed group shots) well; it will miss
profile faces or faces in poor lighting, in which case callers fall back to
a plain centered crop.
"""

from pathlib import Path

import cv2
import numpy as np

_CASCADE_PATH = Path(__file__).parent / "data" / "haarcascade_frontalface_default.xml"
_cascade: cv2.CascadeClassifier | None = None


def _get_cascade() -> cv2.CascadeClassifier:
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(str(_CASCADE_PATH))
        if _cascade.empty():
            raise RuntimeError(f"Failed to load face cascade from {_CASCADE_PATH}")
    return _cascade


def detect_face_bbox(image_rgb: np.ndarray) -> tuple[int, int, int, int] | None:
    """Detect faces in an RGB image array and return a single bounding box
    (left, top, right, bottom) covering all of them, or None if none found.
    """
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    faces = _get_cascade().detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
    )
    if len(faces) == 0:
        return None
    lefts, tops = faces[:, 0], faces[:, 1]
    rights, bottoms = faces[:, 0] + faces[:, 2], faces[:, 1] + faces[:, 3]
    return int(lefts.min()), int(tops.min()), int(rights.max()), int(bottoms.max())
