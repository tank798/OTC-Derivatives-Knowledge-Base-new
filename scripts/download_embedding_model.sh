#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="$ROOT/.cache/huggingface/Xenova/bge-base-zh-v1.5"
REVISION="71e50dc531959f9e04ebf190ea25b00261a0a186"
BASE_URL="https://huggingface.co/Xenova/bge-base-zh-v1.5/resolve/$REVISION"
MODEL_SHA256="b665f3bba56c3119bc76ba131ebcc544d720a7408cb11581bdf354aaa0198d43"

mkdir -p "$MODEL_DIR/onnx"

download() {
  local relative_path="$1"
  local target="$MODEL_DIR/$relative_path"
  if [[ -s "$target" ]]; then
    return
  fi
  curl --fail --location --retry 3 --silent --show-error \
    "$BASE_URL/$relative_path" \
    --output "$target.download"
  mv "$target.download" "$target"
}

download config.json
download tokenizer.json
download tokenizer_config.json
download special_tokens_map.json
download vocab.txt
download quantize_config.json
download onnx/model_quantized.onnx

actual_sha256="$(shasum -a 256 "$MODEL_DIR/onnx/model_quantized.onnx" | awk '{print $1}')"
if [[ "$actual_sha256" != "$MODEL_SHA256" ]]; then
  echo "BGE ONNX SHA-256 mismatch: expected=$MODEL_SHA256 actual=$actual_sha256" >&2
  exit 1
fi

echo "BGE model ready: $MODEL_DIR"
