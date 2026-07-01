FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

# jammy ships python3.10/3.11 only; deadsnakes provides 3.12 to satisfy requires-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common curl ffmpeg && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY aavaaz/ aavaaz/

RUN python3.12 -m pip install --no-cache-dir .[whisper]

EXPOSE 9090 8000

ENTRYPOINT ["aavaaz", "serve"]
CMD ["--model", "large-v3"]
