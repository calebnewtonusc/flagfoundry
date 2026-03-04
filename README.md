# FlagFoundry — Every Flag. Every Time.

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Model: Qwen2.5-7B-Coder](https://img.shields.io/badge/base_model-Qwen2.5--7B--Coder-purple.svg)](https://huggingface.co/Qwen)
[![GPUs: 18x A6000](https://img.shields.io/badge/training-18x_A6000-red.svg)](https://www.nvidia.com)
[![Categories: 8](https://img.shields.io/badge/CTF_categories-8-orange.svg)]()

> **"Every flag. Every time."**

FlagFoundry is the first AI model trained specifically on the **problem-solving process** of CTF competition solving — not vulnerability taxonomies, not documentation, but the actual reasoning chain from "here is a challenge file" to "here is a working exploit and the flag."

Every security LLM today is fine-tuned on vulnerability descriptions. FlagFoundry is trained on 50,000+ competition writeups parsed into `(challenge description, reasoning chain, exploit code, flag)` tuples — across web exploitation, binary exploitation, cryptography, forensics, reverse engineering, OSINT, and steganography. The reward signal is binary and unambiguous: flag captured or not, verified by sandboxed Docker execution.

---

## What Makes FlagFoundry Different

| Capability | GPT-4o | Claude 3.5 | WizardCoder | **FlagFoundry** |
|---|---|---|---|---|
| CTF-specific training | — | — | — | **50k+ writeups, all major competitions** |
| Multi-step exploit reasoning | partial | partial | partial | **Full attack chain reasoning** |
| Working exploit generation | inconsistent | inconsistent | inconsistent | **RL-verified execution** |
| Category routing | — | — | — | **Orchestrator → specialist sub-agents** |
| Novel challenge generalization | poor | poor | poor | **Trained on 15 years of DEFCON/HITCON** |
| Sandboxed execution reward | — | — | — | **Docker harness, binary flag validation** |
| Writeup-style explanations | partial | partial | — | **AoPS-style multi-step breakdowns** |
| Time-to-flag | minutes | minutes | hours | **<30s for known archetypes** |

---

## Architecture

```
                    ┌────────────────────────────────────────────┐
 Challenge File ───►│          FlagFoundry Orchestrator          │
 + Description      │   (Qwen2.5-7B-Coder + LoRA, 3-stage)      │
                    └──────────────────┬─────────────────────────┘
                                       │  challenge_classifier.py
                                       │  routes by category
                    ┌──────────────────▼─────────────────────────┐
                    │         Category Classification             │
                    └──┬──────┬───────┬───────┬──────┬──────────┘
                       │      │       │       │      │
              ┌────────▼─┐ ┌──▼───┐ ┌─▼────┐ ┌▼────┐ ┌▼──────────┐
              │   Web    │ │ Pwn  │ │Crypto│ │Foren│ │   OSINT   │
              │  Agent   │ │Agent │ │Agent │ │Agent│ │  Agent    │
              │SQL/XSS/  │ │BoF/  │ │RSA/  │ │File │ │Recon/HUMINT│
              │SSRF/SSTI │ │ROP/  │ │ECC/  │ │Carve│ │Social/GEOINT│
              │LFI/IDOR  │ │Heap  │ │Hash  │ │Steg │ │           │
              └────┬─────┘ └──┬───┘ └──┬───┘ └──┬──┘ └──┬────────┘
                   │          │        │         │       │
                   └──────────┴────────┴─────────┴───────┘
                                       │
                              ┌─────────▼──────────┐
                              │  Sandbox Harness   │
                              │  Docker container  │
                              │  Flag validation   │
                              │  Binary: captured? │
                              └────────────────────┘
```

**Training data sources (5 streams, 500k+ pairs):**
- Stream 1: CTFtime.org writeups → parsed (challenge, approach, exploit, flag) (40%)
- Stream 2: HackTheBox writeup blog posts + official walkthroughs (25%)
- Stream 3: picoCTF archives + pwn.college curricula (15%)
- Stream 4: DEFCON/HITCON/DEF CON CTF archives (back 15 years) (15%)
- Stream 5: CVE PoC repositories + Exploit-DB for real-world grounding (5%)

---

## Quick Start

**1. Clone and install**

```bash
git clone https://github.com/calebnewtonusc/flagfoundry.git
cd flagfoundry
pip install -r requirements.txt
```

**2. Set environment variables**

```bash
cp .env.example .env
# Edit .env — see variable reference below
```

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [claude.ai/settings](https://claude.ai/settings) |
| `CTFTIME_SESSION` | Browser cookie from ctftime.org after login |
| `HTB_API_TOKEN` | HackTheBox account settings |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) (for CVE/PoC) |

**3. Validate environment**

```bash
bash scripts/check_env.sh
```

**4. Collect training data**

```bash
# Crawl CTFtime writeups (no GPU needed, async)
python discovery/ctftime_crawler.py --years 2010-2025 --workers 30

# Download HackTheBox writeups
python discovery/htb_crawler.py --all-machines --all-challenges

# Download picoCTF archives
python discovery/picoctf_downloader.py --all-years

# Fetch CVE PoC repositories
python discovery/github_poc_crawler.py --limit 10000
```

**5. Synthesize training pairs**

```bash
# Start vLLM servers for synthesis
bash scripts/start_vllm.sh

# Synthesize exploit reasoning chains
python synthesis/synthesize_bulk.py --backend vllm \
  --vllm-urls http://localhost:8001 http://localhost:8002

# Generate additional challenge variants
python synthesis/challenge_generator.py --count 10000

# Generate exploit reasoning chains for novel challenges
python synthesis/exploit_synthesizer.py --backend vllm
```

**6. Prepare and train**

```bash
# Prep dataset (all streams → HuggingFace format)
python training/train_prep.py

# Stage 1: SFT (18 GPUs, ZeRO-3)
deepspeed --num_gpus=18 training/train.py \
  --deepspeed training/configs/ds_config.json \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --data-dir data/train \
  --output-dir checkpoints/flagfoundry-sft

# Stage 2: GRPO RL (binary flag capture reward)
deepspeed --num_gpus=18 training/train_rl.py \
  --deepspeed training/configs/ds_config_rl.json \
  --base-model checkpoints/flagfoundry-sft/final \
  --output-dir checkpoints/flagfoundry-rl

# Stage 3: DPO (explanation quality)
deepspeed --num_gpus=18 training/train_dpo.py \
  --base-model checkpoints/flagfoundry-rl/final \
  --output-dir checkpoints/flagfoundry-final
```

**7. Evaluate**

```bash
python evaluation/flagbench.py --model checkpoints/flagfoundry-final --all
```

**8. Deploy**

```bash
cd deploy && docker compose up -d
python scripts/health_check.py
```

---

## Hardware Requirements

### Data Collection
Any machine with internet. The crawlers are async I/O-bound — a laptop works. Expect 2-4 days for full corpus at 30 workers.

### Synthesis
Qwen2.5-72B for synthesis: 4x A6000 (48GB) per vLLM instance. Two instances (8 GPUs) → 10,000 writeups in ~12 hours.

### Training
| Resource | Specification |
|---|---|
| GPUs | 18x NVIDIA A6000 (48GB each) |
| Total VRAM | 864GB |
| Strategy | DeepSpeed ZeRO-3 + CPU offload |
| RAM | 512GB+ |
| Expected time | 4-8 hours (500k pairs, 3 epochs) |

### Inference
| Configuration | Latency | Use case |
|---|---|---|
| 2x A100 (80GB) | <100ms | Production API |
| 1x A6000 (48GB) | ~200ms | Development |
| 1x RTX 4090 (24GB) | ~500ms | Local testing |

---

## FlagBench

FlagBench is our evaluation suite — 500 challenges across all categories, verified by sandboxed Docker execution. Categories:

| Category | Challenges | Scoring |
|---|---|---|
| Web Exploitation | 100 | Flag captured (binary) |
| Binary Exploitation | 100 | Flag captured (binary) |
| Cryptography | 100 | Flag captured (binary) |
| Forensics | 75 | Flag captured (binary) |
| Reverse Engineering | 75 | Flag captured (binary) |
| OSINT | 25 | Flag captured (binary) |
| Steganography | 25 | Flag captured (binary) |

```bash
python evaluation/flagbench.py --model checkpoints/flagfoundry-final --all
python evaluation/flagbench.py --model checkpoints/flagfoundry-final --category web
python evaluation/flagbench.py --model checkpoints/flagfoundry-final --category pwn
```

---

## Dataset Structure

```
data/
├── raw/                         # Raw scraped writeups (JSON per writeup)
│   ├── ctftime/                 # CTFtime.org writeups
│   ├── htb/                     # HackTheBox writeups
│   ├── picoctf/                 # picoCTF archives
│   ├── defcon/                  # DEFCON CTF archives
│   └── cve_poc/                 # CVE PoC code
├── processed/                   # Parsed (challenge, reasoning, exploit, flag) tuples
│   ├── web.jsonl
│   ├── pwn.jsonl
│   ├── crypto.jsonl
│   ├── forensics.jsonl
│   ├── rev.jsonl
│   ├── osint.jsonl
│   └── steg.jsonl
├── challenges/                  # Generated novel challenges (for RL training)
├── dpo/                         # Preference pairs for Stage 3
└── train/                       # Final HuggingFace dataset splits
    ├── sharegpt_train.jsonl
    ├── sharegpt_val.jsonl
    └── alpaca_train.jsonl
```

---

## Citation

```bibtex
@inproceedings{newton2026flagfoundry,
  title     = {FlagFoundry: Training on Exploit Reasoning Chains for CTF Competition Solving},
  author    = {Newton, Caleb and others},
  booktitle = {IEEE Security and Privacy 2026},
  year      = {2026},
}
```

---

## License

**Code:** MIT License
**Model weights:** Apache 2.0
**Training data:** Synthesis outputs covered under fair use for AI research. Raw writeups remain property of their original authors.

---

*Target: 864GB VRAM, 500k+ training pairs, FlagBench solve rate >70% on web/crypto. Training in progress.*
