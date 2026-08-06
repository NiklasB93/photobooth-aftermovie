"""Face detection used to (a) steer the vertical-crop pan so it follows people
instead of blindly center-cropping, and (b) locate faces for the --face-privacy
blur/emoji modes.

Uses OpenCV's DNN module with a small SSD (Caffe ResNet10) face detector,
vendored in this repo — no runtime model download. Chosen over a Haar
cascade (the original implementation) after finding the cascade missed a
real, common photobooth case: tilted/angled heads. In a synthetic test,
a face rotated 30 degrees was missed entirely by the Haar cascade but
still caught (99.8% confidence) by this detector. It's also generally
far more tolerant of varied expressions and non-frontal poses.

Heavy occlusion (sunglasses, oversized props covering much of the face —
common with photobooth props) can still defeat this detector; that's an
inherent limit of appearance-based 2D face detection, not something
swapping detectors fixes.
"""

from pathlib import Path

import cv2
import numpy as np

_PROTOTXT_PATH = Path(__file__).parent / "data" / "face_detector_deploy.prototxt"
_MODEL_PATH = Path(__file__).parent / "data" / "res10_300x300_ssd_iter_140000.caffemodel"
_CONFIDENCE_THRESHOLD = 0.5

_net: cv2.dnn.Net | None = None

BBox = tuple[int, int, int, int]  # left, top, right, bottom


def _get_net() -> cv2.dnn.Net:
    global _net
    if _net is None:
        _net = cv2.dnn.readNetFromCaffe(str(_PROTOTXT_PATH), str(_MODEL_PATH))
    return _net


def detect_faces(image_rgb: np.ndarray) -> list[BBox]:
    """Detect faces in an RGB image array, returning one bounding box
    (left, top, right, bottom) per face. Empty list if none found.
    """
    h, w = image_rgb.shape[:2]
    bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    blob = cv2.dnn.blobFromImage(cv2.resize(bgr, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
    net = _get_net()
    net.setInput(blob)
    detections = net.forward()

    boxes = []
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence < _CONFIDENCE_THRESHOLD:
            continue
        box = detections[0, 0, i, 3:7] * [w, h, w, h]
        left, top, right, bottom = box.astype(int)
        left, top = max(0, left), max(0, top)
        right, bottom = min(w, right), min(h, bottom)
        if right > left and bottom > top:
            boxes.append((int(left), int(top), int(right), int(bottom)))
    return boxes


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
