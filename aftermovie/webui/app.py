"""Local web UI for reviewing/adjusting auto-detected face blur/emoji
placement on photos before posting them online.

Run with: python -m aftermovie.webui.app
Then open http://127.0.0.1:5050

Design note: this is deliberately a browser UI over a local Flask server,
not a desktop GUI - so the same code can later run as a real (multi-user,
persistent-storage) cloud service without a rewrite, and works on a phone
today via the same LAN your other photobooth gear is already on. The
in-memory PHOTOS store below is the one piece that's explicitly
local-single-user-only; see the note on it before deploying this anywhere
shared.
"""

import io
import uuid
import zipfile

import numpy as np
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image

from aftermovie.faces import detect_faces
from aftermovie.privacy import blur_faces, emoji_faces

MAX_DISPLAY_DIM = 2000  # cap what we ship to the browser; export uses the original

app = Flask(__name__)

# id -> {"image": PIL.Image (original, full-res), "filename": str}
# In-memory and per-process: fine for one person using this locally. Before
# running this anywhere shared/cloud-hosted, this needs to become
# per-session storage (or at least an eviction policy) - as-is, every
# upload stays in RAM until the process restarts.
PHOTOS: dict[str, dict] = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    results = []
    for f in request.files.getlist("photos"):
        img = Image.open(f.stream).convert("RGB")
        photo_id = uuid.uuid4().hex
        PHOTOS[photo_id] = {"image": img, "filename": f.filename or f"{photo_id}.jpg"}

        try:
            boxes = detect_faces(np.array(img))
        except Exception:
            boxes = []

        results.append(
            {
                "id": photo_id,
                "filename": PHOTOS[photo_id]["filename"],
                "width": img.width,
                "height": img.height,
                "faces": [
                    {"left": l, "top": t, "right": r, "bottom": b} for l, t, r, b in boxes
                ],
            }
        )
    return jsonify({"photos": results})


@app.route("/api/photo/<photo_id>/image")
def photo_image(photo_id):
    entry = PHOTOS.get(photo_id)
    if entry is None:
        return "not found", 404
    img = entry["image"]
    if max(img.size) > MAX_DISPLAY_DIM:
        scale = MAX_DISPLAY_DIM / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


@app.route("/api/export", methods=["POST"])
def export():
    payload = request.get_json(force=True)
    photos_payload = payload.get("photos", [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in photos_payload:
            entry = PHOTOS.get(p.get("id"))
            if entry is None:
                continue
            img = entry["image"]
            w, h = img.size

            blur_boxes = []
            emoji_boxes = []
            for r in p.get("regions", []):
                box = (
                    round(r["left"] * w),
                    round(r["top"] * h),
                    round(r["right"] * w),
                    round(r["bottom"] * h),
                )
                (emoji_boxes if r.get("mode") == "emoji" else blur_boxes).append(box)

            result = img
            if blur_boxes:
                result = blur_faces(result, blur_boxes)
            if emoji_boxes:
                result = emoji_faces(result, emoji_boxes)

            out_buf = io.BytesIO()
            result.save(out_buf, format="JPEG", quality=92)
            zf.writestr(entry["filename"], out_buf.getvalue())

    buf.seek(0)
    return send_file(
        buf, mimetype="application/zip", as_attachment=True, download_name="anonymized_photos.zip"
    )


def main():
    app.run(host="127.0.0.1", port=5050, debug=False)


if __name__ == "__main__":
    main()
