# Edge & Embedded Deployment Guide

Aavaaz can run on edge devices including Raspberry Pi 4/5, NVIDIA Jetson Nano/Xavier/Orin, and other ARM64 platforms.

Both edge images are built on the device or on an arm64 machine. CI publishes only the x86 GPU and CPU images, arm64 emulation on a runner is too slow to be worth it.

## Quick Start

### Raspberry Pi / Generic ARM64

```bash
# Build the edge image (arm64, CPU-only torch)
docker build --platform=linux/arm64 -f Dockerfile.edge -t aavaaz-edge .

# Run with defaults (tiny model, REST on 8000, WebSocket on 9090)
docker run -p 9090:9090 -p 8000:8000 aavaaz-edge

# Limit concurrent clients on a small device
docker run -p 9090:9090 -p 8000:8000 aavaaz-edge \
  --model tiny --max-clients 2
```

### NVIDIA Jetson (with CUDA)

```bash
# Build on the Jetson itself (L4T base ships a CUDA torch)
docker build -f Dockerfile.jetson -t aavaaz-jetson .

# Run with NVIDIA runtime
docker run --runtime nvidia -p 9090:9090 -p 8000:8000 aavaaz-jetson
```

## Model Selection for Edge

| Device | RAM | Recommended Model | Compute Type | Notes |
|--------|-----|-------------------|-------------|-------|
| RPi 4 (4GB) | 4GB | `tiny` | int8 | ~1GB RAM usage |
| RPi 5 (8GB) | 8GB | `base` | int8 | ~2GB RAM usage |
| Jetson Nano | 4GB | `tiny` | float16 | CUDA accelerated |
| Jetson Xavier NX | 8GB | `small` | float16 | CUDA accelerated |
| Jetson Orin | 16-64GB | `medium` or `large-v3` | float16 | Full models |

## Performance Tips

### Reduce Memory Usage
- Use `tiny` or `base` models
- Set `--max-clients 1` or `2` for limited RAM devices
- Leave `--metrics-port` at 0 and skip `--enable-diarization`

### Reduce Latency
- Enable `--noise-reduction near_field` for cleaner input
- Set a lower `--max-connection-time` to free resources faster

### Docker Compose for Edge

```yaml
services:
  aavaaz:
    build:
      context: .
      dockerfile: Dockerfile.edge
    ports:
      - "9090:9090"
      - "8000:8000"
      - "9100:9100"
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2'
    command: >
      --model tiny
      --max-clients 2
      --metrics-port 9100
```

## Without Docker

```bash
git clone https://github.com/collabora/Aavaaz.git
cd Aavaaz
pip install --extra-index-url https://download.pytorch.org/whl/cpu torch
pip install .[whisper]

aavaaz serve --model tiny --backend faster_whisper --max-clients 2
```

## Monitoring on Edge

```bash
docker run -p 9090:9090 -p 8000:8000 -p 9100:9100 aavaaz-edge \
  --metrics-port 9100
```

Access metrics at `http://device-ip:9100/metrics`.

## Tested Platforms

- Raspberry Pi 4 Model B (4GB/8GB) with Raspberry Pi OS 64-bit
- Raspberry Pi 5 (8GB) with Raspberry Pi OS 64-bit
- NVIDIA Jetson Nano (4GB) with JetPack 5.x
- NVIDIA Jetson Xavier NX (8GB) with JetPack 5.x
- NVIDIA Jetson AGX Orin with JetPack 6.x
- Generic x86_64 and ARM64 Linux with Docker
