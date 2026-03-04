# FlagFoundry — Data Sources

## Overview

FlagFoundry is trained on 5 data streams totaling 500k+ `(challenge, reasoning, exploit)` triples. All streams converge on the same unit of training: the expert reasoning process, not the taxonomy classification.

---

## Stream 1: CTFtime.org Writeups (40%)

**Target:** 30,000+ writeups from 2010-2025

CTFtime.org is the central hub for CTF competition tracking. After every competition, teams publish writeups — detailed explanations of how they solved each challenge. These are the highest-signal data source because they document the entire reasoning process, including failed attempts and pivots.

| Source | Count | Format | Notes |
|--------|-------|--------|-------|
| CTFtime writeup links | 50k+ | HTML/Markdown | Links to external blogs, GitHub, HackMD |
| External writeup pages | 30k+ | Various | Crawled from CTFtime links |
| GitHub repos tagged "ctf-writeups" | 15k+ | Markdown | Direct repository crawl |

**Parser**: `discovery/ctftime_crawler.py`
- Crawls CTFtime event list → scrapes writeup links → fetches external pages
- Extracts: challenge title, category, description, author approach, exploit code, flag format
- Handles: HTML, Markdown, PDF, Jupyter notebooks

**Quality filter**: Must contain at least one code block + flag pattern match.

---

## Stream 2: HackTheBox Writeups (25%)

**Target:** 15,000+ writeups (all machines + challenges)

HackTheBox is a premium platform with professional-quality challenges. HTB writeups are particularly valuable because:
1. Machines require multi-step attack chains (initial foothold → privesc → root flag)
2. The community produces exceptionally well-documented writeups with tools and commands
3. HTB Official writeups are released after machines retire — verified correct solutions

| Source | Count | Format | Notes |
|--------|-------|--------|-------|
| HTB official walkthroughs | 500+ | PDF | Retired machines only |
| Community writeup blogs | 10k+ | HTML/Markdown | ippsec, 0xdf, HackTricks refs |
| HTB Academy modules | 200+ | Structured | Educational, multi-step |
| HTB challenge writeups | 5k+ | Markdown | Web, Pwn, Crypto, Forensics, Rev |

**Parser**: `discovery/htb_crawler.py`
- Requires HTB API token for access
- Downloads machine metadata, walkthrough PDFs, community links
- Parses multi-step chains into sequential reasoning steps

---

## Stream 3: picoCTF + pwn.college (15%)

**Target:** 10,000+ problems with solutions

These educational platforms are uniquely valuable for training because challenges are explicitly designed with pedagogical scaffolding — each challenge has a clear difficulty progression and documented solution approach.

| Source | Count | Format | Notes |
|--------|-------|--------|-------|
| picoCTF archives 2013-2025 | 2k+ challenges | JSON | Full problem + solution pairs |
| pwn.college modules | 500+ modules | HTML | Progressive difficulty, shell access |
| picoCTF community writeups | 5k+ | Markdown | Multiple approaches per problem |

**Parser**: `discovery/picoctf_downloader.py`
- picoCTF API access (no auth required for archived competitions)
- Downloads: problem statement, hints, solution files, point value
- pwn.college: scrapes module descriptions + forum solutions

---

## Stream 4: DEFCON/HITCON Archives (15%)

**Target:** 5,000+ challenge-solution pairs from elite competitions

DEFCON CTF Finals and HITCON are the most prestigious competitions globally. Challenges from these events represent the frontier of what's possible — novel vulnerability classes, creative exploit chains, and techniques that later propagate into the broader CTF ecosystem.

| Source | Years | Categories | Notes |
|--------|-------|------------|-------|
| DEFCON CTF Finals | 2010-2025 | All | Hardest challenges, elite solves |
| DEFCON CTF Quals | 2010-2025 | All | 2000+ teams competing |
| HITCON CTF | 2014-2025 | All | Asia-Pacific elite |
| Plaid CTF | 2011-2025 | All | Carnegie Mellon PPP team |
| hxp CTF | 2017-2025 | Pwn/Rev/Crypto | European elite |

**Parser**: `discovery/defcon_crawler.py`
- Crawls OtterCTF, GitHub orgs, and personal blogs for archived challenges
- Downloads challenge files (binaries, source, network captures)
- Links challenges to writeups via competition name + challenge title matching

---

## Stream 5: CVE PoC Repositories (5%)

**Target:** 10,000+ CVE proof-of-concept exploits

CVE PoC repositories provide real-world grounding. CTF challenges often mirror real vulnerabilities (a CTF SQL injection challenge uses the same class of techniques as CVE-2023-XXXXX). Training on PoC code teaches the model the actual exploit implementation patterns.

| Source | Count | Format | Notes |
|--------|-------|--------|-------|
| trickest/cve GitHub repo | 25k+ | Python/Shell | CVE PoC collection |
| Exploit-DB | 50k+ | Python/C/Shell | Verified exploits, searchable |
| GitHub topics: "cve-poc", "exploit" | 10k+ | Various | Community contributions |
| NVD CVE descriptions | 200k+ | JSON | Vulnerability context (text only) |

**Parser**: `discovery/github_poc_crawler.py`
- GitHub API search for CVE-tagged repositories
- Downloads PoC code + CVE description for each
- Pairs: (CVE description + affected software + vulnerability class) → (working PoC code)

---

## Synthesis Pipeline

Raw writeups are parsed into structured `(challenge, reasoning, exploit)` triples using Qwen2.5-72B as the synthesis model.

### Input Format (raw writeup)
```
[Raw writeup text / HTML / Markdown from any source]
```

### Output Format (training triple)
```json
{
  "challenge": {
    "title": "SQLi in the Dark",
    "category": "web",
    "description": "Can you extract the flag from this database?",
    "url": "http://challenge.example.com:8080",
    "files": [],
    "points": 200,
    "competition": "PicoCTF 2024"
  },
  "reasoning": [
    "Step 1: Identify injection point — the 'id' parameter in /search is reflected in the query",
    "Step 2: Test basic injection — id=1' causes a 500 error, confirming SQLi",
    "Step 3: Determine DB type — SLEEP(1) works, confirms MySQL",
    "Step 4: Enumerate tables — information_schema.tables reveals 'flags' table",
    "Step 5: Extract flag — SELECT flag FROM flags LIMIT 1"
  ],
  "exploit": "import requests\n\nurl = 'http://challenge.example.com:8080/search'\n\n# ...",
  "flag": "picoCTF{sql_1nj3ct10n_m4st3r}",
  "tools": ["sqlmap", "burpsuite", "python-requests"],
  "techniques": ["blind_sqli", "error_based_sqli", "union_based_sqli"],
  "difficulty": "medium",
  "source": "ctftime",
  "quality_score": 0.87
}
```

### Quality Filter
Only triples with `quality_score >= 0.7` enter Stage 1 training. Quality scoring:
- `has_working_code`: exploit code block is syntactically valid Python/Shell
- `has_reasoning_steps`: at least 3 distinct reasoning steps
- `has_flag_format`: flag pattern matches challenge's flag format string
- `no_duplicate`: MinHash similarity to existing triples < 0.85
- `category_confirmed`: classifier agrees with author's stated category
