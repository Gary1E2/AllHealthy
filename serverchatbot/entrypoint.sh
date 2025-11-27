#!/bin/bash
set -e

MODEL_DIR="/app/models/Qwen3-VL-8B-Instruct"

echo "==============================================="
echo " LLM Server Startup Process"
echo "==============================================="

if [ ! -d "$MODEL_DIR" ]; then
    echo "Model not found in $MODEL_DIR"
    echo "Running model_download.py..."
    python3 model_download.py

    if [ $? -ne 0 ]; then
        echo "Model download failed."
        exit 1
    fi
    echo "Model download complete."
else
    echo "Model already exists at $MODEL_DIR"
fi

echo "Starting serverchatbot.py..."
exec python3 serverchatbot.py
