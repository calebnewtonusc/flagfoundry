# FlagFoundry — Full System Architecture
## "Every flag. Every time."

---

## THE VISION

User inputs: a CTF challenge description + attached binary/pcap/image/URL.
FlagFoundry: classifies the category → routes to the right specialist agent → reasons through the attack chain step-by-step → generates working exploit code → executes it in a sandboxed container → returns the flag.

Not a lookup table. Not a taxonomy description. An actual reasoning machine that goes from challenge file to captured flag.

---

## 4-PHASE PRODUCT VISION

```
Phase 1 (v1):   SOLVE           challenge → reasoning chain → working exploit → flag     ← CURRENT
Phase 2 (v1.5): TEACH           Socratic explanations, learning mode, hint scaffolding
Phase 3 (v2):   GENERATE        novel challenge generation, CTF platform integration
Phase 4 (v3):   COMPETE         autonomous team agent, time-optimized multi-challenge solving
```

### Phase 1 — v1: SOLVE (Current)

Given a CTF challenge (description + file), reason through the vulnerability class, write working exploit code, execute it in a Docker sandbox, validate the flag. Covers all 7 major CTF categories. Handles multi-step attack chains (e.g., SQLi → LFI → RCE → privesc → flag).

### Phase 2 — v1.5: TEACH

FlagFoundry learns to teach, not just solve. Given a student's attempted solution, diagnose where the reasoning broke down and provide Socratic guidance toward the correct approach. Outputs: hint trees, partial solutions, directed questions that lead the solver toward the vulnerability class.

### Phase 3 — v2: GENERATE

FlagFoundry generates novel CTF challenges with verified solutions. Creates challenges calibrated to a target difficulty rating, across any category, with Docker deployment files. Challenge generation is the training flywheel: new challenges → new training data → better model.

### Phase 4 — v3: COMPETE

FlagFoundry operates as an autonomous CTF team agent. Given a competition URL and credentials, it enumerates all challenges, prioritizes by expected point yield vs. estimated solve time, dispatches specialist sub-agents in parallel, and submits flags. Target: top 10% on CTFtime competitive events.

---

## TARGET METRICS

| Version | Task | Target | Key Benchmark |
|---------|------|--------|---------------|
| v1 | Web exploitation solve rate | >75% | FlagBench-Web |
| v1 | Binary exploitation solve rate | >55% | FlagBench-Pwn |
| v1 | Cryptography solve rate | >80% | FlagBench-Crypto |
| v1 | Forensics solve rate | >70% | FlagBench-Forensics |
| v1 | Reverse engineering solve rate | >60% | FlagBench-Rev |
| v1 | Time-to-flag (known archetypes) | <30s | FlagBench-Speed |
| v1.5 | Hint relevance score | >4.0/5.0 | CoachBench-CTF |
| v2 | Generated challenge solve rate | 50-70% (calibrated) | GenBench |
| v3 | CTFtime competitive ranking | top 10% | Live competition |

---

## 6 TECHNICAL DIFFERENTIATORS

### 1. Process-Trained, Not Taxonomy-Trained

Every existing security LLM is trained on vulnerability descriptions — CVE summaries, OWASP pages, security blog posts. These describe vulnerability classes in the abstract. FlagFoundry is trained on **exploit reasoning chains**: the actual step-by-step process a skilled CTF player uses to go from "here's a binary" to "here's a working ROP chain." The corpus is 50,000+ competition writeups — not descriptions of how buffer overflows work, but transcripts of people actually exploiting them.

### 2. Binary Reward Signal (No Approximation)

The reward signal is exact and free: did the generated exploit capture the flag or not? Docker containers run the generated exploit against the challenge service. Flag extracted? Score 1.0. Exception or timeout? Score 0.0. No reward model needed, no human raters, no approximation. This is structurally identical to Nalana's headless Blender execution loop — a verifiable ground-truth reward.

### 3. Orchestrator → Specialist Architecture

The base model routes challenges to specialized sub-agents (web, pwn, crypto, forensics, OSINT, rev). Each sub-agent is initialized with category-specific tool access and system prompts tuned to that domain's conventions. A web agent knows about Burp Suite payloads and HTTP headers. A pwn agent has pwntools, pwndbg, and ROPgadget in its context. The orchestrator never confuses the domains.

### 4. 15-Year Historical Corpus

FlagFoundry is trained on DEFCON CTF archives back to 2010 — the oldest and most prestigious CTF competition. This means the model has seen the evolution of challenges from basic stack overflows to modern kernel exploits, from simple SQL injection to complex chain exploits. Generalization to novel challenges comes from understanding the entire history of how challenge authors think.

