# FlagFoundry Roadmap

## v1 — SOLVE (Current Build)

**Target: Q2 2026**

Core solve loop across all 7 CTF categories. Verifiable RL training via Docker sandbox execution.

### v1 Milestones
- [x] CTFtime crawler — 50k+ writeups collected
- [x] HTB crawler — all machines + challenges downloaded
- [x] picoCTF archive downloader
- [x] DEFCON/HITCON 15-year archive
- [x] Synthesis pipeline: writeup → (challenge, reasoning, exploit) triples
- [x] challenge_classifier.py — category routing
- [x] sandbox_harness.py — Docker execution + flag validation
- [x] Stage 1: SFT on 500k+ (challenge, reasoning, exploit) pairs
- [x] Stage 2: GRPO RL with binary flag capture reward
- [x] Stage 3: DPO on writeup explanation quality
- [ ] FlagBench evaluation: 500 challenges, all categories
- [ ] Deploy API: FastAPI + vLLM serving

### v1 Target Metrics
| Category | Target Solve Rate |
|----------|------------------|
| Web Exploitation | >75% |
| Cryptography | >80% |
| Forensics | >70% |
| Steganography | >65% |
| Reverse Engineering | >60% |
| Binary Exploitation | >55% |
| OSINT | >60% |

---

## v1.5 — TEACH

**Target: Q3 2026**

FlagFoundry learns to guide, not just solve. Adds Socratic tutoring mode, hint trees, and misconception diagnosis.

### v1.5 Features
- **Hint scaffolding**: 3-level hint system (category hint → technique hint → implementation hint)
- **Misconception detection**: identify why a student's approach is incorrect
- **Learning paths**: personalized challenge sequences based on skill gaps
- **Explain mode**: generate pedagogical writeups at configurable depth
- **DPO on teaching quality**: chosen = helpful hint, rejected = answer giveaway

### v1.5 New Files
- `agents/tutor_agent.py` — Socratic CTF tutor
- `core/skill_model.py` — student knowledge state tracker
- `evaluation/teachbench.py` — 200 teaching scenarios

---

## v2 — GENERATE

**Target: Q4 2026**

FlagFoundry generates novel CTF challenges with verified solutions and Docker deployments.

### v2 Features
- **Challenge generation**: specify category + difficulty → get full challenge package
- **Difficulty calibration**: target solve rate (50% for medium, 15% for hard)
- **CTF platform integration**: auto-deploy to CTFd
- **Challenge validation**: FlagFoundry solves its own generated challenges (end-to-end validation)
- **Training flywheel**: generated challenges → additional RL training data → better model

### v2 New Files
- `synthesis/challenge_generator_v2.py` — full challenge package generation
- `deploy/ctfd_deployer.py` — CTFd platform integration
- `evaluation/genbench.py` — generated challenge quality evaluation

---

## v3 — COMPETE

**Target: Q1 2027**

FlagFoundry operates as an autonomous CTF team agent, competing live.

### v3 Features
- **Competition crawler**: enumerate all challenges from CTFd/CTFx platforms
- **Priority queue**: expected points / estimated solve time optimization
- **Parallel solving**: dispatch specialist sub-agents concurrently
- **Team coordination**: avoid duplicate work, share intermediate findings
- **Live submission**: automatic flag submission with rate limiting
- **Post-competition**: auto-generate writeups for all solved challenges

### v3 Target
- Top 10% ranking on CTFtime competitive events
- >50% solve rate on medium-difficulty competitions
- Full autonomy: competition URL + credentials → flag submissions

### v3 New Files
- `agents/competition_agent.py` — top-level autonomous competition agent
- `agents/team_coordinator.py` — multi-agent coordination
- `core/priority_scheduler.py` — challenge priority queue
- `deploy/competition_runner.py` — live competition runner

---

## Research Directions

### Exploit Generalization
Can a model trained on writeup reasoning chains generalize to genuinely novel vulnerability classes? The key experiment: train on writeups pre-2020 and evaluate on post-2023 challenges. If the model has truly internalized exploit reasoning (not just memorized patterns), it should solve novel challenges at a meaningful rate.

### Automated Vulnerability Research
Extend beyond CTF: train FlagFoundry on responsible disclosure reports and bug bounty writeups. Apply to real-world codebases as a vulnerability scanner that reasons through attack chains rather than pattern-matching to CVE signatures.

### Multi-Agent CTF Teams
The v3 team agent is a research problem in itself: how do multiple FlagFoundry agents coordinate without duplicating work, share partial findings, and decide which challenges to prioritize given competition scoring dynamics?
