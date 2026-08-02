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
    beat_energy: list[float]  # normalized 0..1 per beat_times entry; empty if not adaptive


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


def _per_beat_energy(y: np.ndarray, sr: int, beat_times: np.ndarray, duration: float) -> np.ndarray:
    """Return a 0..1 energy value per beat, from the onset-strength envelope
    averaged over each beat's time window and normalized against the song's
    own 10th/90th percentile range (robust to one loud hit or a silent
    intro skewing a plain min/max).
    """
    if len(beat_times) == 0:
        return np.array([])

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.times_like(onset_env, sr=sr)

    boundaries = np.append(beat_times, duration)
    energies = np.zeros(len(beat_times))
    for i in range(len(beat_times)):
        mask = (onset_times >= boundaries[i]) & (onset_times < boundaries[i + 1])
        seg = onset_env[mask]
        energies[i] = seg.mean() if len(seg) else 0.0

    lo, hi = np.percentile(energies, 10), np.percentile(energies, 90)
    if hi - lo < 1e-9:
        return np.full(len(energies), 0.5)
    return np.clip((energies - lo) / (hi - lo), 0.0, 1.0)


def adaptive_cut_times(
    beat_times: list[float] | np.ndarray,
    beat_energy: list[float] | np.ndarray,
    min_beats: int,
    max_beats: int,
) -> list[float]:
    """Walk through beats, cutting sooner (min_beats) during high-energy
    stretches and later (max_beats) during calmer ones, instead of a fixed
    stride. Pure function of (beat_times, beat_energy) so it's testable
    without any real audio.
    """
    beat_times = list(beat_times)
    beat_energy = list(beat_energy)
    if not beat_times:
        return []
    min_beats = max(1, min_beats)
    max_beats = max(min_beats, max_beats)

    cut_times = []
    i = 0
    n = len(beat_times)
    while i < n:
        cut_times.append(float(beat_times[i]))
        energy = beat_energy[i] if i < len(beat_energy) else 0.5
        # high energy -> short span (fast cuts), low energy -> long span (slow cuts)
        span = round(max_beats - energy * (max_beats - min_beats))
        i += max(min_beats, span)
    return cut_times


def _with_leading_zero(cut_times: list[float]) -> list[float]:
    if not cut_times or cut_times[0] > 0.05:
        return [0.0] + cut_times
    return cut_times


def detect_beats(
    audio_path: str,
    beats_per_cut: int = 2,
    adaptive: bool = False,
    adaptive_min: int = 1,
    adaptive_max: int = 4,
) -> BeatInfo:
    """Load an audio file — or the audio track of a video file, e.g. an OBS
    .mkv recording — and return beat/cut timestamps in seconds.

    beats_per_cut controls a fixed cadence: change photo every N beats
    (1 = every beat/frantic, 4 = every bar/slower, cinematic). Ignored if
    adaptive is True.

    adaptive, if True, instead varies the cadence by the song's own energy:
    faster cuts (down to adaptive_min beats) during high-energy stretches
    like a chorus/drop, slower cuts (up to adaptive_max beats) during
    calmer ones.
    """
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = str(Path(tmp) / "audio.wav")
        _extract_audio(audio_path, wav_path)
        y, sr = librosa.load(wav_path, sr=ANALYSIS_SR, mono=True)

    duration = librosa.get_duration(y=y, sr=sr)

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    beat_energy = np.array([])
    if adaptive:
        beat_energy = _per_beat_energy(y, sr, beat_times, duration)
        cut_times = adaptive_cut_times(beat_times, beat_energy, adaptive_min, adaptive_max)
    else:
        cut_times = beat_times[::beats_per_cut].tolist()

    cut_times = _with_leading_zero(cut_times)

    return BeatInfo(
        tempo=tempo,
        beat_times=beat_times.tolist(),
        cut_times=cut_times,
        duration=duration,
        beat_energy=beat_energy.tolist(),
    )
