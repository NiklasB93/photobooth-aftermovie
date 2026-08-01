"""Beat detection on a music track, used to decide when the video should cut to the next photo."""

from dataclasses import dataclass

import librosa
import numpy as np


@dataclass
class BeatInfo:
    tempo: float
    beat_times: list[float]
    cut_times: list[float]
    duration: float


def detect_beats(audio_path: str, beats_per_cut: int = 2) -> BeatInfo:
    """Load an audio file and return beat/cut timestamps in seconds.

    beats_per_cut controls how often the photo changes: 1 = every beat
    (frantic), 2 = every other beat (typical), 4 = every bar in 4/4 time
    (slower, more cinematic).
    """
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    cut_times = beat_times[::beats_per_cut]
    if len(cut_times) == 0 or cut_times[0] > 0.05:
        cut_times = np.insert(cut_times, 0, 0.0)

    return BeatInfo(
        tempo=tempo,
        beat_times=beat_times.tolist(),
        cut_times=cut_times.tolist(),
        duration=duration,
    )
