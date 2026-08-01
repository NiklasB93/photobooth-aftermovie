"""Assembles a list of photos into a vertical, beat-cut video with a subtle Ken Burns
zoom on each photo, and attaches the source audio track.
"""

from pathlib import Path

import numpy as np
from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips
from PIL import Image

TARGET_W, TARGET_H = 1080, 1920  # 9:16, matches TikTok/Reels/Shorts


def _cover_fit(image_path: Path, w: int, h: int) -> np.ndarray:
    """Center-crop + scale an arbitrary photo to exactly fill a w x h canvas."""
    img = Image.open(image_path).convert("RGB")
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left, top = (new_w - w) // 2, (new_h - h) // 2
    img = img.crop((left, top, left + w, top + h))
    return np.array(img)


def _ken_burns_clip(
    image_path: Path, duration: float, w: int, h: int, zoom_end: float, zoom_in: bool
) -> CompositeVideoClip:
    duration = max(duration, 0.05)
    frame = _cover_fit(image_path, w, h)
    base = ImageClip(frame).with_duration(duration)

    if zoom_in:
        scale_fn = lambda t: 1.0 + (zoom_end - 1.0) * (t / duration)
    else:
        scale_fn = lambda t: zoom_end - (zoom_end - 1.0) * (t / duration)

    zoomed = base.resized(scale_fn).with_position("center")
    return CompositeVideoClip([zoomed], size=(w, h)).with_duration(duration)


def build_clips(
    photo_paths: list[Path],
    cut_times: list[float],
    total_duration: float,
    w: int = TARGET_W,
    h: int = TARGET_H,
    zoom_end: float = 1.08,
) -> list[CompositeVideoClip]:
    """Turn cut timestamps + a photo pool into a sequence of Ken-Burns clips.

    Photos are cycled through in order if there are more segments than photos.
    """
    boundaries = [t for t in cut_times if t < total_duration] + [total_duration]
    n_photos = len(photo_paths)
    clips = []
    for i in range(len(boundaries) - 1):
        seg_duration = boundaries[i + 1] - boundaries[i]
        if seg_duration <= 0.03:
            continue
        photo = photo_paths[i % n_photos]
        clips.append(
            _ken_burns_clip(photo, seg_duration, w, h, zoom_end, zoom_in=(i % 2 == 0))
        )
    if not clips:
        raise ValueError("No segments produced — check cut_times/total_duration.")
    return clips


def render(
    clips: list[CompositeVideoClip],
    audio_path: Path,
    total_duration: float,
    output_path: Path,
    fps: int = 30,
):
    video = concatenate_videoclips(clips, method="chain")
    audio = AudioFileClip(str(audio_path)).subclipped(0, total_duration)
    video = video.with_audio(audio)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,
    )
    video.close()
    audio.close()
