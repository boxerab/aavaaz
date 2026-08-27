FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# jammy ships python3.10/3.11 only; deadsnakes provides 3.12 to satisfy requires-python
# PyAudio ships no wheel, so portaudio19-dev and a compiler have to be here
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common curl ffmpeg git build-essential portaudio19-dev && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY aavaaz/ aavaaz/

RUN python3.12 -m pip install --no-cache-dir .[whisper]

# pypi whisper-live lacks the hooks aavaaz serve passes, so the fork replaces
# it last and a ref change rebuilds only this layer. force-reinstall because the
# fork carries the same version and pip would otherwise call it already
# satisfied and leave the pypi build in place, and no-deps to keep the
# resolution the layer above settled on
ARG WHISPER_LIVE_SOURCE=git+https://github.com/boxerab/WhisperLive@dev
RUN python3.12 -m pip install --no-cache-dir --force-reinstall --no-deps "$WHISPER_LIVE_SOURCE"

EXPOSE 9090 8000 9100

ENTRYPOINT ["aavaaz", "serve"]
CMD ["--model", "large-v3"]
