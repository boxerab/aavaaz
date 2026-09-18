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

# dependencies before the source, against an empty package, so this layer keys on
# pyproject.toml alone. Editing a python file otherwise re-downloads about 4 GB of
# torch and CUDA wheels.
RUN mkdir -p aavaaz && touch aavaaz/__init__.py && \
    python3.12 -m pip install --no-cache-dir .[whisper]

COPY aavaaz/ aavaaz/
RUN python3.12 -m pip install --no-cache-dir --no-deps --force-reinstall .

# an undeclared dependency of the engine only shows up on import
RUN python3.12 -c "import aavaaz.server"

EXPOSE 9090 8000 9100

ENTRYPOINT ["aavaaz", "serve"]
CMD ["--model", "large-v3"]
