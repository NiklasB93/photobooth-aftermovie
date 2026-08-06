"""Face anonymization for --face-privacy: blur or a drawn smiley over each
detected face, applied to the source photo before it's cropped/panned/zoomed
so the effect naturally scales and moves with the rest of the frame.
"""

from PIL import Image, ImageDraw, ImageFilter

from .faces import BBox


def blur_faces(img: Image.Image, boxes: list[BBox], strength: int = 25) -> Image.Image:
    """Gaussian-blur each face with a soft, feathered-edge oval mask (not a
    hard rectangle) so it reads as an intentional, polished blur rather than
    a crude redaction box. Padded generously to cover hair/forehead/chin,
    since the face cascade's box is tight around eyes-nose-mouth.
    """
    if not boxes:
        return img
    img = img.copy()
    w, h = img.size
    for left, top, right, bottom in boxes:
        bw, bh = right - left, bottom - top
        px0 = max(0, int(left - bw * 0.35))
        px1 = min(w, int(right + bw * 0.35))
        py0 = max(0, int(top - bh * 0.55))  # extra room above for hair/forehead
        py1 = min(h, int(bottom + bh * 0.35))  # a bit less below, for chin only
        if px1 <= px0 or py1 <= py0:
            continue

        region = img.crop((px0, py0, px1, py1))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=strength))

        mask = Image.new("L", region.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, region.size[0], region.size[1]), fill=255)
        feather = max(4, int(min(region.size) * 0.12))
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))

        img.paste(blurred, (px0, py0), mask)
    return img


def _draw_smiley(size: int) -> Image.Image:
    """Render a simple, clean flat-style smiley face at the given pixel size."""
    scale = 4  # supersample, then downscale, for smooth anti-aliased edges
    s = size * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    margin = int(s * 0.04)
    draw.ellipse((margin, margin, s - margin, s - margin), fill=(255, 205, 30, 255))
    # Subtle shading for a touch of depth. Note: PIL's ImageDraw *replaces*
    # the alpha channel rather than blending, so a semi-transparent fill
    # here would punch a translucent hole in the opaque base circle above
    # (this bit me during testing) - use a pre-blended, fully opaque color
    # instead of relying on partial alpha.
    draw.ellipse(
        (margin + s * 0.05, margin + s * 0.08, s - margin - s * 0.05, s - margin),
        fill=(245, 183, 22, 255),
    )

    eye_w, eye_h = s * 0.09, s * 0.14
    eye_y = s * 0.4
    for ex in (s * 0.32, s * 0.68):
        draw.ellipse(
            (ex - eye_w / 2, eye_y - eye_h / 2, ex + eye_w / 2, eye_y + eye_h / 2),
            fill=(60, 40, 20, 255),
        )

    smile_box = (s * 0.27, s * 0.4, s * 0.73, s * 0.8)
    draw.arc(smile_box, start=20, end=160, fill=(60, 40, 20, 255), width=int(s * 0.045))

    return canvas.resize((size, size), Image.LANCZOS)


def emoji_faces(img: Image.Image, boxes: list[BBox], scale: float = 1.4) -> Image.Image:
    """Cover each face with a drawn smiley, sized to comfortably cover the
    whole head (not just the tight cascade box).
    """
    if not boxes:
        return img
    img = img.convert("RGBA")
    for left, top, right, bottom in boxes:
        bw, bh = right - left, bottom - top
        cx, cy = (left + right) / 2, (top + bottom) / 2
        size = max(1, int(max(bw, bh) * scale))
        smiley = _draw_smiley(size)
        img.alpha_composite(smiley, (int(cx - size / 2), int(cy - size / 2)))
    return img.convert("RGB")