### 5. Multi-Step Attack Chain Reasoning

The key gap in current AI security tools: they can identify a vulnerability but cannot reason through a multi-step chain. FlagFoundry is trained on writeups where the exploit requires: initial foothold → lateral movement → privilege escalation → flag extraction. Each step is explicitly reasoned before executing, and the chain is retried with corrected assumptions if any step fails.

### 6. FlagBench Defines the Standard

No standard benchmark exists for AI CTF solving. FlagBench fills that gap — 500 challenges across all categories, each verified by Docker execution. Publishing FlagBench positions FlagFoundry as the benchmark against which all future security AI models are measured.

---

## 3-STAGE TRAINING PIPELINE

### Stage 1 — Supervised Fine-Tuning: train.py

Teaches the model what correct exploit reasoning looks like. Training data covers all 5 streams across all 7 categories.

```
Input:  (challenge_description, attached_file_contents, category_hint)
Output: (reasoning_chain, exploit_code, flag)

Data mix:
  40% Stream 1: CTFtime.org writeups (50k+ competitions)
  25% Stream 2: HackTheBox writeups (all machines + challenges)
  15% Stream 3: picoCTF + pwn.college (educational, clean structure)
  15% Stream 4: DEFCON/HITCON archives 2010-2025
   5% Stream 5: CVE PoC repositories (real-world grounding)

Target: ~500k (challenge, reasoning, exploit) triples
Base model: Qwen2.5-Coder-7B-Instruct
Training: DeepSpeed ZeRO-3, LoRA rank 64, 3 epochs
```

### Stage 2 — Flag Capture RL: train_rl.py

Uses sandboxed Docker execution as the reward signal. The model generates exploit code; Docker runs it against the challenge service; the flag is extracted and compared to ground truth.

```
Reward function:
  +1.0  flag captured correctly
  +0.3  correct vulnerability class identified but exploit failed
  -0.5  wrong vulnerability class
  -1.0  exploit crashes target or times out

Algorithm: GRPO with KL penalty against Stage 1 checkpoint
Parallelism: 12 Docker workers (GPUs 16-17 idle during Docker execution)
Target: flag capture rate >65% across all categories
```

### Stage 3 — DPO on Explanation Quality: train_dpo.py

Teaches the model to produce writeup-quality explanations — not just "this is SQLi" but the full attack narrative that a CTF author would publish post-competition.

```
Preference signal:
  Chosen:   detailed step-by-step reasoning → working exploit → clear flag extraction
  Rejected: vague vulnerability name → generic exploit attempt → no flag

Algorithm: Direct Preference Optimization (DPO)
Data: ~30k preference pairs from human-ranked writeup quality ratings
```

---

## WHAT MAKES THIS DIFFERENT

| Tool | What it does | What it lacks |
|------|-------------|---------------|
| GPT-4o | General code generation | Not CTF-trained, no execution loop |
| WizardCoder | Code assistance | No security specialization |
| SecurityLLM (various) | Describes vulnerabilities | Not trained on exploit process |
| **FlagFoundry** | Reasons through attack chains, executes exploits | **Nothing like this exists** |

The moat: CTF writeups are the closest thing to "expert thinking out loud" in security. A writeup is a skilled player explaining their entire thought process — why they tried one approach, why it failed, what they noticed, how they pivoted. 50,000 of those, parsed into reasoning chains, distilled into model weights. That corpus has never been used for fine-tuning before.

---

## HARDWARE

```
18x A6000 (48GB VRAM each) = 864GB total VRAM

GPU Allocation During Synthesis:
  GPUs  0-3:  vLLM Qwen2.5-72B    (reasoning chain synthesis, port 8001)
  GPUs  4-7:  vLLM Qwen2.5-72B    (reasoning chain synthesis, port 8002)
  GPUs  8-11: vLLM Qwen2.5-Coder  (exploit code synthesis, port 8003)
  GPUs 12-15: vLLM Qwen2.5-Coder  (exploit code synthesis, port 8004)
  GPUs 16-17: Docker workers       (exploit execution validation)

GPU Allocation During Training:
  All 18 A6000s: DeepSpeed ZeRO-3 (Stage 1 SFT)
  Model: 7B × bf16 = ~14GB
  Per GPU: 14GB model + 30GB activations/optimizer = ~44GB (fits ZeRO-3)
  Effective batch: 4 × 18 × 4 grad_accum = 288

  GPUs 16-17 during Stage 2 RL: Docker execution workers
```

---

