#!/bin/sh
set -eu
launchctl setenv OLLAMA_NO_CLOUD 1
launchctl setenv OLLAMA_NUM_PARALLEL 1
exec open -a /Applications/Ollama.app
