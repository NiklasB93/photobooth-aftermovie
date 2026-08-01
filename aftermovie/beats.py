"""Beat detection on a music track, used to decide when the video should cut to the next photo."""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

ANALYSIS_SR = 22050


@dataclass
class BeatInfo:
    tempo: float
    beat_times: list[float]
    cut_times: list[float]
    duration: float


def _extract_audio(input_path: str, out_wav: str) -> None:
    """Pull the audio track out of any container ffmpeg can demux (mp3, wav, m4a,
    or a video file like an OBS .mkv recording) and normalize it to mono PCM wav.

    Doing this explicitly, rather than handing the original file straight to
    librosa, avoids librosa's audioread fallback path — the one that lets it
    read non-wav formats at all — which is deprecated and slated for removal.
    """
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-vn", "-ac", "1", "-ar", str(ANALYSIS_SR), out_wav],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "ffmpeg not found. Install it (apt install ffmpeg / brew install ffmpeg) "
            "to load audio from this file."
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffmpeg failed to extract audio from {input_path}: "
            f"{e.stderr.decode(errors='replace').strip()}"
        ) from e


def detect_beats(audio_path: str, beats_per_cut: int = 2) -> BeatInfo:
    """Load an audio file — or the audio track of a video file, e.g. an OBS
    .mkv recording — and return beat/cut timestamps in seconds.

    beats_per_cut controls how often the photo changes: 1 = every beat
    (frantic), 2 = every other beat (typical), 4 = every bar in 4/4 time
    (slower, more cinematic).
    """
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = str(Path(tmp) / "audio.wav")
        _extract_audio(audio_path, wav_path)
        y, sr = librosa.load(wav_path, sr=ANALYSIS_SR, mono=True)

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
