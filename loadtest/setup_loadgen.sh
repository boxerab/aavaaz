#!/bin/bash
# run as the login user, not root
set -euo pipefail

sudo dnf install -y -q git tar
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

cd "$HOME"
[ -d aavaaz ] || git clone -q https://github.com/collabora/aavaaz.git
cd aavaaz
uv sync -q --extra loadtest

mkdir -p "$HOME/.cache/aavaaz-loadtest"
cd "$HOME/.cache/aavaaz-loadtest"
[ -d LibriSpeech/test-clean ] || {
  curl -sSL -o test-clean.tar.gz https://www.openslr.org/resources/12/test-clean.tar.gz
  tar xzf test-clean.tar.gz && rm test-clean.tar.gz
}
cd "$HOME/aavaaz"
uv run loadtest/prepare_audio.py

echo '* soft nofile 1048576' | sudo tee -a /etc/security/limits.conf >/dev/null
echo '* hard nofile 1048576' | sudo tee -a /etc/security/limits.conf >/dev/null
echo "load generator ready, log in again for the file limit to apply"
