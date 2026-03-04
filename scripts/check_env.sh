#!/bin/bash
# FlagFoundry environment check script
set -e

PASS=0
FAIL=0

check() {
  local name="$1"
  local cmd="$2"
  if eval "$cmd" &>/dev/null; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== FlagFoundry Environment Check ==="
echo ""

echo "Python:"
check "Python 3.11+" "python3 -c 'import sys; sys.exit(0) if sys.version_info >= (3,11) else sys.exit(1)'"
check "pip installed" "pip --version"
echo ""

echo "Python packages:"
check "torch" "python3 -c 'import torch'"
check "transformers" "python3 -c 'import transformers'"
check "peft" "python3 -c 'import peft'"
check "trl" "python3 -c 'import trl'"
check "deepspeed" "python3 -c 'import deepspeed'"
check "pwntools" "python3 -c 'import pwn'"
check "pycryptodome" "python3 -c 'from Crypto.Cipher import AES'"
check "scapy" "python3 -c 'import scapy'"
check "loguru" "python3 -c 'import loguru'"
echo ""

echo "GPU:"
check "CUDA available" "python3 -c 'import torch; assert torch.cuda.is_available()'"
GPU_COUNT=$(python3 -c 'import torch; print(torch.cuda.device_count())' 2>/dev/null || echo "0")
echo "  GPU count: $GPU_COUNT (target: 18)"
echo ""

echo "Docker (required for sandbox execution):"
check "Docker daemon" "docker info"
check "Docker run" "docker run --rm hello-world"
echo ""

echo "Environment variables:"
check "ANTHROPIC_API_KEY" "[ -n \"$ANTHROPIC_API_KEY\" ]"
check "GITHUB_TOKEN" "[ -n \"$GITHUB_TOKEN\" ]"
echo ""

echo "Disk space:"
AVAILABLE=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
echo "  Available: ${AVAILABLE}GB (need: ~500GB for full dataset)"
if [ "$AVAILABLE" -lt 200 ]; then
  echo "  [WARN] Low disk space"
fi
echo ""

echo "=== Summary: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "Fix failures above before running the pipeline."
  exit 1
else
  echo "Environment ready!"
fi
