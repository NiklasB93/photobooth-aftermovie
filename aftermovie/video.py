"""Assembles a list of photos into a video, in one of two modes:

- "vertical" (1080x1920, TikTok/Reels/Shorts): photos are cropped to fill
  the frame. Since source photos are typically horizontal, this crops
  along the width — instead of a blind center-crop (which regularly cut
  people out of frame), we detect faces and either center on them
  statically, or slowly pan across them if they're spread wider than one
  crop window, always clamped so the pan never drifts into empty
  background beyond the detected faces.
- "horizontal" (1920x1080, for a website/wide screen): photos are shown
  in full, uncropped, letterboxed onto a blurred/darkened copy of the
  same photo as a backdrop instead of plain bars.

Both modes apply a subtle Ken Burns zoom for segments that don't pan.
"""

from pathlib import Path

import numpy as np
from moviepy import CompositeVideoClip, ImageClip, concatenate_videoclips, AudioFileClip
from PIL import Image, ImageEnhance, ImageFilter

from .faces import detect_face_bbox

MODE_DIMS = {
    "vertical": (1080, 1920),
    "horizontal": (1920, 1080),
}

# Backward-compatible names (vertical mode was previously the only mode).
TARGET_W, TARGET_H = MODE_DIMS["vertical"]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_pan_offsets(
    scaled_w: int,
    target_w: int,
    face_bbox: tuple[float, float, float, float] | None,
    margin_frac: float = 0.15,
) -> tuple[float, float]:
    """Given a horizontally-oversized frame (scaled_w >= target_w) and an
    optional face bounding box in that same coordinate space, return
    (start_x, end_x): the x-offset of the target_w-wide crop window's left
    edge at the start and end of the clip.

    - No horizontal room to pan, or no face detected -> centered static
      crop (start == end).
    - Face(s) already fit inside one crop window (plus margin) -> static
      crop centered on them, no pointless panning (start == end).
    - Face(s) span wider than one window -> pan between showing the
      leftmost and rightmost face, each kept `margin_frac * target_w`
      pixels clear of the frame edge, and always clamped to
      [0, scaled_w - target_w] so it never shows past the real image.
    """
    max_offset = max(scaled_w - target_w, 0)
    if max_offset == 0 or face_bbox is None:
        center = max_offset / 2
        return center, center

    left, _, right, _ = face_bbox
    margin = margin_frac * target_w
    start = _clamp(left - margin, 0, max_offset)
    end = _clamp(right + margin - target_w, 0, max_offset)

    if end <= start:
        center = _clamp((left + right) / 2 - target_w / 2, 0, max_offset)
        return center, center

    return start, end


def _zoom_clip_from_frame(
    frame: np.ndarray, duration: float, w: int, h: int, zoom_end: float, zoom_in: bool
) -> CompositeVideoClip:
    base = ImageClip(frame).with_duration(duration)
    if zoom_in:
        scale_fn = lambda t: 1.0 + (zoom_end - 1.0) * (t / duration)
    else:
        scale_fn = lambda t: zoom_end - (zoom_end - 1.0) * (t / duration)
    zoomed = base.resized(scale_fn).with_position("center")
    return CompositeVideoClip([zoomed], size=(w, h)).with_duration(duration)


def _build_vertical_segment(
    image_path: Path,
    duration: float,
    w: int,
    h: int,
    zoom_end: float,
    zoom_in: bool,
    face_margin: float,
) -> CompositeVideoClip:
    img = Image.open(image_path).convert("RGB")
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    scaled_w, scaled_h = round(src_w * scale), round(src_h * scale)
    scaled_img = img.resize((scaled_w, scaled_h), Image.LANCZOS)

    try:
        raw_bbox = detect_face_bbox(np.array(img))
    except Exception:
        raw_bbox = None
    face_bbox_scaled = None
    if raw_bbox is not None:
        left, top, right, bottom = raw_bbox
        face_bbox_scaled = (left * scale, top * scale, right * scale, bottom * scale)

    start_x, end_x = compute_pan_offsets(scaled_w, w, face_bbox_scaled, face_margin)

    max_y_offset = max(scaled_h - h, 0)
    if face_bbox_scaled is not None:
        _, top, _, bottom = face_bbox_scaled
        y = _clamp((top + bottom) / 2 - h / 2, 0, max_y_offset)
    else:
        y = max_y_offset / 2

    if end_x - start_x > 1:  # meaningful horizontal room to pan across
        arr = np.array(scaled_img)
        base = ImageClip(arr).with_duration(duration)
        pos_fn = lambda t: (-(start_x + (end_x - start_x) * (t / duration)), -y)
        positioned = base.with_position(pos_fn)
        return CompositeVideoClip([positioned], size=(w, h)).with_duration(duration)

    left = int(_clamp(round(start_x), 0, scaled_w - w))
    top = int(_clamp(round(y), 0, scaled_h - h))
    cropped = scaled_img.crop((left, top, left + w, top + h))
    return _zoom_clip_from_frame(np.array(cropped), duration, w, h, zoom_end, zoom_in)


