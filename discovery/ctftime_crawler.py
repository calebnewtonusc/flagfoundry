"""
ctftime_crawler.py - Scrape CTFtime.org writeup links and fetch external writeup pages.

CTFtime.org is the central registry of CTF competitions and writeup links.
This crawler:
  1. Fetches the list of past events from the CTFtime API
  2. For each event, fetches all writeup submissions
  3. For each writeup, fetches the external URL content (blog, GitHub, HackMD)
  4. Parses into raw writeup files for synthesis

Output format (per writeup):
  data/raw/ctftime/{event_id}_{challenge_id}.json:
  {
    "event": "PicoCTF 2024",
    "challenge": "SQL Injection 101",
    "category": "web",
    "points": 200,
    "writeup_url": "https://blog.example.com/pico-2024-sqli",
    "raw_text": "...",
    "raw_html": "...",
    "author": "team_pwn",
    "source": "ctftime"
  }
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger


CTFTIME_API = "https://ctftime.org/api/v1"
WRITEUP_LIST_URL = "https://ctftime.org/writeups/"
REQUEST_DELAY = 0.5  # seconds between requests to avoid rate limiting


class CTFtimeCrawler:
    """
    Async crawler for CTFtime.org writeup links and external writeup content.

    Usage:
        crawler = CTFtimeCrawler(output_dir=Path("data/raw/ctftime"), workers=30)
        n = crawler.crawl_all(years=range(2010, 2026))
    """

    def __init__(
        self,
        output_dir: Path,
        workers: int = 30,
        session_cookie: Optional[str] = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workers = workers
        self.session_cookie = session_cookie or os.environ.get("CTFTIME_SESSION", "")

        # Track seen URLs to avoid re-crawling
        self._seen: set[str] = set()
        self._load_seen()

    def _load_seen(self):
        """Load already-crawled writeup IDs from disk."""
        for f in self.output_dir.glob("*.json"):
            self._seen.add(f.stem)
        logger.info(
            f"CTFtime crawler: {len(self._seen):,} already-crawled writeups found"
        )

    def crawl_all(self, years: range | None = None) -> int:
        """Crawl all CTFtime writeups (optionally filtered by year)."""
        return asyncio.run(self._crawl_all_async(years))

    async def _crawl_all_async(self, years: range | None) -> int:
        headers = {
            "User-Agent": "FlagFoundry Research Crawler — contact flagfoundry@example.com",
        }
        if self.session_cookie:
            headers["Cookie"] = f"sessionid={self.session_cookie}"

        connector = aiohttp.TCPConnector(limit=self.workers)
        async with aiohttp.ClientSession(
            headers=headers, connector=connector
        ) as session:
            events = await self._fetch_events(session, years)
            logger.info(f"Found {len(events):,} events to process")

            all_writeup_links = []
            for event in events:
                links = await self._fetch_event_writeups(session, event["id"])
                all_writeup_links.extend(links)
                await asyncio.sleep(REQUEST_DELAY)

            logger.info(f"Found {len(all_writeup_links):,} writeup links total")

            # Process writeups in parallel batches
            sem = asyncio.Semaphore(self.workers)
            tasks = [
                self._crawl_writeup(session, link, sem)
                for link in all_writeup_links
                if self._writeup_id(link) not in self._seen
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

        n_saved = sum(1 for r in results if r is True)
        logger.info(f"CTFtime crawl complete: {n_saved:,} new writeups saved")
        return n_saved

    async def _fetch_events(
        self, session: aiohttp.ClientSession, years: range | None
    ) -> list[dict]:
        """Fetch the CTFtime event list."""
        events = []
        try:
            year_range = years or range(2010, 2026)
            for year in year_range:
                url = f"{CTFTIME_API}/events/"
                params = {"limit": 200, "year": year}
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        events.extend(data)
                        logger.debug(f"Year {year}: {len(data)} events")
                await asyncio.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.warning(f"Error fetching events: {e}")
        return events

    async def _fetch_event_writeups(
        self, session: aiohttp.ClientSession, event_id: int
    ) -> list[dict]:
        """Fetch all writeup submissions for a single event."""
        url = f"{CTFTIME_API}/events/{event_id}/writeups/"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.debug(f"Event {event_id} writeups error: {e}")
        return []

    async def _crawl_writeup(
        self,
        session: aiohttp.ClientSession,
        writeup_meta: dict,
        sem: asyncio.Semaphore,
    ) -> bool:
        """Fetch a single writeup page and save to disk."""
        async with sem:
            writeup_id = self._writeup_id(writeup_meta)
            out_path = self.output_dir / f"{writeup_id}.json"

            if out_path.exists():
                return False

            url = writeup_meta.get("url", "")
            if not url:
                return False

            try:
                await asyncio.sleep(REQUEST_DELAY)
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        return False
                    html = await resp.text(errors="replace")

                soup = BeautifulSoup(html, "lxml")
                raw_text = soup.get_text(separator="\n", strip=True)

                # Extract code blocks separately for exploit synthesis
                code_blocks = [
                    code.get_text() for code in soup.find_all(["code", "pre"])
                ]

                record = {
                    "event": writeup_meta.get("event_title", ""),
                    "event_id": writeup_meta.get("event_id"),
                    "challenge": writeup_meta.get("task", ""),
                    "category": self._infer_category(writeup_meta),
                    "points": writeup_meta.get("points", 0),
                    "writeup_url": url,
                    "raw_text": raw_text[:50000],  # cap at 50k chars
                    "code_blocks": code_blocks[:20],  # cap at 20 blocks
                    "author": writeup_meta.get("author", ""),
                    "source": "ctftime",
                    "crawled_at": time.time(),
                }

                out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                self._seen.add(writeup_id)
                return True

            except Exception as e:
                logger.debug(f"Error crawling {url}: {e}")
                return False

    def _writeup_id(self, meta: dict) -> str:
        """Unique ID for a writeup."""
        event_id = meta.get("event_id", "0")
        challenge = meta.get("task", "unknown").replace(" ", "_")[:50]
        return f"{event_id}_{challenge}"

    def _infer_category(self, meta: dict) -> str:
        """Infer CTF category from metadata."""
        raw = (meta.get("category", "") or "").lower()
        mapping = {
            "web": "web",
            "sqli": "web",
            "xss": "web",
            "pwn": "pwn",
            "binary": "pwn",
            "exploit": "pwn",
            "crypto": "crypto",
            "cryptography": "crypto",
            "forensics": "forensics",
            "forensic": "forensics",
            "rev": "rev",
            "reverse": "rev",
            "reversing": "rev",
            "osint": "osint",
            "steg": "steg",
            "steganography": "steg",
            "misc": "misc",
        }
        for key, cat in mapping.items():
            if key in raw:
                return cat
        return "misc"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl CTFtime writeups")
    parser.add_argument("--output-dir", default="data/raw/ctftime")
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument(
        "--years", nargs="+", type=int, help="Years to crawl (default: 2010-2025)"
    )
    args = parser.parse_args()

    # FF-16 FIX: Iterate args.years directly instead of constructing a range that fills in
    # gaps between non-consecutive years (e.g., --years 2020 2023 should NOT include 2021/2022)
    year_range = args.years if args.years else None
    crawler = CTFtimeCrawler(output_dir=Path(args.output_dir), workers=args.workers)
    n = crawler.crawl_all(years=year_range)
    print(f"\nCrawled {n:,} writeups to {args.output_dir}/")
