"""Builds a closing logo clip appended after the main beat-synced content."""

from pathlib import Path

import numpy as np
from moviepy import CompositeVideoClip, ImageClip
from moviepy.video.fx import FadeIn
from PIL import Image, ImageEnhance, ImageFilter


def build_outro_clip(
    logo_path: Path,
    w: int,
    h: int,
    duration: float,
    background_frame: np.ndarray | None = None,
    fade_duration: float = 0.6,
) -> CompositeVideoClip:
    """A closing clip: your logo centered on a blurred, dimmed copy of the
    video's last frame for visual continuity (or plain black if no frame is
    given), fading in from black.
    """
    if background_frame is not None:
        bg_img = Image.fromarray(background_frame).convert("RGB").resize((w, h))
        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=max(w, h) // 30))
        bg_img = ImageEnhance.Brightness(bg_img).enhance(0.35)
        bg_array = np.array(bg_img)
    else:
        bg_array = np.zeros((h, w, 3), dtype=np.uint8)

    bg_clip = ImageClip(bg_array).with_duration(duration)

    logo_img = Image.open(logo_path).convert("RGBA")
    # Many logo PNGs have transparent padding baked in around the visible
    # mark - crop to the actual visible content first, so `target_w` below
    # reflects what you'll actually see, not the source canvas size.
    visible_bbox = logo_img.split()[-1].getbbox()
    if visible_bbox is not None:
        logo_img = logo_img.crop(visible_bbox)

    target_w = int(w * 0.32)
    scale = target_w / logo_img.width
    logo_img = logo_img.resize((target_w, max(1, round(logo_img.height * scale))), Image.LANCZOS)
    logo_clip = (
        ImageClip(np.array(logo_img))
        .with_duration(duration)
        .with_position("center")
    )

    outro = CompositeVideoClip([bg_clip, logo_clip], size=(w, h)).with_duration(duration)
    return outro.with_effects([FadeIn(min(fade_duration, duration / 2), initial_color=[0, 0, 0])])
