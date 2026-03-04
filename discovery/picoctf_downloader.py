"""
picoctf_downloader.py - Download picoCTF archives and pwn.college curricula.

picoCTF is a free educational CTF platform with well-structured problems.
Each problem has a clean description, hints, and point value.
Community writeups exist for most problems.

Output: data/raw/picoctf/{year}_{challenge_name}.json
"""

import json
import time
from pathlib import Path

import requests
from loguru import logger


PICOCTF_API = "https://play.picoctf.org/api"
PWNCOLLEGE_BASE = "https://pwn.college"


class PicoCTFDownloader:
    """Download picoCTF problem archives + community writeup links."""

    COMPETITIONS = {
        "2024": "picoctf-2024",
        "2023": "picoctf-2023",
        "2022": "picoctf-2022",
        "2021": "picoctf-2021",
        "2019": "picoctf-2019",
        "2018": "picoctf-2018",
        "2017": "picoctf-2017",
        "2014": "picoctf-2014",
        "2013": "picoctf-2013",
    }

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "FlagFoundry Research"

    def download_all(self) -> int:
        """Download all picoCTF competition archives."""
        total = 0
        for year, competition_id in self.COMPETITIONS.items():
            n = self._download_competition(year, competition_id)
            logger.info(f"picoCTF {year}: {n} challenges downloaded")
            total += n
        return total

    def _download_competition(self, year: str, competition_id: str) -> int:
        """Download all challenges for a single competition year."""
        saved = 0
        problems = self._fetch_problems(competition_id)

        for problem in problems:
            out_path = (
                self.output_dir
                / f"{year}_{problem['id']}_{problem.get('name', 'unknown')[:40]}.json"
            )
            if out_path.exists():
                continue

            record = {
                "source": "picoctf",
                "year": year,
                "competition": competition_id,
                "id": problem.get("id"),
                "name": problem.get("name", ""),
                "category": (problem.get("category", "") or "").lower(),
                "description": problem.get("description", ""),
                "hints": problem.get("hints", []),
                "points": problem.get("score", problem.get("points", 0)),
                "solve_count": problem.get("solves", 0),
                "flag_format": problem.get("flag_prefix", "picoCTF{"),
                "crawled_at": time.time(),
            }

            out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            saved += 1
            time.sleep(0.1)

        return saved

    def _fetch_problems(self, competition_id: str) -> list[dict]:
        """Fetch problem list for a competition from the picoCTF API."""
        try:
            resp = self._session.get(
                f"{PICOCTF_API}/problems/",
                params={"competition": competition_id, "limit": 500},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", data if isinstance(data, list) else [])
        except Exception as e:
            logger.warning(f"picoCTF API error for {competition_id}: {e}")

        return self._fetch_problems_fallback(competition_id)

    def _fetch_problems_fallback(self, competition_id: str) -> list[dict]:
        """Fallback: scrape the picoCTF practice problems page."""
        # Attempt to use public practice endpoint
        try:
            resp = self._session.get(
                "https://play.picoctf.org/practice",
                timeout=10,
            )
            if resp.status_code == 200:
                # Extract problem data from page HTML / embedded JSON.
                # Use raw_decode starting from the matched position to avoid
                # greedy regex over-capture with nested arrays/objects.
                import re

                m = re.search(r'"problems"\s*:\s*(\[)', resp.text, re.DOTALL)
                if m:
                    try:
                        arr, _ = json.JSONDecoder().raw_decode(resp.text, m.start(1))
                        return arr
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass  # intentional: fallback scrape is best-effort
        return []


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download picoCTF archives")
    parser.add_argument("--output-dir", default="data/raw/picoctf")
    parser.add_argument("--years", nargs="+", help="Specific years to download")
    args = parser.parse_args()

    dl = PicoCTFDownloader(output_dir=Path(args.output_dir))
    if args.years:
        total = 0
        for year in args.years:
            if year in dl.COMPETITIONS:
                n = dl._download_competition(year, dl.COMPETITIONS[year])
                total += n
            else:
                logger.warning(f"Year {year} not in known competitions")
        print(f"Downloaded {total:,} challenges")
    else:
        n = dl.download_all()
        print(f"Downloaded {n:,} challenges total")
