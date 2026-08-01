import argparse
import random
import sys
from pathlib import Path

from .beats import detect_beats
from .video import TARGET_H, TARGET_W, build_clips, render

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


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aftermovie",
        description=(
            "Turn a folder of event photos into a vertical, beat-synced video "
            "(cuts to the next photo on the music's beat) for TikTok/Reels/Shorts."
        ),
    )
    parser.add_argument("photos_dir", type=Path, help="Folder of photos (jpg/png/webp)")
    parser.add_argument("audio_path", type=Path, help="Music track (mp3/wav/m4a/...)")
    parser.add_argument("output_path", type=Path, help="Output file, e.g. aftermovie.mp4")
    parser.add_argument(
        "--beats-per-cut",
        type=int,
        default=2,
        help="Change photo every N beats (default: 2). 1=frantic, 4=slower/cinematic.",
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
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)

    if not args.photos_dir.is_dir():
        raise SystemExit(f"{args.photos_dir} is not a directory")
    if not args.audio_path.is_file():
        raise SystemExit(f"{args.audio_path} not found")
    if args.beats_per_cut < 1:
        raise SystemExit("--beats-per-cut must be >= 1")

    photos = collect_photos(args.photos_dir, args.order)
    print(f"Found {len(photos)} photos in {args.photos_dir}")

    print("Detecting beats...")
    info = detect_beats(str(args.audio_path), beats_per_cut=args.beats_per_cut)
    total_duration = min(info.duration, args.max_duration)
    print(
        f"Tempo ~{info.tempo:.1f} BPM, {len(info.cut_times)} candidate cuts, "
        f"using first {total_duration:.1f}s of audio."
    )

    clips = build_clips(
        photos, info.cut_times, total_duration, TARGET_W, TARGET_H, zoom_end=args.zoom
    )
    print(f"Rendering {len(clips)} segments -> {args.output_path} ...")
    render(clips, args.audio_path, total_duration, args.output_path, fps=args.fps)
    print(f"Done: {args.output_path}")


if __name__ == "__main__":
    main()
