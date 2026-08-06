# Deploys aftermovie/webui/ (the local face-privacy review UI) as a Cloud Run
# service. This is NOT the video-generation CLI - that needs ffmpeg + the full
# requirements.txt (librosa/moviepy) and is meant to run locally, not as a web
# service. The webui only touches images (opencv/numpy/pillow), so this image
# installs just that, explicitly, rather than the full requirements.txt - keeps
# the image smaller and cold starts faster.
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    flask \
    gunicorn \
    "opencv-python-headless>=4.8,<5" \
    numpy \
    pillow

# Only what the webui actually imports (aftermovie/faces.py, privacy.py, and
# their vendored model files in aftermovie/data/) - not the CLI's beats.py/
# video.py/outro.py/cli.py, so a missing ffmpeg or librosa there never matters
# here. See .dockerignore for what's excluded from the build context entirely.
COPY aftermovie/__init__.py aftermovie/faces.py aftermovie/privacy.py aftermovie/
COPY aftermovie/data/ aftermovie/data/
COPY aftermovie/webui/ aftermovie/webui/

ENV PYTHONUNBUFFERED=1

# Cloud Run sets $PORT (defaults to 8080) and expects the container to listen
# on it - shell-form CMD so that substitution actually happens (exec-form CMD
# does not invoke a shell, so "$PORT" would be passed through literally).
# --workers 1 --threads N (not multiple worker *processes*) is deliberate: the
# webui's photo store is an in-memory dict on the Flask app object, so it must
# stay in one process's memory to work at all - threads share that memory,
# separate worker processes would not. See the README's Cloud Run section for
# why this also means the *service* needs to be pinned to a single instance.
CMD gunicorn --bind :${PORT:-8080} --workers 1 --threads 8 --timeout 120 aftermovie.webui.app:app
