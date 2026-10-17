#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export GRADIO_SERVER_NAME=127.0.0.1
export GRADIO_SERVER_PORT=7860
export GRADIO_ANALYTICS_ENABLED=false
export ANONYMIZED_TELEMETRY=false
exec .venv/bin/python app.py
