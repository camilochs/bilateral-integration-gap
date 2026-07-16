#!/usr/bin/env bash
# Install everything needed to RE-RUN the experiment from scratch.
# (To only reproduce the paper's numbers from the shipped run, you need none of this —
#  just: python3 corpus.py && python3 test_scoring.py && python3 analyze.py)
set -euo pipefail

echo ">> Python dependencies"
python3 -m pip install -r requirements.txt

if ! command -v ollama >/dev/null 2>&1; then
  echo "!! Ollama is not installed. Install it from https://ollama.com and re-run this script."
  echo "   (Ollama serves the five local models over an OpenAI-compatible endpoint.)"
  exit 1
fi

echo ">> Pulling the five local models used in the paper (this downloads several GB)"
for m in gemma2:2b qwen2.5:7b llama3.1:8b mistral-nemo:12b qwen2.5:14b; do
  echo "   - $m"
  ollama pull "$m"
done

echo
echo ">> Local models ready."
echo ">> For the frontier model (Opus 4.8), export your Anthropic key before running:"
echo "     export ANTHROPIC_API_KEY=..."
echo ">> Then reproduce the full run with:"
echo "     MODELS=\"gemma2:2b,qwen2.5:7b,llama3.1:8b,mistral-nemo:12b,qwen2.5:14b,claude-opus-4-8\" \\"
echo "       N_RUNS=3 ROUNDS=3 python3 harness.py"
