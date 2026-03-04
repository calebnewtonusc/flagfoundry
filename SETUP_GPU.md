# FlagFoundry — GPU Setup Guide

## Target Hardware: 18x NVIDIA A6000 (48GB)

FlagFoundry is designed for the 18x A6000 cluster (864GB total VRAM). This guide covers setup for this configuration, with notes for smaller setups.

---

## Driver and CUDA Setup

```bash
# Verify NVIDIA drivers
nvidia-smi

# Install CUDA 12.1+ (if not installed)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt update && sudo apt install -y cuda-toolkit-12-1

# Verify CUDA
nvcc --version
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

---

## Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Flash Attention 2 (significant speedup on A6000)
pip install flash-attn --no-build-isolation

# DeepSpeed
pip install deepspeed
ds_report  # verify installation
```

---

## Docker Setup (for sandbox execution)

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER && newgrp docker

# Pull base challenge images
docker pull ubuntu:22.04
docker pull python:3.11-slim

# Test Docker sandbox
python3 core/sandbox_harness.py --test
```

---

## GPU Allocation Strategy

### Phase 1: Data Synthesis

```bash
# 4 vLLM instances, 4 GPUs each = 16 GPUs for synthesis
# GPUs 0-3:  Text reasoning synthesis (Qwen2.5-72B), port 8001
# GPUs 4-7:  Text reasoning synthesis (Qwen2.5-72B), port 8002
# GPUs 8-11: Exploit code synthesis (Qwen2.5-Coder-72B), port 8003
# GPUs 12-15: Exploit code synthesis (Qwen2.5-Coder-72B), port 8004
# GPUs 16-17: Docker execution validation workers

bash scripts/start_vllm.sh
```

### Phase 2: Training

```bash
# All 18 GPUs: DeepSpeed ZeRO-3 SFT
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17 \
deepspeed --num_gpus=18 training/train.py \
  --deepspeed training/configs/ds_config.json

# Stage 2 GRPO: 16 GPUs training + 2 Docker workers
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
deepspeed --num_gpus=16 training/train_rl.py \
  --deepspeed training/configs/ds_config_rl.json \
  --docker-workers 8  # runs on CPU
```

---

## Smaller Hardware Configurations

### Single A100 (80GB) — Development

```bash
# Can fit 7B model for inference, not full training
# Use LoRA with gradient checkpointing for training
python training/train.py \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --batch-size 1 --grad-accum 32 --lora-r 16
```

### 4x A6000 (192GB) — Reduced training

```bash
# Reduce batch size proportionally
deepspeed --num_gpus=4 training/train.py \
  --deepspeed training/configs/ds_config.json \
  --batch-size 2 --grad-accum 16
```

---

## Monitoring

```bash
# GPU utilization
watch -n 1 nvidia-smi

# Training metrics (W&B)
# Set WANDB_API_KEY in .env, then training auto-logs

# Docker sandbox health
docker ps  # verify challenge containers are running
```

---

## Common Issues

**OOM during training**: Reduce `--batch-size` to 2, increase `--grad-accum` to 8.
**Blender not found**: Not needed for FlagFoundry (uses Docker, not Blender).
**Docker permission denied**: `sudo usermod -aG docker $USER && newgrp docker`
**vLLM CUDA error**: Ensure `CUDA_VISIBLE_DEVICES` is set correctly per instance.
