import argparse
import random
import sys
from pathlib import Path

from .beats import detect_beats
from .outro import build_outro_clip
from .video import COMPRESSION_PRESETS, FACE_PRIVACY_MODES, MODE_DIMS, build_clips, render

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def collect_photos(photos_dir: Path, order: str) -> list[Path]:
    photos = sorted(p for p in photos_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not photos:
        raise SystemExit(
            f"No images found in {photos_dir} (looked for {sorted(IMAGE_EXTS)})"
        )
    if order == "shuffle":
        random.shuffle(photos)
    return photos


def _format_mmss(seconds: float) -> str:
    seconds = max(0, round(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def write_sync_guide(output_path: Path, offset: float, song_name: str | None) -> tuple[Path, str]:
    label = song_name or "the reference track"
    start = _format_mmss(offset)
    message = (
        f'This video is silent and was cut to the beat of "{label}".\n'
        f'To sync it: add "{label}" as audio in Instagram/TikTok and set its start '
        f"point to {start} — the video's cuts will then line up with the song's "
        f"beat from that point on.\n"
    )
    guide_path = output_path.with_suffix(".sync.txt")
    guide_path.write_text(message)
    return guide_path, message


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aftermovie",
        description=(
            "Turn a folder of event photos into a vertical, beat-synced video "
            "(cuts to the next photo on the music's beat) for TikTok/Reels/Shorts."
        ),
    )
    parser.add_argument("photos_dir", type=Path, help="Folder of photos (jpg/png/webp)")
    parser.add_argument(
        "audio_path",
        type=Path,
        help=(
            "Audio to analyze for beat timing (mp3/wav/m4a/...). Can be a track you have "
            "rights to embed, or a personal reference recording of a song you don't "
            "(use with --mute so it never gets baked into the export)."
        ),
    )
    parser.add_argument("output_path", type=Path, help="Output file, e.g. aftermovie.mp4")
    parser.add_argument(
        "--mode",
        choices=list(MODE_DIMS),
        default="vertical",
        help=(
            "vertical (1080x1920, default): cropped for phone/TikTok/Reels, with "
            "face-aware panning instead of a blind center-crop. "
            "horizontal (1920x1080): uncropped, for a website — photos are shown in "
            "full, letterboxed onto a blurred backdrop."
        ),
    )
    parser.add_argument(
        "--face-margin",
        type=float,
        default=0.15,
        help=(
            "In vertical mode, how much clearance (as a fraction of frame width) to "
            "keep between detected faces and the frame edge when panning (default: 0.15)."
        ),
    )
    parser.add_argument(
        "--beats-per-cut",
        type=int,
        default=2,
        help=(
            "Fixed cadence: change photo every N beats (default: 2). "
            "1=frantic, 4=slower/cinematic. Ignored if --adaptive is set."
        ),
    )
    parser.add_argument(
        "--adaptive",
        action="store_true",
        help=(
            "Vary the cut cadence with the song's own energy instead of a fixed "
            "--beats-per-cut: faster cuts on high-energy stretches (chorus/drop), "
            "slower on calmer ones (verse/intro)."
        ),
    )
    parser.add_argument(
        "--adaptive-min",
        type=int,
        default=1,
        help="With --adaptive: fastest cadence, in beats per cut, on the highest-energy parts (default: 1).",
    )
    parser.add_argument(
        "--adaptive-max",
        type=int,
        default=4,
        help="With --adaptive: slowest cadence, in beats per cut, on the calmest parts (default: 4).",
    )
    parser.add_argument(
        "--mute",
        action="store_true",
        help=(
            "Export without any audio track. Use this when audio_path is only a "
            "personal reference recording of a song you don't have rights to "
            "distribute — prints/saves a sync guide instead of embedding audio."
        ),
    )
    parser.add_argument(
        "--offset",
        type=float,
        default=0.0,
        help=(
            "Song-time in seconds where audio_path's recording begins (e.g. you "
            "started recording at the 0:47 mark of the real track). Only used to "
            "compute the --mute sync guide; does not affect beat detection."
        ),
    )
    parser.add_argument(
        "--song-name",
        default=None,
        help='Song title for the printed sync guide, e.g. "Song Title - Artist".',
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=60.0,
        help="Trim output to at most this many seconds (default: 60, good for shorts).",
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--zoom",
        type=float,
        default=1.08,
        help="Max Ken Burns zoom factor applied per photo (default: 1.08).",
    )
    parser.add_argument(
        "--order",
        choices=["sorted", "shuffle"],
        default="sorted",
        help="Photo sequence: alphabetical by filename, or shuffled (default: sorted).",
    )
    parser.add_argument(
        "--face-privacy",
        choices=FACE_PRIVACY_MODES,
        default="none",
        help=(
            "Obscure detected faces for data protection: 'blur' (soft, feathered-edge "
            "blur) or 'emoji' (a drawn smiley over each face). Default 'none'. Applied "
            "to the source photo before cropping/panning/zoom, so it moves naturally "
            "with the rest of the frame."
        ),
    )
    parser.add_argument(
        "--logo",
        type=Path,
        default=None,
        help=(
            "Path to a logo image (PNG with transparency recommended) to show as a "
            "closing card after the main content, centered on a blurred still of the "
            "video's last frame."
        ),
    )
    parser.add_argument(
        "--logo-duration",
        type=float,
        default=2.5,
        help="How long the logo closing card is shown, in seconds (default: 2.5).",
    )
    parser.add_argument(
        "--compress",
        choices=list(COMPRESSION_PRESETS),
        default="high",
        help=(
            "Output compression tier: 'high' (default, unchanged from before), "
            "'web' (noticeably smaller, minimal visible quality loss), 'small' "
            "(much smaller, e.g. for messaging apps with size limits)."
        ),
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)

    if not args.photos_dir.is_dir():
        raise SystemExit(f"{args.photos_dir} is not a directory")
    if not args.audio_path.is_file():
        raise SystemExit(f"{args.audio_path} not found")
    if args.beats_per_cut < 1:
        raise SystemExit("--beats-per-cut must be >= 1")
    if args.adaptive_min < 1:
        raise SystemExit("--adaptive-min must be >= 1")
    if args.logo is not None and not args.logo.is_file():
        raise SystemExit(f"--logo {args.logo} not found")

    photos = collect_photos(args.photos_dir, args.order)
    print(f"Found {len(photos)} photos in {args.photos_dir}")

    print("Detecting beats..." + (" (adaptive cadence)" if args.adaptive else ""))
    info = detect_beats(
        str(args.audio_path),
        beats_per_cut=args.beats_per_cut,
        adaptive=args.adaptive,
        adaptive_min=args.adaptive_min,
        adaptive_max=args.adaptive_max,
    )
    total_duration = min(info.duration, args.max_duration)
    print(
        f"Tempo ~{info.tempo:.1f} BPM, {len(info.cut_times)} candidate cuts, "
        f"using first {total_duration:.1f}s of audio."
    )

    clips = build_clips(
        photos,
        info.cut_times,
        total_duration,
        mode=args.mode,
        zoom_end=args.zoom,
        face_margin=args.face_margin,
        face_privacy=args.face_privacy,
    )
    w, h = MODE_DIMS[args.mode]

    if args.logo is not None:
        print(f"Adding logo outro ({args.logo_duration}s) from {args.logo} ...")
        last_frame = clips[-1].get_frame(max(0.0, clips[-1].duration - 0.05))
        clips.append(
            build_outro_clip(args.logo, w, h, args.logo_duration, background_frame=last_frame)
        )

    print(f"Rendering {len(clips)} segments ({args.mode}, {w}x{h}) -> {args.output_path} ...")

    if args.mute:
        render(clips, args.output_path, fps=args.fps, compression=args.compress)
        guide_path, message = write_sync_guide(args.output_path, args.offset, args.song_name)
        print(f"Done (silent): {args.output_path}")
        print(message)
        print(f"(sync guide also saved to {guide_path})")
    else:
        render(
            clips,
            args.output_path,
            fps=args.fps,
            audio_path=args.audio_path,
            compression=args.compress,
        )
        print(f"Done: {args.output_path}")


if __name__ == "__main__":
    main()
