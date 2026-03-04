# FlagFoundry Model Card

## Model Details

| Field | Value |
|-------|-------|
| **Model name** | FlagFoundry-7B |
| **Base model** | Qwen2.5-Coder-7B-Instruct |
| **Fine-tuning method** | 3-stage: SFT + GRPO RL + DPO |
| **Training hardware** | 18x NVIDIA A6000 (48GB), DeepSpeed ZeRO-3 |
| **Repository** | github.com/calebnewtonusc/flagfoundry |
| **License** | Apache 2.0 |
| **Developer** | Caleb Newton |

## Intended Use

FlagFoundry is designed for:
- CTF competition participants who want to learn by seeing expert reasoning chains
- Security researchers studying AI-assisted vulnerability analysis
- CTF challenge authors validating challenge solvability
- Security educators building AI-assisted tutoring tools

**Not intended for:**
- Real-world unauthorized access to computer systems
- Exploitation of production infrastructure
- Any use that violates computer fraud laws in your jurisdiction

## Training Data

Five streams totaling 500k+ (challenge, reasoning, exploit) triples:
1. CTFtime.org writeups (2010-2025) — 40%
2. HackTheBox writeups — 25%
3. picoCTF + pwn.college — 15%
4. DEFCON/HITCON archives — 15%
5. CVE PoC repositories — 5%

All data is from publicly available sources. No data from private competition systems.

## Evaluation

**FlagBench** — 500 challenges across 7 categories, verified by Docker sandbox execution:

| Category | Challenges | v1 Target |
|----------|------------|-----------|
| Web Exploitation | 100 | >75% |
| Binary Exploitation | 100 | >55% |
| Cryptography | 100 | >80% |
| Forensics | 75 | >70% |
| Reverse Engineering | 75 | >60% |
| OSINT | 25 | >60% |
| Steganography | 25 | >65% |

## Limitations

- Model may attempt to solve challenges using outdated tools or techniques for post-2024 challenges
- Binary exploitation accuracy depends heavily on the specific architecture (x86/x86-64/ARM)
- OSINT tasks involving real individuals are filtered from training and evaluation
- Model does not have internet access at inference time — all reasoning is from training distribution

## Ethical Considerations

FlagFoundry is trained exclusively on CTF competition data — synthetic environments explicitly designed for security education and competition. The model has no training signal toward real-world unauthorized access. Responsible disclosure: any use of FlagFoundry against systems you do not own or have explicit permission to test is illegal and unethical.

## Citation

```bibtex
@inproceedings{newton2026flagfoundry,
  title     = {FlagFoundry: Training on Exploit Reasoning Chains for CTF Competition Solving},
  author    = {Newton, Caleb},
  year      = {2026},
}
```