def _contain_with_blur_backdrop(image_path: Path, w: int, h: int) -> np.ndarray:
    img = Image.open(image_path).convert("RGB")
    src_w, src_h = img.size

    bg_scale = max(w / src_w, h / src_h)
    bg_w, bg_h = round(src_w * bg_scale), round(src_h * bg_scale)
    bg = img.resize((bg_w, bg_h), Image.LANCZOS)
    left, top = (bg_w - w) // 2, (bg_h - h) // 2
    bg = bg.crop((left, top, left + w, top + h))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=max(w, h) // 40))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)

    fg_scale = min(w / src_w, h / src_h)
    fg_w, fg_h = round(src_w * fg_scale), round(src_h * fg_scale)
    fg = img.resize((fg_w, fg_h), Image.LANCZOS)

    canvas = bg.copy()
    canvas.paste(fg, ((w - fg_w) // 2, (h - fg_h) // 2))
    return np.array(canvas)


def _build_horizontal_segment(
    image_path: Path, duration: float, w: int, h: int, zoom_end: float, zoom_in: bool
) -> CompositeVideoClip:
    frame = _contain_with_blur_backdrop(image_path, w, h)
    return _zoom_clip_from_frame(frame, duration, w, h, zoom_end, zoom_in)


def build_clips(
    photo_paths: list[Path],
    cut_times: list[float],
    total_duration: float,
    mode: str = "vertical",
    zoom_end: float = 1.08,
    face_margin: float = 0.15,
) -> list[CompositeVideoClip]:
    """Turn cut timestamps + a photo pool into a sequence of clips.

    Photos are cycled through in order if there are more segments than photos.
    """
    if mode not in MODE_DIMS:
        raise ValueError(f"mode must be one of {list(MODE_DIMS)}, got {mode!r}")
    w, h = MODE_DIMS[mode]

    boundaries = [t for t in cut_times if t < total_duration] + [total_duration]
    n_photos = len(photo_paths)
    clips = []
    for i in range(len(boundaries) - 1):
        seg_duration = boundaries[i + 1] - boundaries[i]
        if seg_duration <= 0.03:
            continue
        photo = photo_paths[i % n_photos]
        zoom_in = i % 2 == 0
        if mode == "vertical":
            clips.append(
                _build_vertical_segment(photo, seg_duration, w, h, zoom_end, zoom_in, face_margin)
            )
        else:
            clips.append(
                _build_horizontal_segment(photo, seg_duration, w, h, zoom_end, zoom_in)
            )
    if not clips:
        raise ValueError("No segments produced — check cut_times/total_duration.")
    return clips


def render(
    clips: list[CompositeVideoClip],
    output_path: Path,
    fps: int = 30,
    audio_path: Path | None = None,
    total_duration: float | None = None,
):
    """Render clips to a video file.

    If audio_path is None, the output is silent — used for the --mute
    workflow, where the reference track was only used to derive beat
    timing and must not be baked into (and distributed with) the export.
    """
    video = concatenate_videoclips(clips, method="chain")
    audio = None
    write_kwargs = {}
    if audio_path is not None:
        audio = AudioFileClip(str(audio_path)).subclipped(0, total_duration or video.duration)
        video = video.with_audio(audio)
        write_kwargs["audio_codec"] = "aac"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        preset="medium",
        threads=4,
        logger=None,
        **write_kwargs,
    )
    video.close()
    if audio is not None:
        audio.close()
