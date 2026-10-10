#!/bin/bash
set -e

# Base models directory relative to script location
MODELS_DIR="$(cd "$(dirname "$0")/../models" && pwd)"

# Create directories if they do not exist
mkdir -p "$MODELS_DIR/llm"
mkdir -p "$MODELS_DIR/piper"

echo "Downloading Qwen2.5-3B-Instruct-GGUF to $MODELS_DIR/llm/"
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF qwen2.5-3b-instruct-q4_k_m.gguf --local-dir "$MODELS_DIR/llm" --local-dir-use-symlinks False

echo "Downloading Piper voice en_US-ryan-medium to $MODELS_DIR/piper/"
wget -q --show-progress -O "$MODELS_DIR/piper/en_US-ryan-medium.onnx" "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx"
wget -q --show-progress -O "$MODELS_DIR/piper/en_US-ryan-medium.onnx.json" "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json"

echo "Faster-Whisper downloads its own weights automatically."

echo "Stream C complete."
