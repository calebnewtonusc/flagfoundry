"""
challenge_generator.py - Generate novel CTF challenges for RL training.

Generates self-contained CTF challenges with:
- Complete problem description
- Docker deployment files
- Verified solution + exploit

These novel challenges feed the Stage 2 GRPO RL training loop:
  generate challenge → model attempts solve → Docker validates flag → reward signal

Usage:
  python synthesis/challenge_generator.py --category web --count 100
  python synthesis/challenge_generator.py --all --count 50 --difficulty hard
"""

import asyncio
import json
import os
import random
from pathlib import Path

import aiohttp
from loguru import logger

from synthesis.prompts import CHALLENGE_GENERATION_SYSTEM, CHALLENGE_GENERATION_USER

OUTPUT_DIR = Path(__file__).parents[1] / "data" / "challenges"

WEB_TECHNIQUES = [
    "SQL injection (blind, time-based)",
    "XSS via SVG upload",
    "SSRF to cloud metadata",
    "SSTI in Jinja2/Mako",
    "JWT algorithm confusion (RS256→HS256)",
    "OAuth2 state parameter bypass",
    "GraphQL introspection + injection",
    "XXE with custom DTD",
    "CORS misconfiguration with credential exfiltration",
    "Prototype pollution → RCE",
    "HTTP request smuggling",
    "Cache poisoning via unkeyed header",
]

PWN_TECHNIQUES = [
    "ret2win with one gadget",
    "ROP chain to execve('/bin/sh')",
    "tcache dup → fake chunk → arbitrary write",
    "House of Spirit",
    "format string → ASLR bypass → ROP",
    "off-by-one heap overflow",
    "stack pivot + SROP",
    "seccomp bypass via execveat",
]

CRYPTO_TECHNIQUES = [
    "RSA with small private exponent (Wiener's attack)",
    "Pohlig-Hellman on composite-order elliptic curve",
    "AES-CBC padding oracle",
    "ECDSA nonce reuse (k-reuse)",
    "Bleichenbacher's attack on RSA PKCS#1",
    "GCM nonce reuse",
    "LLL lattice reduction on knapsack",
    "Mersenne Twister state recovery",
]

FORENSICS_TECHNIQUES = [
    "PNG chunk manipulation (hidden data in IDAT)",
    "LSB steganography in BMP/PNG",
    "PCAP analysis: HTTP password in plaintext",
    "Memory forensics: Volatility profile extraction",
    "PDF with embedded JavaScript + obfuscated data",
    "Zip archive with password (crackable with rockyou)",
    "EXT4 filesystem deleted file recovery",
    "Registry hive analysis (Windows artifact)",
]

COMPETITIONS = [
    "PicoCTF", "CTFzone", "PlaidCTF", "DEFCON CTF Quals",
    "Google CTF", "hxp CTF", "DiceCTF", "CakeCTF",
]


class ChallengeGenerator:
    """Generates novel CTF challenges with verified solutions."""

    def __init__(
        self,
        output_dir: Path = OUTPUT_DIR,
        backend: str = "claude",
        vllm_urls: list[str] | None = None,
        concurrency: int = 5,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.backend = backend
        self.vllm_urls = vllm_urls or []
        self.concurrency = concurrency

    def generate(
        self,
        categories: list[str] | None = None,
        count: int = 50,
        difficulty: str = "medium",
    ) -> int:
        """Generate CTF challenges."""
        return asyncio.run(self._generate_async(categories, count, difficulty))

    async def _generate_async(
        self, categories: list[str] | None, count: int, difficulty: str
    ) -> int:
        """Async challenge generation loop."""
        tech_map = {
            "web": WEB_TECHNIQUES,
            "pwn": PWN_TECHNIQUES,
            "crypto": CRYPTO_TECHNIQUES,
            "forensics": FORENSICS_TECHNIQUES,
        }

        if categories:
            tech_map = {k: v for k, v in tech_map.items() if k in categories}

        tasks = []
        sem = asyncio.Semaphore(self.concurrency)
        connector = aiohttp.TCPConnector(limit=self.concurrency)

        async with aiohttp.ClientSession(connector=connector) as session:
            for _ in range(count):
                cat = random.choice(list(tech_map.keys()))
                technique = random.choice(tech_map[cat])
                competition = random.choice(COMPETITIONS)

                task = self._generate_one(
                    session, sem, cat, technique, difficulty, competition
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

        n = sum(1 for r in results if r is True)
        logger.info(f"Generated {n:,} challenges")
        return n

    async def _generate_one(
        self,
        session: aiohttp.ClientSession,
        sem: asyncio.Semaphore,
        category: str,
        technique: str,
        difficulty: str,
        competition: str,
    ) -> bool:
        """Generate a single challenge."""
        async with sem:
            prompt = CHALLENGE_GENERATION_USER.format(
                category=category,
                difficulty=difficulty,
                technique=technique,
                competition=competition,
            )

            response = await self._call_llm(session, CHALLENGE_GENERATION_SYSTEM, prompt)
            if not response:
                return False

            # Parse JSON from response
            import re
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if not match:
                return False

            try:
                challenge = json.loads(match.group())
            except json.JSONDecodeError:
                return False

            # Validate required fields
            if not all(k in challenge for k in ["title", "category", "flag", "solution"]):
                return False

            # Save challenge
            safe_title = re.sub(r"[^\w\-]", "_", challenge.get("title", "unknown"))[:50]
            out_path = self.output_dir / f"{category}_{safe_title}.json"
            out_path.write_text(json.dumps(challenge, ensure_ascii=False, indent=2))
            return True

    async def _call_llm(
        self, session: aiohttp.ClientSession, system: str, user: str
    ) -> str | None:
        """Call configured LLM backend."""
        if self.backend == "claude":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 3000,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    # FF-24 FIX: Explicit Content-Type header required by Anthropic API
                    "content-type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"]
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--category", nargs="+", choices=["web", "pwn", "crypto", "forensics"])
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    parser.add_argument("--backend", default="claude", choices=["claude", "vllm"])
    args = parser.parse_args()

    gen = ChallengeGenerator(backend=args.backend)
    n = gen.generate(categories=args.category, count=args.count, difficulty=args.difficulty)
    print(f"Generated {n:,} challenges to data/challenges/")
