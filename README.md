# photobooth-aftermovie

Turns a folder of event photos into a beat-synced video: the image cuts to
the next photo on the beat of the music, with either a face-aware pan (for
vertical/phone output) or a subtle Ken Burns zoom.

Built for [Magic Flamingo Events](https://magic-flamingo-fotobox.de) as a
same-day social recap for events, and as a base for a possible standalone
service for other photobooth businesses later.

## How it works

1. Loads the audio track and detects its tempo/beat timestamps
   ([`librosa`](https://librosa.org)).
2. Picks a cut every N beats (`--beats-per-cut`, default 2) to decide how
   long each photo stays on screen.
3. Cycles through your photos in order, building each into a clip per the
   chosen `--mode` (see below).
4. Concatenates the segments and lays the original audio underneath
   ([`moviepy`](https://zulko.github.io/moviepy/) + `ffmpeg`).

## Output modes

Most event photos are horizontal. Cropping one down to a vertical 9:16
frame with a blind center-crop regularly cuts people out of frame if
they're not dead-center in the original shot. `--mode` controls how that's
handled:

- **`vertical`** (1080x1920, default — TikTok/Reels/Shorts): detects faces
  ([OpenCV](https://opencv.org) Haar cascade, bundled in this repo, no
  model download) and either centers the crop on them statically, or — if
  they're spread wider than one crop window can show — slowly **pans**
  across them instead of zooming. The pan is clamped so it never drifts
  into empty background beyond the detected faces (with `--face-margin`
  clearance on each side), and if no face is detected, it falls back to the
  previous plain centered crop + zoom.
- **`horizontal`** (1920x1080 — for a website): shows the **whole photo,
  uncropped**, letterboxed onto a blurred/darkened copy of the same photo
  as a backdrop instead of plain bars.

Face detection works best on frontal, reasonably well-lit faces — typical
for posed photobooth shots. It'll miss profile shots or bad lighting, in
which case that segment just uses the static center-crop fallback.

## Setup

Requires Python 3.10+ and `ffmpeg` installed on your system (`apt install
ffmpeg` / `brew install ffmpeg`).

The audio file can be a plain track (mp3/wav/m4a/...) or the audio track of
a video file — e.g. an OBS `.mkv` recording of a song playing — ffmpeg
extracts the audio for analysis regardless of container.

```bash
pip install -r requirements.txt
```

## Usage

```bash
python -m aftermovie <photos_dir> <audio_file> <output.mp4>
```

Example:

```bash
python -m aftermovie ./event-photos ./track.mp3 ./aftermovie.mp4 \
    --mode vertical \
    --beats-per-cut 2 \
    --max-duration 45 \
    --zoom 1.1
```

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--mode {vertical,horizontal}` | `vertical` | See "Output modes" above. |
| `--face-margin F` | `0.15` | Vertical mode only: clearance to keep between faces and the frame edge (fraction of frame width) when panning. |
| `--beats-per-cut N` | `2` | Change photo every N beats. `1` = frantic, `4` = slower/cinematic. |
| `--max-duration S` | `60` | Trim output to at most S seconds. |
| `--zoom Z` | `1.08` | Max Ken Burns zoom factor per photo (segments that pan don't also zoom). |
| `--fps N` | `30` | Output frame rate. |
| `--order {sorted,shuffle}` | `sorted` | Photo sequence — alphabetical by filename, or shuffled. |
| `--mute` | off | Export with no audio track (see "trending songs" below). |
| `--offset S` | `0` | Song-time in seconds where `audio_path` begins — only affects the `--mute` sync guide. |
| `--song-name` | — | Song title to include in the `--mute` sync guide. |

Output is an H.264 MP4, ready to upload.

## Using a trending/newest song you don't have rights to embed

There's no reliable database of exact beat-grid timestamps for arbitrary
songs anymore — Spotify permanently killed its Audio Analysis API for new
apps in Nov 2024, and BPM-only databases (GetSongBPM, Tunebat, etc.) give
you a tempo number but not *where* beat 1 falls, which isn't enough for
frame-accurate cuts, especially for something released last week.

The workaround: get a short **reference recording** of the real song (e.g.
play it from Spotify/YouTube and record ~20-30s on your phone), note the
song-time you started recording at, and run:

```bash
python -m aftermovie ./event-photos ./phone-recording.m4a ./aftermovie.mp4 \
    --mute \
    --offset 47 \
    --song-name "Song Title - Artist"
```

This analyzes the recording for beat timing exactly as normal, but the
exported video has **no audio track** — safe to post without owning the
song. It also prints (and saves alongside the video as `<output>.sync.txt`)
a one-line instruction:

> Add "Song Title - Artist" as audio in Instagram/TikTok and set its start
> point to 0:47 — the video's cuts will then line up with the song's beat
> from that point on.

You (or the person posting) then add the real, officially-licensed audio
directly in Instagram/TikTok's own picker and trim it to that start point —
the app supports setting a custom start point when adding trending audio.
The reference recording itself is never embedded or distributed; it's only
used locally to work out the timing.

## Smoke-testing without real assets

`examples/generate_test_assets.py` generates a synthetic 120 BPM click
track and colored placeholder photos, so you can verify the pipeline works
end to end without needing real event photos or a licensed music track:

```bash
python examples/generate_test_assets.py
python -m aftermovie examples/test_assets/photos examples/test_assets/click_120bpm.wav examples/test_assets/out.mp4
```

## Tests

`tests/test_pan_offsets.py` covers the pan-window math directly (no
photos/faces needed — pure input/output on coordinates): no-face fallback,
faces that fit in one window (static, centered), faces spread wide enough
to require panning, and edge-clamping so a pan never requests pixels
outside the actual image.

```bash
python3 tests/test_pan_offsets.py
```

## Music licensing

This tool does not source or license music for you — bring your own audio
file. If you plan to publish or resell videos commercially, make sure you
have the rights to whatever track you use (a royalty-free library such as
Epidemic Sound or Artlist, or your own recording). For personal
social-media posts, it's often simpler to export silent/muted and add a
trending track directly in TikTok/Instagram after upload, which sidesteps
licensing entirely.
