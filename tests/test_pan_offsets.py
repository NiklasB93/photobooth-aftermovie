"""Tests for the face-aware pan-window math in aftermovie.video.compute_pan_offsets.

Runnable standalone (no pytest needed): `python3 tests/test_pan_offsets.py`
Also discoverable by pytest if installed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aftermovie.video import compute_pan_offsets


def test_no_horizontal_room_returns_static_regardless_of_face():
    start, end = compute_pan_offsets(1080, 1080, (100, 0, 300, 200))
    assert start == end == 0


def test_no_face_detected_centers_statically():
    start, end = compute_pan_offsets(2000, 1080, None)
    assert start == end == (2000 - 1080) / 2


def test_face_fitting_in_one_window_is_static_and_centered_on_face():
    # face spans [900, 1100] in a 2000px-wide scaled image, 1080px window
    start, end = compute_pan_offsets(2000, 1080, (900, 0, 1100, 200))
    assert start == end
    # window should be centered on the face's midpoint (1000), clamped to bounds
    expected_center = max(0, min(1000 - 1080 / 2, 2000 - 1080))
    assert start == expected_center


def test_wide_face_spread_produces_a_real_pan():
    # face bbox spans almost the whole width of a very wide scaled image
    start, end = compute_pan_offsets(3000, 1080, (100, 0, 2800, 200))
    assert end > start
    # never requests pixels outside the actual image
    assert start >= 0
    assert end <= 3000 - 1080


def test_face_near_left_edge_never_goes_negative():
    start, end = compute_pan_offsets(2000, 1080, (0, 0, 200, 200))
    assert start >= 0
    assert end >= 0


def test_face_near_right_edge_never_exceeds_bounds():
    max_offset = 2000 - 1080
    start, end = compute_pan_offsets(2000, 1080, (1800, 0, 2000, 200))
    assert start <= max_offset
    assert end <= max_offset


def test_pan_keeps_margin_clear_of_frame_edge_when_possible():
    # face spans [500, 2500] in a 3000px image, plenty of room for margin
    start, end = compute_pan_offsets(3000, 1080, (500, 0, 2500, 200), margin_frac=0.15)
    margin = 0.15 * 1080
    # at the start of the pan, the face's left edge should sit `margin` px
    # inside the window's left edge (not flush against it)
    assert abs((start + margin) - 500) < 1e-6
    # at the end of the pan, the face's right edge should sit `margin` px
    # inside the window's right edge
    assert abs((end + 1080 - margin) - 2500) < 1e-6


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed.")
