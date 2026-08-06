"""Face detection used to (a) steer the vertical-crop pan so it follows people
instead of blindly center-cropping, and (b) locate faces for the --face-privacy
blur/emoji modes.

Uses OpenCV's bundled-with-this-repo Haar cascade — fast, no model download,
no GPU needed. Works best on frontal, reasonably well-lit faces, which
covers the common photobooth case (posed group shots) well; it will miss
profile faces or faces in poor lighting, in which case callers fall back to
a plain centered crop / leave those faces unobscured.
"""

from pathlib import Path

import cv2
import numpy as np

_CASCADE_PATH = Path(__file__).parent / "data" / "haarcascade_frontalface_default.xml"
_cascade: cv2.CascadeClassifier | None = None

BBox = tuple[int, int, int, int]  # left, top, right, bottom


def _get_cascade() -> cv2.CascadeClassifier:
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(str(_CASCADE_PATH))
        if _cascade.empty():
            raise RuntimeError(f"Failed to load face cascade from {_CASCADE_PATH}")
    return _cascade


def detect_faces(image_rgb: np.ndarray) -> list[BBox]:
    """Detect faces in an RGB image array, returning one bounding box
    (left, top, right, bottom) per face. Empty list if none found.
    """
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    faces = _get_cascade().detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
    )
    return [(int(x), int(y), int(x + w), int(y + h)) for x, y, w, h in faces]


def union_bbox(boxes: list[BBox]) -> BBox | None:
    """Collapse a list of face boxes into one bounding box covering all of
    them, or None if the list is empty. Used to steer the vertical pan.
    """
    if not boxes:
        return None
    lefts = [b[0] for b in boxes]
    tops = [b[1] for b in boxes]
    rights = [b[2] for b in boxes]
    bottoms = [b[3] for b in boxes]
    return min(lefts), min(tops), max(rights), max(bottoms)


def detect_face_bbox(image_rgb: np.ndarray) -> BBox | None:
    """Convenience wrapper: detect faces and return their union bbox directly."""
    return union_bbox(detect_faces(image_rgb))
