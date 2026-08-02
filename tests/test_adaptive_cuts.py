"""Tests for aftermovie.beats.adaptive_cut_times — the energy-driven cut
cadence, decoupled from any real audio so it's fast and deterministic.

Runnable standalone: `python3 tests/test_adaptive_cuts.py`
Also discoverable by pytest if installed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aftermovie.beats import adaptive_cut_times


def test_empty_beats_returns_empty():
    assert adaptive_cut_times([], [], 1, 4) == []


def test_uniform_high_energy_cuts_at_min_span():
    beat_times = [float(i) for i in range(12)]  # one beat per second
    energy = [1.0] * 12  # maximally energetic throughout
    cuts = adaptive_cut_times(beat_times, energy, min_beats=1, max_beats=4)
    # every beat should become a cut
    assert cuts == beat_times


def test_uniform_low_energy_cuts_at_max_span():
    beat_times = [float(i) for i in range(12)]
    energy = [0.0] * 12  # completely flat/quiet throughout
    cuts = adaptive_cut_times(beat_times, energy, min_beats=1, max_beats=4)
    # should cut every 4th beat: 0, 4, 8
    assert cuts == [0.0, 4.0, 8.0]


def test_energy_variation_produces_cut_count_between_the_uniform_extremes():
    # The algorithm is greedy/reactive (decides span from the energy at the
    # beat it's currently on, no lookahead), so it won't land on exact
    # section boundaries — what matters is that mixing energy levels
    # produces a cut count strictly between the two uniform extremes for
    # tracks of the same length, proving it's actually responding to the
    # local energy rather than defaulting to one end.
    beat_times = [float(i) for i in range(16)]
    low_count = len(adaptive_cut_times(beat_times, [0.0] * 16, 1, 4))
    high_count = len(adaptive_cut_times(beat_times, [1.0] * 16, 1, 4))
    mixed_energy = [0.0] * 5 + [1.0] * 6 + [0.0] * 5
    mixed_count = len(adaptive_cut_times(beat_times, mixed_energy, 1, 4))
    assert low_count < mixed_count < high_count


def test_min_beats_is_floored_at_one():
    beat_times = [0.0, 1.0, 2.0, 3.0]
    cuts = adaptive_cut_times(beat_times, [1.0] * 4, min_beats=0, max_beats=4)
    # a min_beats of 0 would infinite-loop; must be floored to 1
    assert cuts == beat_times


def test_max_beats_cannot_be_below_min_beats():
    beat_times = [float(i) for i in range(10)]
    # deliberately pass max < min; should behave as if max == min
    cuts = adaptive_cut_times(beat_times, [0.0] * 10, min_beats=3, max_beats=1)
    assert cuts == [0.0, 3.0, 6.0, 9.0]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK: {t.__name__}")
    print(f"\n{len(tests)} tests passed.")
