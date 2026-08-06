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
   long each photo stays on screen — or, with `--adaptive`, varies that
   cadence with the song's own energy (see below).
3. Cycles through your photos in order, building each into a clip per the
   chosen `--mode` (see below).
4. Concatenates the segments and lays the original audio underneath
   ([`moviepy`](https://zulko.github.io/moviepy/) + `ffmpeg`).

## Adaptive cut cadence

By default (`--beats-per-cut`), the photo changes at one fixed rate for
the entire song. `--adaptive` instead follows the song's actual energy —
computed from librosa's onset-strength envelope, averaged per beat and
normalized against the track's own 10th/90th-percentile range — and cuts
faster (`--adaptive-min` beats, default 1) during high-energy stretches
like a chorus/drop, and slower (`--adaptive-max` beats, default 4) during
calmer ones like a verse/intro. It reacts to the energy at each beat as it
goes (no lookahead), so transitions land near section boundaries rather
than exactly on them — still a noticeably better feel than one constant
rate for a whole song with real dynamic range.

```bash
python -m aftermovie ./event-photos ./track.mp3 ./aftermovie.mp4 --adaptive
```

## Output modes

Most event photos are horizontal. Cropping one down to a vertical 9:16
frame with a blind center-crop regularly cuts people out of frame if
they're not dead-center in the original shot. `--mode` controls how that's
handled:

- **`vertical`** (1080x1920, default — TikTok/Reels/Shorts): detects faces
  ([OpenCV](https://opencv.org) DNN face detector, a small SSD model
  vendored in this repo — no runtime model download) and either centers the
  crop on them statically, or — if they're spread wider than one crop
  window can show — slowly **pans** across them instead of zooming. The pan
  is clamped so it never drifts into empty background beyond the detected
  faces (with `--face-margin` clearance on each side), and if no face is
  detected, it falls back to the previous plain centered crop + zoom.
- **`horizontal`** (1920x1080 — for a website): shows the **whole photo,
  uncropped**, letterboxed onto a blurred/darkened copy of the same photo
  as a backdrop instead of plain bars.

Face detection handles tilted/angled heads and varied expressions well
(this repo originally used a Haar cascade, which missed a rotated head
entirely in testing — switched to this DNN model after confirming it
catches that case). Heavy occlusion — sunglasses, an oversized prop
covering much of the face — can still defeat it; that's an inherent limit
of appearance-based face detection, not something any detector fully
solves. A missed face just uses the static center-crop fallback / stays
unobscured under `--face-privacy`.

## Face privacy (`--face-privacy`)

For data protection, `--face-privacy` can obscure every detected face
before it's cropped/panned/zoomed, so the effect moves naturally with the
rest of the frame instead of being pasted on afterward:

- `blur` — a soft, feathered-edge Gaussian blur over each face (padded to
  cover hair/forehead/chin, not just the tight detection box).
- `emoji` — a drawn smiley face over each face, sized to fully cover it.
- `none` (default) — off.

```bash
python -m aftermovie ./event-photos ./track.mp3 ./aftermovie.mp4 --face-privacy blur
```

**Given this exists for data protection, treat it as best-effort, not a
guarantee** — uses the same face detection as the vertical-mode panning
(see "Output modes" above for what it handles well vs. its limits, mainly
heavy occlusion). Spot-check the output before relying on it for actual
privacy compliance, especially on photos with props/sunglasses covering
much of a face.

### Manual review/editing UI

`--face-privacy` on the command line applies to every detected face with no
way to fix a miss or a false positive. For photos going out individually
(not through the video pipeline) — e.g. picking a few shots for a social
post — `aftermovie/webui/` is a local browser tool for that:

```bash
pip install -r requirements.txt -r requirements-webui.txt
python -m aftermovie.webui.app
# open http://127.0.0.1:5050
```

Add multiple photos, review the auto-detected faces (same detector as
`--face-privacy`), and adjust by hand — drag to move, drag the corner to
resize, drag on empty space to add a region the detector missed, × to
remove a false positive, and a per-region toggle to switch that one region
between blur and emoji (so you can mix both in one photo). "Export all"
downloads a `.zip` with the real blur/emoji baked in at full resolution —
the on-screen blur is a live CSS preview, the export re-renders with the
same PIL-based `blur_faces`/`emoji_faces` the CLI uses, so what you get
matches what you saw.

This is a local, single-user tool as-is (an in-memory store keyed to one
Flask process — restarting it loses anything not yet exported). It's built
as a browser UI over a local server specifically so it *could* later run as
a real cloud service — e.g. folded into the photobooth website — without a
rewrite. It's a step closer to that now (see "Deploying to Cloud Run"
below), but still has no auth and no durable storage: anything not yet
exported is lost if the container restarts. Treat it as "one person at a
time," not multi-tenant.

### Deploying to Cloud Run

`Dockerfile` (repo root) packages just the webui — not the CLI, which needs
`ffmpeg`/`librosa`/`moviepy` and is meant to run locally, not as a service —
behind `gunicorn` instead of Flask's dev server.

```bash
gcloud run deploy photobooth-face-privacy \
  --source . \
  --region europe-west1 \
  --memory 1Gi \
  --max-instances 1 \
  --allow-unauthenticated   # or omit + set up IAM, see caveat below
```

**`--max-instances 1` is not just a cost setting here, it's required for
correctness.** Uploaded photos live in an in-memory dict on the Flask app
object (see the module docstring in `aftermovie/webui/app.py`) — the
Dockerfile already pins `gunicorn` to one worker process precisely so that
memory stays consistent within an instance, but Cloud Run can still run
*multiple instances* in parallel under load, each with its own separate
memory. Two instances means an upload can land on one and an export request
on the other, 404ing on a photo that "should" exist. `--max-instances 1`
keeps everything on one instance so this can't happen — at the cost of no
horizontal scaling, which is fine for a single-user tool but would need
fixing (e.g. moving photo storage to Cloud Storage or a database) before
this becomes a real multi-user service.

**`--allow-unauthenticated` is a real tradeoff, not a default to accept
blindly**: this tool has zero authentication of its own, so an
unauthenticated Cloud Run service is reachable by anyone with the URL, and
the photos people upload could contain guests' faces before they're
anonymized. For anything beyond quick personal testing, prefer Cloud Run's
IAM-based access instead (omit `--allow-unauthenticated`, grant
`roles/run.invoker` to your own account, and authenticate requests — e.g.
`gcloud auth print-identity-token` for testing, or Identity-Aware Proxy for
browser access) rather than leaving it open.

## Logo outro (`--logo`)

`--logo path/to/logo.png` appends a closing card after the main content:
your logo (transparent-background PNG recommended — padding baked into the
source file is auto-cropped so sizing is based on the actual visible mark)
centered on a blurred, dimmed still of the video's last frame, fading in
from black. `--logo-duration` controls how long it's shown (default 2.5s).
If the main content has audio, it continues playing under the outro rather
than cutting off abruptly, for as long as the source track has left.

```bash
python -m aftermovie ./event-photos ./track.mp3 ./aftermovie.mp4 --logo ./logo.png --logo-duration 3
```

## Compression (`--compress`)

`--compress {high,web,small}` controls the output encoding tier (all use
H.264 + `+faststart` for progressive playback):

| Tier | CRF | Use case |
|---|---|---|
| `high` (default) | 23 | Matches the previous unconfigured default — no change unless you opt in. |
| `web` | 26 | Noticeably smaller, minimal visible quality loss — good default for social/web upload. |
| `small` | 31 | Much smaller, e.g. for messaging apps with attachment size limits. |

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
| `--beats-per-cut N` | `2` | Fixed cadence: change photo every N beats. `1` = frantic, `4` = slower/cinematic. Ignored if `--adaptive` is set. |
| `--adaptive` | off | Vary the cut cadence with the song's own energy instead of a fixed cadence — see below. |
| `--adaptive-min N` | `1` | With `--adaptive`: fastest cadence (beats/cut) on the highest-energy parts. |
| `--adaptive-max N` | `4` | With `--adaptive`: slowest cadence (beats/cut) on the calmest parts. |
| `--max-duration S` | `60` | Trim output to at most S seconds. |
| `--zoom Z` | `1.08` | Max Ken Burns zoom factor per photo (segments that pan don't also zoom). |
| `--fps N` | `30` | Output frame rate. |
| `--order {sorted,shuffle}` | `sorted` | Photo sequence — alphabetical by filename, or shuffled. |
| `--mute` | off | Export with no audio track (see "trending songs" below). |
| `--offset S` | `0` | Song-time in seconds where `audio_path` begins — only affects the `--mute` sync guide. |
| `--song-name` | — | Song title to include in the `--mute` sync guide. |
| `--face-privacy {none,blur,emoji}` | `none` | Obscure detected faces — see "Face privacy" below. |
| `--logo PATH` | — | Append a logo closing card — see "Logo outro" below. |
| `--logo-duration S` | `2.5` | How long the logo card is shown. |
| `--compress {high,web,small}` | `high` | Output encoding tier — see "Compression" below. |

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