## FILE STRUCTURE

```
flagfoundry/
│
├── DISCOVERY
│   └── discovery/
│       ├── ctftime_crawler.py      Scrape CTFtime writeups (2010-2025)
│       ├── htb_crawler.py          HackTheBox writeup downloader
│       ├── picoctf_downloader.py   picoCTF archive fetcher
│       ├── defcon_crawler.py       DEFCON CTF archive crawler
│       └── github_poc_crawler.py   CVE PoC + Exploit-DB fetcher
│
├── SYNTHESIS
│   └── synthesis/
│       ├── prompts.py              All system prompts (import from here)
│       ├── synthesize_bulk.py      Async multi-writeup synthesis
│       ├── exploit_synthesizer.py  Generate exploit reasoning chains
│       ├── challenge_generator.py  Generate novel challenges for RL training
│       └── generate_dpo_pairs.py   Writeup quality preference pairs
│
├── CORE
│   └── core/
│       ├── challenge_classifier.py Category routing (web/pwn/crypto/forensics/rev/osint/steg)
│       └── sandbox_harness.py      Docker sandbox execution + flag validation
│
├── AGENTS
│   └── agents/
│       ├── orchestrator_agent.py   Routes to specialist sub-agent
│       ├── web_exploit_agent.py    SQL injection, XSS, SSRF, SSTI, LFI, IDOR
│       ├── binary_agent.py         Buffer overflow, ROP chains, heap exploitation
│       ├── crypto_agent.py         RSA, ECC, symmetric, hash, custom crypto
│       ├── forensics_agent.py      File carving, network analysis, memory forensics
│       ├── rev_agent.py            Static analysis, decompilation, anti-debug bypass
│       └── osint_agent.py          Recon, HUMINT, GEOINT, social media analysis
│
├── TRAINING
│   └── training/
│       ├── train_prep.py           Merge all streams → HuggingFace format
│       ├── train.py                Stage 1: SFT (DeepSpeed + LoRA)
│       ├── train_rl.py             Stage 2: GRPO flag-capture RL
│       ├── train_dpo.py            Stage 3: DPO on explanation quality
│       └── configs/
│           ├── ds_config.json      DeepSpeed ZeRO-3 config
│           └── ds_config_rl.json   DeepSpeed ZeRO-2 config for GRPO
│
├── EVALUATION
│   └── evaluation/
│       └── flagbench.py            FlagBench: 500 challenges, Docker-verified
│
├── KNOWLEDGE
│   └── knowledge/
│       ├── web_techniques.md       SQLi, XSS, SSRF, SSTI reference
│       ├── pwn_techniques.md       BOF, ROP, heap, format string reference
│       ├── crypto_techniques.md    RSA, ECC, symmetric, hash reference
│       └── forensics_techniques.md File carving, steg, memory reference
│
├── DEPLOYMENT
│   └── deploy/
│       ├── docker-compose.yml      One-command: model + API + sandbox + Redis
│       ├── Dockerfile              Multi-stage CUDA container
│       ├── api_server.py           FastAPI REST + WebSocket server
│       └── challenge_sandbox/      Per-category Docker challenge templates
│
├── SCRIPTS
│   └── scripts/
│       ├── run_all.sh              Master pipeline
│       ├── start_vllm.sh           Launch vLLM servers on GPUs 0-15
│       ├── check_env.sh            Verify deps + Docker + CUDA
│       └── health_check.py         Post-deploy smoke test
│
└── DATA (gitignored)
    └── data/
        ├── raw/                    Raw scraped writeups
        ├── processed/              Parsed (challenge, reasoning, exploit) tuples
        ├── challenges/             Generated novel challenges
        ├── dpo/                    Preference pairs
        └── train/                  HuggingFace splits
```

---

## DEPLOYMENT API

```
POST /v1/solve
  { "description": "...", "file": "<base64>", "category": "auto" }
  → { "category": "web", "reasoning": "...", "exploit": "...", "flag": "FLAG{...}" }

POST /v1/hint
  { "description": "...", "attempted_approach": "...", "hint_level": 1 }
  → { "hint": "Think about what happens when the input is 256 characters long..." }

POST /v1/classify
  { "description": "...", "file": "<base64>" }
  → { "category": "pwn", "confidence": 0.94, "vulnerability_class": "heap_overflow" }

WS  /v1/stream
  Real-time streaming exploit generation with step-by-step reasoning
```

---

## STATUS

All pipeline components implemented. See ROADMAP.md for v1.5/v2/v3 plans.
FlagBench: 500 challenges ready. Training in progress.
