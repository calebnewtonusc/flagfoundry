#!/bin/bash
# FlagFoundry — Full pipeline: discovery → synthesis → train SFT → train RL → train DPO
# Runtime: ~36 hours on 18× A6000
#
# Resume from a stage: FROM_STAGE=3 ./scripts/run_all.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

FROM_STAGE="${FROM_STAGE:-1}"

# Load environment
if [ -f .env ]; then
    set -a; source .env; set +a
else
    echo "ERROR: .env file not found. Copy .env.example and fill in your keys."
    exit 1
fi

echo "=== Validating environment ==="
bash scripts/check_env.sh

echo ""
echo "=== FlagFoundry Full Pipeline ==="
echo "Started: $(date)"
echo "Resuming from stage: $FROM_STAGE"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 DISCOVER — Crawl CTFtime, HTB, picoCTF, GitHub CTF repos
# ─────────────────────────────────────────────────────────────────────────────
if [ "$FROM_STAGE" -le 1 ]; then
    echo "━━━ STEP 1 DISCOVER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    echo "  [1/4] Crawling CTFtime writeups (years 2018-2025)..."
    python discovery/ctftime_crawler.py \
        --years $(seq 2018 2025) \
        --workers 30 \
        --output-dir data/raw/ctftime

    echo "  [2/4] Downloading HackTheBox writeups..."
    python discovery/htb_crawler.py \
        --output-dir data/raw/htb

    echo "  [3/4] Downloading picoCTF archives..."
    python discovery/picoctf_downloader.py \
        --output-dir data/raw/picoctf

    echo "  [4/4] Crawling GitHub CTF writeup repositories..."
    python discovery/github_ctf_repos.py \
        --output data/raw/github_ctf \
        --max-repos 5000 \
        --max-files-per-repo 50

    echo ""
    echo "  STEP 1 DISCOVER complete: $(date)"
    echo ""
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 SYNTHESIZE — Synthesize (challenge, reasoning, exploit) triples
# ─────────────────────────────────────────────────────────────────────────────
if [ "$FROM_STAGE" -le 2 ]; then
    echo "━━━ STEP 2 SYNTHESIZE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    echo "  Starting vLLM synthesis cluster (4 instances, GPUs 0-15)..."
    bash scripts/start_vllm.sh
    export VLLM_URLS="http://localhost:8001,http://localhost:8002,http://localhost:8003,http://localhost:8004"

    echo "  Synthesizing training triples (challenge, reasoning, exploit)..."
    python synthesis/synthesize_bulk.py \
        --backend vllm \
        --vllm-urls http://localhost:8001 http://localhost:8002 \
        --concurrency 20

    echo "  Generating exploit reasoning chains (ports 8003/8004)..."
    python synthesis/exploit_synthesizer.py \
        --backend vllm \
        --vllm-urls http://localhost:8003 http://localhost:8004 \
        --count 10

    echo "  Generating novel challenges for RL training..."
    python synthesis/challenge_generator.py \
        --backend vllm \
        --count 1000 \
        --difficulty medium

    echo "  Killing vLLM synthesis cluster..."
    pkill -f "vllm serve" 2>/dev/null || pkill -f "vllm.entrypoints" 2>/dev/null || true

    echo ""
    echo "  STEP 2 SYNTHESIZE complete: $(date)"
    echo ""
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 TRAIN SFT — Supervised fine-tuning on CTF (challenge, reasoning, exploit) triples
# ─────────────────────────────────────────────────────────────────────────────
if [ "$FROM_STAGE" -le 3 ]; then
    echo "━━━ STEP 3 TRAIN SFT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17 \
    deepspeed --num_gpus=18 training/train.py \
        --deepspeed training/configs/deepspeed_zero3.json \
        --model Qwen/Qwen2.5-Coder-7B-Instruct \
        --data-dir data/train \
        --output-dir checkpoints/flagfoundry-sft \
        --epochs 3

    echo ""
    echo "  STEP 3 TRAIN SFT complete: $(date)"
    echo ""
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 TRAIN RL — GRPO with Docker-based flag capture reward
# ─────────────────────────────────────────────────────────────────────────────
if [ "$FROM_STAGE" -le 4 ]; then
    echo "━━━ STEP 4 TRAIN RL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
    deepspeed --num_gpus=16 training/train_rl.py \
        --deepspeed training/configs/deepspeed_zero3.json \
        --base-model checkpoints/flagfoundry-sft/final \
        --output-dir checkpoints/flagfoundry-rl \
        --docker-workers 8 \
        --max-steps 2000

    echo ""
    echo "  STEP 4 TRAIN RL complete: $(date)"
    echo ""
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 TRAIN DPO — Direct preference optimization on explanation quality
# ─────────────────────────────────────────────────────────────────────────────
if [ "$FROM_STAGE" -le 5 ]; then
    echo "━━━ STEP 5 TRAIN DPO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17 \
    deepspeed --num_gpus=18 training/train_dpo.py \
        --deepspeed training/configs/deepspeed_zero3.json \
        --base-model checkpoints/flagfoundry-rl/final \
        --output-dir checkpoints/flagfoundry-final \
        --max-steps 1000

    echo ""
    echo "  STEP 5 TRAIN DPO complete: $(date)"
    echo ""
fi

echo "=== Pipeline complete: $(date) ==="
echo "Model: checkpoints/flagfoundry-final"
echo "API: http://localhost:8080"
