"""
htb_crawler.py - Download HackTheBox writeups (machines + challenges).

HackTheBox is a premium platform with professional-quality challenges.
Retired machines have official walkthroughs released by HTB.
Active machines have community writeups on external blogs.

Output format: data/raw/htb/{machine_name}_{challenge_name}.json

Requires: HTB_API_TOKEN in .env (HackTheBox account settings → API Key)
"""

import json
import os
import time
from pathlib import Path

import requests
from loguru import logger


HTB_API_BASE = "https://www.hackthebox.com/api/v4"
HTB_BLOG_BASE = "https://app.hackthebox.com"


class HTBCrawler:
    """
    Downloads HackTheBox machine + challenge writeup metadata and content.

    Usage:
        crawler = HTBCrawler(output_dir=Path("data/raw/htb"))
        n = crawler.crawl_all()
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.api_token = os.environ.get("HTB_API_TOKEN", "")
        if not self.api_token:
            logger.warning("HTB_API_TOKEN not set — HTB crawling will be limited")

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_token}",
                "User-Agent": "FlagFoundry Research — flagfoundry@example.com",
            }
        )

    def crawl_all(self) -> int:
        """Download all accessible HTB machine + challenge writeups."""
        total = 0
        total += self._crawl_machines()
        total += self._crawl_challenges()
        return total

    def _crawl_machines(self) -> int:
        """Download retired machine metadata + writeup content."""
        logger.info("Fetching HTB retired machines list...")
        machines = self._get_retired_machines()
        logger.info(f"Found {len(machines):,} retired machines")

        saved = 0
        for machine in machines:
            out_path = (
                self.output_dir / f"machine_{machine['id']}_{machine['name']}.json"
            )
            if out_path.exists():
                continue

            writeup = self._fetch_machine_writeup(machine)
            if writeup:
                out_path.write_text(json.dumps(writeup, ensure_ascii=False, indent=2))
                saved += 1
                logger.debug(f"Saved machine: {machine['name']}")

            time.sleep(0.5)

        logger.info(f"HTB machines: {saved:,} writeups saved")
        return saved

    def _crawl_challenges(self) -> int:
        """Download HTB challenge writeup metadata."""
        logger.info("Fetching HTB challenges list...")
        challenges = self._get_challenges()
        logger.info(f"Found {len(challenges):,} challenges")

        saved = 0
        for challenge in challenges:
            out_path = (
                self.output_dir
                / f"challenge_{challenge['id']}_{challenge['name']}.json"
            )
            if out_path.exists():
                continue

            writeup = self._fetch_challenge_writeup(challenge)
            if writeup:
                out_path.write_text(json.dumps(writeup, ensure_ascii=False, indent=2))
                saved += 1

            time.sleep(0.3)

        logger.info(f"HTB challenges: {saved:,} writeups saved")
        return saved

    def _get_retired_machines(self) -> list[dict]:
        """Fetch list of all retired HTB machines."""
        machines = []
        page = 1
        while True:
            try:
                resp = self._session.get(
                    f"{HTB_API_BASE}/machine/list/retired/paginated",
                    params={"per_page": 100, "page": page},
                    timeout=10,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                batch = data.get("data", [])
                if not batch:
                    break
                machines.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"Error fetching machines page {page}: {e}")
                break
        return machines

    def _get_challenges(self) -> list[dict]:
        """Fetch list of all HTB challenges."""
        try:
            resp = self._session.get(
                f"{HTB_API_BASE}/challenge/list",
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("challenges", [])
        except Exception as e:
            logger.warning(f"Error fetching challenges: {e}")
        return []

    def _fetch_machine_writeup(self, machine: dict) -> dict | None:
        """Fetch writeup content for a single machine."""
        machine_id = machine.get("id")
        machine_name = machine.get("name", "unknown")
        if not machine_id:
            logger.warning(f"Skipping machine with missing ID: {machine_name}")
            return None
        os_type = machine.get("os", "Linux")
        difficulty = machine.get("difficultyText", "Medium")
        category_tags = machine.get("tags", [])

        # Attempt to fetch official walkthrough
        official_writeup = self._fetch_official_walkthrough(machine_id)

        return {
            "source": "htb",
            "type": "machine",
            "name": machine_name,
            "machine_id": machine_id,
            "os": os_type,
            "difficulty": difficulty,
            "tags": category_tags,
            "category": self._infer_category_from_tags(category_tags),
            "official_writeup": official_writeup,
            "official_writeup_url": f"https://www.hackthebox.com/machine/{machine_id}",
            "crawled_at": time.time(),
        }

    def _fetch_challenge_writeup(self, challenge: dict) -> dict | None:
        """Fetch writeup metadata for a single challenge."""
        return {
            "source": "htb",
            "type": "challenge",
            "name": challenge.get("name", ""),
            "challenge_id": challenge.get("id"),
            "category": (challenge.get("category_name", "") or "").lower(),
            "difficulty": challenge.get("difficulty", ""),
            "description": challenge.get("description", ""),
            "points": challenge.get("points", 0),
            "solved_count": challenge.get("solves", 0),
            "crawled_at": time.time(),
        }

    def _fetch_official_walkthrough(self, machine_id: int) -> str | None:
        """Attempt to fetch official HTB walkthrough text."""
        try:
            resp = self._session.get(
                f"{HTB_API_BASE}/machine/writeup/{machine_id}",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("writeup", None)
        except Exception:
            pass
        return None

    def _infer_category_from_tags(self, tags: list) -> str:
        """Map HTB machine tags to CTF category."""
        tag_text = " ".join(str(t).lower() for t in tags)
        if any(k in tag_text for k in ["web", "http", "sql", "api"]):
            return "web"
        if any(k in tag_text for k in ["buffer", "overflow", "rop", "pwn", "exploit"]):
            return "pwn"
        if any(k in tag_text for k in ["crypto", "hash", "rsa", "aes"]):
            return "crypto"
        if any(k in tag_text for k in ["forensic", "memory", "pcap", "log"]):
            return "forensics"
        if any(k in tag_text for k in ["reverse", "binary", "disassem"]):
            return "rev"
        return "misc"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download HackTheBox writeups")
    parser.add_argument("--output-dir", default="data/raw/htb")
    parser.add_argument("--machines-only", action="store_true")
    parser.add_argument("--challenges-only", action="store_true")
    args = parser.parse_args()

    crawler = HTBCrawler(output_dir=Path(args.output_dir))
    if args.machines_only:
        n = crawler._crawl_machines()
    elif args.challenges_only:
        n = crawler._crawl_challenges()
    else:
        n = crawler.crawl_all()
    print(f"\nSaved {n:,} writeups to {args.output_dir}/")
