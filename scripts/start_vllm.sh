#!/bin/bash
# Start vLLM synthesis servers on 16 GPUs
# GPUs 0-3:   Qwen2.5-72B text reasoning (port 8001)
# GPUs 4-7:   Qwen2.5-72B text reasoning (port 8002)
# GPUs 8-11:  Qwen2.5-Coder-72B exploit code (port 8003)
# GPUs 12-15: Qwen2.5-Coder-72B exploit code (port 8004)

set -e
echo "Starting FlagFoundry vLLM synthesis servers..."

VLLM_KEY="${VLLM_API_KEY:-flagfoundry_synthesis_key}"

# Instance 1: Reasoning synthesis
CUDA_VISIBLE_DEVICES=0,1,2,3 python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-72B-Instruct \
  --tensor-parallel-size 4 \
  --port 8001 \
  --api-key "$VLLM_KEY" \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --served-model-name "Qwen/Qwen2.5-72B-Instruct" &

echo "  Instance 1 (reasoning) starting on port 8001 (PIDs: GPUs 0-3)..."
sleep 5

# Instance 2: Reasoning synthesis (parallel)
CUDA_VISIBLE_DEVICES=4,5,6,7 python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-72B-Instruct \
  --tensor-parallel-size 4 \
  --port 8002 \
  --api-key "$VLLM_KEY" \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --served-model-name "Qwen/Qwen2.5-72B-Instruct" &

echo "  Instance 2 (reasoning) starting on port 8002 (PIDs: GPUs 4-7)..."
sleep 5

# Instance 3: Exploit code synthesis
CUDA_VISIBLE_DEVICES=8,9,10,11 python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-32B-Instruct \
  --tensor-parallel-size 4 \
  --port 8003 \
  --api-key "$VLLM_KEY" \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --served-model-name "Qwen/Qwen2.5-Coder-32B-Instruct" &

echo "  Instance 3 (exploit code) starting on port 8003 (PIDs: GPUs 8-11)..."
sleep 5

# Instance 4: Exploit code synthesis (parallel)
CUDA_VISIBLE_DEVICES=12,13,14,15 python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-32B-Instruct \
  --tensor-parallel-size 4 \
  --port 8004 \
  --api-key "$VLLM_KEY" \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --served-model-name "Qwen/Qwen2.5-Coder-32B-Instruct" &

echo "  Instance 4 (exploit code) starting on port 8004 (PIDs: GPUs 12-15)..."

echo ""
echo "All vLLM servers launched. Waiting 60s for startup..."
sleep 60

echo "Checking health..."
for port in 8001 8002 8003 8004; do
  if curl -s "http://localhost:$port/health" &>/dev/null; then
    echo "  port $port: OK"
  else
    echo "  port $port: NOT READY (may still be loading)"
  fi
done

echo ""
echo "vLLM servers ready for synthesis."
echo "To stop: pkill -f 'vllm.entrypoints'"
