"""Generates a synthetic click-track audio file and colored placeholder photos,
so the pipeline can be smoke-tested end-to-end without needing real event photos
or a licensed music track.

Usage:
    python examples/generate_test_assets.py
"""

from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw


def generate_click_track(path: Path, bpm: float = 120.0, duration: float = 20.0, sr: int = 22050):
    beat_interval = 60.0 / bpm
    n_samples = int(duration * sr)
    audio = np.zeros(n_samples, dtype=np.float64)
    click_len = int(0.02 * sr)
    envelope = np.linspace(1.0, 0.0, click_len)
    beat_times = np.arange(0, duration, beat_interval)
    for bt in beat_times:
        start = int(bt * sr)
        end = min(start + click_len, n_samples)
        n = end - start
        if n <= 0:
            continue
        tone = np.sin(2 * np.pi * 1000 * np.arange(n) / sr)
        audio[start:end] += envelope[:n] * tone
    peak = np.max(np.abs(audio)) or 1.0
    audio = (audio / peak) * 0.8
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, sr)


def generate_photos(out_dir: Path, n: int = 8):
    out_dir.mkdir(parents=True, exist_ok=True)
    colors = [
        (230, 126, 34), (41, 128, 185), (39, 174, 96), (142, 68, 173),
        (231, 76, 60), (26, 188, 156), (243, 156, 18), (52, 73, 94),
    ]
    for i in range(n):
        img = Image.new("RGB", (1600, 1200), colors[i % len(colors)])
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, 1560, 1160], outline="white", width=6)
        draw.text((80, 80), f"Photo {i + 1}", fill="white")
        img.save(out_dir / f"{i + 1:02d}.jpg", quality=90)


if __name__ == "__main__":
    base = Path(__file__).parent / "test_assets"
    generate_click_track(base / "click_120bpm.wav", bpm=120.0, duration=20.0)
    generate_photos(base / "photos", n=8)
    print(f"Test assets written to {base}")
    print(
        f"Try: python -m aftermovie {base / 'photos'} {base / 'click_120bpm.wav'} "
        f"{base / 'out.mp4'}"
    )
