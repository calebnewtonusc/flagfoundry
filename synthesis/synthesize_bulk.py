"""
synthesize_bulk.py - Async multi-writeup synthesis pipeline.

For each raw writeup in data/raw/, calls the LLM to extract:
  (challenge, reasoning, exploit, flag) → data/processed/{category}.jsonl

Supports two backends:
  --backend claude  : Anthropic Claude API (no GPU needed, rate-limited)
  --backend vllm    : Local vLLM servers (fast, requires 4+ A6000s)

Usage:
  # Claude API (laptop-friendly, slow)
  python synthesis/synthesize_bulk.py --backend claude

  # vLLM (fast, GPU required)
  python synthesis/synthesize_bulk.py --backend vllm \
    --vllm-urls http://localhost:8001 http://localhost:8002
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
import os
import random
import time
from typing import Any

import aiohttp
from loguru import logger

from synthesis.prompts import WRITEUP_TO_TRIPLE_SYSTEM, WRITEUP_TO_TRIPLE_USER

RAW_DIR = Path(__file__).parents[1] / "data" / "raw"
PROCESSED_DIR = Path(__file__).parents[1] / "data" / "processed"
CATEGORIES = ["web", "pwn", "crypto", "forensics", "rev", "osint", "steg", "misc"]


class SynthesisPipeline:
    """
    Main synthesis pipeline: raw writeups → structured (challenge, reasoning, exploit) triples.

    Supports Claude API and local vLLM as backends.
    Output: one JSONL per category in data/processed/.
    """

    def __init__(
        self,
        raw_dir: Path = RAW_DIR,
        output_dir: Path = PROCESSED_DIR,
        backend: str = "claude",
        vllm_urls: list[str] | None = None,
        concurrency: int = 20,
    ):
        self.raw_dir = Path(raw_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.backend = backend
        self.vllm_urls = vllm_urls or []
        self.concurrency = concurrency

        # Track already-synthesized writeup IDs
        self._done: set[str] = self._load_done()

    def _load_done(self) -> set[str]:
        """Load IDs of already-synthesized writeups."""
        done = set()
        for f in self.output_dir.glob("*.jsonl"):
            for line in f.read_text().splitlines():
                if line.strip():
                    try:
                        d = json.loads(line)
                        if "source_id" in d:
                            done.add(d["source_id"])
                    except Exception:
                        pass
        logger.info(f"Synthesis: {len(done):,} writeups already synthesized")
        return done

    def run(self) -> int:
        """Run the full synthesis pipeline. Returns count of new triples."""
        return asyncio.run(self._run_async())

    async def _run_async(self) -> int:
        """Async main loop."""
        raw_files = list(self.raw_dir.rglob("*.json"))
        pending = [f for f in raw_files if f.stem not in self._done]
        logger.info(f"Synthesis: {len(pending):,} writeups to process")

        if not pending:
            logger.info("All writeups already synthesized.")
            return 0

        # Open output files
        writers: dict[str, Any] = {}
        for cat in CATEGORIES:
            out_path = self.output_dir / f"{cat}.jsonl"
            writers[cat] = open(str(out_path), "a", encoding="utf-8")

        sem = asyncio.Semaphore(self.concurrency)
        # FF-26 FIX: Shared file handles are written from concurrent coroutines.
        # Create per-category asyncio Locks so only one coroutine writes to each
        # file at a time, preventing interleaved (corrupted) JSONL lines.
        writer_locks: dict[str, asyncio.Lock] = {
            cat: asyncio.Lock() for cat in CATEGORIES
        }
        connector = aiohttp.TCPConnector(limit=self.concurrency)

        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._synthesize_one(session, f, writers, sem, writer_locks)
                for f in pending
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for writer in writers.values():
            writer.close()

        n_saved = 0
        for r in results:
            if isinstance(r, BaseException):
                logger.error(f"Synthesis task raised an exception: {r}")
            elif r is True:
                n_saved += 1
        logger.info(f"Synthesis complete: {n_saved:,} new triples saved")
        return n_saved

    async def _synthesize_one(
        self,
        session: aiohttp.ClientSession,
        raw_file: Path,
        writers: dict,
        sem: asyncio.Semaphore,
        writer_locks: dict,
    ) -> bool:
        """Synthesize a single writeup into a structured triple."""
        async with sem:
            try:
                raw = json.loads(raw_file.read_text())
                raw_text = raw.get("raw_text", "")
                code_blocks = raw.get("code_blocks", [])

                if not raw_text or len(raw_text) < 200:
                    return False

                prompt_user = WRITEUP_TO_TRIPLE_USER.format(
                    raw_text=raw_text[:8000],
                    code_blocks="\n---\n".join(code_blocks[:5]),
                )

                response = await self._call_llm(
                    session, WRITEUP_TO_TRIPLE_SYSTEM, prompt_user
                )
                if not response:
                    return False

                triple = self._parse_response(response)
                if not triple:
                    return False

                # Validate quality
                quality = self._score_quality(triple)
                if quality < 0.5:
                    return False

                triple["quality_score"] = quality
                triple["source"] = raw.get("source", "unknown")
                triple["source_id"] = raw_file.stem
                triple["crawled_at"] = raw.get("crawled_at", time.time())

                category = triple.get("challenge", {}).get("category", "misc")
                if category not in CATEGORIES:
                    category = "misc"

                line = json.dumps(triple, ensure_ascii=False)
                # FF-26 FIX: Acquire per-category lock before writing to prevent
                # interleaved writes from concurrent coroutines corrupting JSONL.
                async with writer_locks[category]:
                    writers[category].write(line + "\n")
                    writers[category].flush()

                self._done.add(raw_file.stem)
                return True

            except Exception as e:
                logger.debug(f"Synthesis error for {raw_file.name}: {e}")
                return False

    async def _call_llm(
        self, session: aiohttp.ClientSession, system: str, user: str
    ) -> str | None:
        """Call the configured LLM backend."""
        if self.backend == "claude":
            return await self._call_claude(session, system, user)
        elif self.backend == "vllm":
            return await self._call_vllm(session, system, user)
        return None

    async def _call_claude(
        self, session: aiohttp.ClientSession, system: str, user: str
    ) -> str | None:
        """Call Anthropic Claude API."""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        # FF-12 FIX: Retry on 429 instead of sleeping and returning None (dropping the request)
        for attempt in range(3):
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"]
                elif resp.status == 429:
                    # Exponential backoff with jitter to avoid thundering herd on 429 errors
                    backoff = 30 * (2**attempt) + random.uniform(0, 10)
                    await asyncio.sleep(backoff)
                    continue  # retry after backoff
                else:
                    return None
        return None

    async def _call_vllm(
        self, session: aiohttp.ClientSession, system: str, user: str
    ) -> str | None:
        """Call a local vLLM server (OpenAI-compatible API)."""
        if not self.vllm_urls:
            raise RuntimeError("No vLLM URLs configured")

        # Round-robin across servers
        url = self.vllm_urls[hash(user) % len(self.vllm_urls)]
        payload = {
            "model": "Qwen/Qwen2.5-72B-Instruct",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 2048,
            "temperature": 0.3,
        }
        async with session.post(
            f"{url}/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {os.environ.get('VLLM_API_KEY', 'none')}"
            },
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
            return None

    def _parse_response(self, response: str) -> dict | None:
        """Parse LLM response into a structured triple."""
        # Try to extract JSON from the response
        response = response.strip()

        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block using raw_decode starting from the first '{'
        # so nested braces and large JSON objects are handled correctly
        first_brace = response.find("{")
        if first_brace != -1:
            try:
                obj, _ = json.JSONDecoder().raw_decode(response, first_brace)
                return obj
            except json.JSONDecodeError:
                pass

        return None

    def _score_quality(self, triple: dict) -> float:
        """Score a synthesized triple on 0-1 scale."""
        score = 0.0

        challenge = triple.get("challenge", {})
        reasoning = triple.get("reasoning", [])
        exploit = triple.get("exploit", "")

        # Challenge completeness
        if challenge.get("title"):
            score += 0.1
        if challenge.get("category") in CATEGORIES:
            score += 0.1
        if challenge.get("description") and len(challenge["description"]) > 20:
            score += 0.1

        # Reasoning depth
        if len(reasoning) >= 3:
            score += 0.2
        if len(reasoning) >= 5:
            score += 0.1
        # Steps should explain WHY not just WHAT
        long_steps = sum(1 for s in reasoning if len(str(s)) > 50)
        score += min(0.1, long_steps * 0.02)

        # Exploit quality
        if exploit and len(exploit) > 30:
            score += 0.1
        if "import" in exploit:
            score += 0.05
        if any(kw in exploit for kw in ["requests", "pwntools", "pwn.", "socket"]):
            score += 0.05

        # Flag present
        if triple.get("flag") and "{" in str(triple.get("flag", "")):
            score += 0.1

        return min(1.0, score)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Synthesize CTF training triples from writeups"
    )
    parser.add_argument("--backend", default="claude", choices=["claude", "vllm"])
    parser.add_argument("--vllm-urls", nargs="+", help="vLLM server URLs")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--output-dir", default="data/processed")
    args = parser.parse_args()

    pipeline = SynthesisPipeline(
        raw_dir=Path(args.raw_dir),
        output_dir=Path(args.output_dir),
        backend=args.backend,
        vllm_urls=args.vllm_urls,
        concurrency=args.concurrency,
    )
    n = pipeline.run()
    print(f"\nSynthesis complete: {n:,} new triples")
