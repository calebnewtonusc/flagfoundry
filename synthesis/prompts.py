"""
prompts.py - All FlagFoundry synthesis system prompts.

Import from here — never hardcode prompts elsewhere.
"""

# ─── Core synthesis prompt: writeup → (challenge, reasoning, exploit) triple ──

WRITEUP_TO_TRIPLE_SYSTEM = """You are a CTF expert who specializes in extracting structured training data from competition writeups.

Given a raw CTF writeup (blog post, markdown, or HTML text), extract:
1. The challenge description and category
2. The step-by-step reasoning chain the author used
3. The working exploit code (cleaned up, executable)
4. The captured flag

Output ONLY valid JSON in this exact format — no other text:
{
  "challenge": {
    "title": "challenge name",
    "category": "web|pwn|crypto|forensics|rev|osint|steg|misc",
    "description": "what the challenge presents to the player",
    "flag_format": "FLAG{} or picoCTF{} etc",
    "difficulty": "easy|medium|hard|insane"
  },
  "reasoning": [
    "Step 1: Initial observation — what caught the expert's eye first",
    "Step 2: Hypothesis — what vulnerability class this maps to",
    "Step 3: Verification — how they confirmed the vulnerability",
    "Step 4: Exploitation — the actual attack approach",
    "Step 5: Flag extraction — exactly how the flag was obtained"
  ],
  "exploit": "# Complete, runnable exploit code\\nimport ...",
  "flag": "FLAG{example_flag_here}",
  "tools": ["pwntools", "burpsuite", "sqlmap"],
  "techniques": ["buffer_overflow", "rop_chain", "sql_injection"]
}

Rules:
- reasoning must have AT LEAST 3 steps, each explaining WHY not just WHAT
- exploit must be syntactically valid Python, Shell, or C
- If the writeup has no exploit code, synthesize it from the described technique
- category must be exactly one of: web, pwn, crypto, forensics, rev, osint, steg, misc
- quality_score: 0.0-1.0 based on reasoning depth and exploit completeness"""

WRITEUP_TO_TRIPLE_USER = """Here is the raw CTF writeup. Extract the structured training triple:

---
{raw_text}
---

Code blocks found in the writeup:
{code_blocks}

Extract the (challenge, reasoning, exploit, flag) triple. Output only JSON."""


# ─── Exploit synthesis: given vulnerability class → generate exploit ───────────

EXPLOIT_SYNTHESIS_SYSTEM = """You are an expert CTF exploit developer. Given a vulnerability description and challenge context, write a complete, working exploit.

Your exploits must:
1. Import all required libraries (pwntools, requests, etc.)
2. Connect to the target (use environment variables for host/port)
3. Execute the full attack chain step by step
4. Extract and print the flag

Use standard CTF tools:
- Web: requests, httpx, BeautifulSoup
- Pwn: pwntools (pwn.ELF, pwn.process, pwn.remote, pwn.ROP)
- Crypto: pycryptodome, z3-solver, sympy
- Forensics: scapy, pyshark, PIL/Pillow

Always include comments explaining each step of the exploit."""

EXPLOIT_SYNTHESIS_USER = """Write a complete working exploit for this CTF challenge:

Challenge: {challenge_description}
Category: {category}
Vulnerability class: {vuln_class}
Target: {target_info}

Additional context:
{context}

Write the complete exploit code:"""


# ─── Challenge generation: create novel CTF challenges for RL training ─────────

CHALLENGE_GENERATION_SYSTEM = """You are a senior CTF challenge author. Design novel, solvable CTF challenges with complete solutions.

A good CTF challenge:
1. Has one clear vulnerability or puzzle at its core
2. Requires a specific technique (not brute force)
3. Has a unique, verifiable flag
4. Teaches something about security or cryptography

Output format (JSON):
{
  "title": "challenge name",
  "category": "web|pwn|crypto|forensics|rev|osint|steg",
  "description": "what players see — includes connection info, file download, hint",
  "difficulty": "easy|medium|hard",
  "points": 100-500,
  "flag": "FLAG{unique_flag_here}",
  "solution": {
    "reasoning": ["step 1", "step 2", ...],
    "exploit": "complete exploit code",
    "key_insight": "the one thing you need to realize to solve this"
  },
  "deployment": {
    "type": "docker|static|nc",
    "dockerfile": "FROM python:3.11\\n...",
    "files": {"challenge.py": "..."}
  }
}"""

CHALLENGE_GENERATION_USER = """Generate a novel CTF challenge with these constraints:

Category: {category}
Difficulty: {difficulty}
Technique: {technique}
Inspiration competition: {competition}

The challenge should NOT appear in any existing CTF competition.
Make the flag unique: FLAG{{novel_{category}_{technique}_challenge}}

Output the complete challenge JSON:"""


# ─── DPO: writeup quality preference pairs ────────────────────────────────────

DPO_QUALITY_CHOSEN_SYSTEM = """You are a master CTF player writing a high-quality competition writeup.

A great writeup:
1. Explains your initial analysis and what caught your eye
2. Describes your reasoning process including failed approaches
3. Shows the exact exploit with comments
4. Explains what you learned from this challenge
5. Uses precise security terminology correctly

Write like you're teaching another CTF player."""

DPO_QUALITY_REJECTED_SYSTEM = """You are writing a minimal CTF writeup.

A minimal writeup just:
1. Names the vulnerability
2. Pastes the exploit script
3. Shows the flag

No reasoning, no explanation of WHY, no teaching."""

DPO_SYNTHESIS_USER = """Write a {quality} writeup for this CTF challenge:

Challenge: {challenge_description}
Category: {category}
Flag: {flag}
Solution approach: {solution}"""
