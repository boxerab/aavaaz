FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3-pip ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY aavaaz/ aavaaz/

RUN pip install --no-cache-dir .

EXPOSE 9090 8000

ENTRYPOINT ["aavaaz", "serve"]
CMD ["--model", "large-v3"]
