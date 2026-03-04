"""
discovery/github_ctf_repos.py — Search GitHub for CTF writeup repositories and
extract challenge solutions, exploit techniques, and flag capture methods.

Search strategy:
  1. GitHub search API: repos with "ctf writeup" / "ctf-writeups" / "ctf solutions"
  2. Topic search: topic:ctf, topic:ctf-writeups, topic:capture-the-flag
  3. Crawl known CTF organization accounts
  4. Parse README.md and writeup .md files for challenge descriptions + solutions

Output per repo:
  - challenge descriptions
  - vulnerability type categorization
  - exploit techniques and code
  - flag format patterns

Usage:
    python discovery/github_ctf_repos.py \
        --output data/raw/github_ctf \
        --max-repos 5000 \
        --max-files-per-repo 50
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import aiohttp
import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
VLLM_URLS = os.environ.get(
    "VLLM_URLS",
    "http://localhost:8001,http://localhost:8002,http://localhost:8003,http://localhost:8004",
).split(",")

GH_API_BASE = "https://api.github.com"
REQUEST_DELAY = 0.8  # seconds between GitHub API calls


def _gh_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


# GitHub search queries for CTF writeup repositories
GITHUB_SEARCH_QUERIES: list[str] = [
    "ctf-writeups in:name,description",
    "ctf writeup in:name,description",
    "capture-the-flag writeup in:name,description",
    "ctf solutions exploit in:readme",
    "ctf 2024 writeup in:name",
    "ctf 2023 writeup in:name",
    "ctf 2022 writeup in:name",
    "pwn rev crypto web forensics ctf in:readme",
    "hackthebox writeup solution in:name",
    "picoctf writeup solution in:name",
    "ctftime writeup in:name,description",
    "binary exploitation ctf writeup in:readme",
    "web exploitation ctf writeup in:readme",
    "cryptography ctf writeup in:readme",
    "reverse engineering ctf writeup in:readme",
]

# Known CTF organizations on GitHub with high-quality writeups
KNOWN_CTF_ORGS: list[str] = [
    "shellphish",
    "perfectblue",
    "idekCTF",
    "redpwn",
    "Dragon-Sec",
    "pwn-noobs",
    "dcua",
    "angstromctf",
    "DownUnderCTF",
    "NahamCon",
    "CyberSecurityRumble",
    "ritsec",
    "b01lers",
    "bluehens",
    "kalmarunionen",
    "c0r3dump",
    "RealWorldCTF",
    "justCTF",
    "HackTM",
    "sekai-ctf",
    "maple-ctf",
    "team-rocketm",
    "allesctf",
    "teamrocketist",
]

# File patterns to look for in CTF repos
WRITEUP_FILE_PATTERNS: list[str] = [
    r"(?i)readme\.md$",
    r"(?i)writeup\.md$",
    r"(?i)solution\.md$",
    r"(?i)solve\.md$",
    r"(?i).*writeup.*\.md$",
    r"(?i).*solution.*\.md$",
    r"(?i).*exploit.*\.py$",
    r"(?i).*solve.*\.py$",
    r"(?i).*pwn.*\.py$",
]

# CTF challenge categories / vulnerability types
CHALLENGE_CATEGORIES: dict[str, list[str]] = {
    "pwn": [
        "buffer overflow", "stack overflow", "heap overflow", "use-after-free",
        "format string", "ret2libc", "rop chain", "shellcode", "pwntools",
        "arbitrary write", "arbitrary read", "tcache", "fastbin", "off-by-one",
    ],
    "web": [
        "sql injection", "xss", "csrf", "ssrf", "xxe", "path traversal",
        "command injection", "deserialization", "jwt", "oauth", "graphql",
        "race condition", "prototype pollution", "template injection",
    ],
    "crypto": [
        "rsa", "aes", "des", "ecc", "diffie-hellman", "xor", "padding oracle",
        "bit flipping", "cbc", "ctr", "ecb", "sha", "md5", "hash extension",
        "lcg", "prng", "lattice", "coppersmith", "bleichenbacher",
    ],
    "rev": [
        "reverse engineering", "decompile", "ghidra", "ida", "radare2",
        "angr", "z3", "anti-debug", "obfuscation", "packing", "upx",
        "vm", "bytecode", "wasm",
    ],
    "forensics": [
        "steganography", "stego", "pcap", "wireshark", "memory forensics",
        "volatility", "disk image", "file carving", "metadata", "exif",
        "binwalk", "strings",
    ],
    "misc": [
        "jail escape", "pyjail", "sandbox escape", "osint", "networking",
        "blockchain", "smart contract", "solidity", "base64", "encoding",
    ],
}


def _classify_challenge(text: str) -> dict[str, Any]:
    """
    Classify a CTF challenge/writeup by category and vulnerability type.
    Returns {category, vulnerability_types, difficulty_indicators}.
    """
    text_lower = text.lower()
    found_categories: dict[str, list[str]] = {}

    for cat, keywords in CHALLENGE_CATEGORIES.items():
        matches = [kw for kw in keywords if kw in text_lower]
        if matches:
            found_categories[cat] = matches

    primary_category = max(found_categories, key=lambda k: len(found_categories[k])) if found_categories else "misc"

    # Difficulty heuristics
    difficulty_indicators: list[str] = []
    if any(w in text_lower for w in ["beginner", "easy", "basic", "intro"]):
        difficulty_indicators.append("easy")
    if any(w in text_lower for w in ["medium", "intermediate"]):
        difficulty_indicators.append("medium")
    if any(w in text_lower for w in ["hard", "advanced", "expert", "god"]):
        difficulty_indicators.append("hard")
    if any(w in text_lower for w in ["1000", "500 pts", "400 pts", "difficult"]):
        difficulty_indicators.append("hard")

    return {
        "primary_category": primary_category,
        "categories": list(found_categories.keys()),
        "vulnerability_types": found_categories.get(primary_category, []),
        "difficulty": difficulty_indicators[0] if difficulty_indicators else "unknown",
    }


def _extract_flag_patterns(text: str) -> list[str]:
    """Extract flag format patterns from writeup text."""
    flag_patterns = [
        r"flag\{[^}]{3,60}\}",
        r"ctf\{[^}]{3,60}\}",
        r"FLAG\{[^}]{3,60}\}",
        r"[A-Z]{2,8}\{[^}]{3,60}\}",
        r"flag is: ([^\n]{5,60})",
        r"the flag[: ]+([A-Za-z0-9_\-\{\}]+)",
    ]
    found: list[str] = []
    for pattern in flag_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found.extend(matches[:3])
    return list(set(found))[:5]


def _extract_exploit_code(text: str) -> list[str]:
    """Extract Python exploit code snippets from markdown."""
    code_blocks: list[str] = []
    # Python code fences
    python_fences = re.findall(r"```(?:python|py)\s*([\s\S]*?)```", text)
    code_blocks.extend([b.strip() for b in python_fences if len(b.strip()) > 50])
    # Generic code fences that look like pwntools
    generic_fences = re.findall(r"```\s*(from pwn|import pwn|p = remote|io = remote[\s\S]*?)```", text)
    code_blocks.extend([b.strip() for b in generic_fences if len(b.strip()) > 50])
    return code_blocks[:5]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _gh_search_repos(query: str, page: int = 1, per_page: int = 100) -> dict[str, Any]:
    """Search GitHub repositories."""
    resp = requests.get(
        f"{GH_API_BASE}/search/repositories",
        params={
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(per_page, 100),
            "page": page,
        },
        headers=_gh_headers(),
        timeout=20,
    )
    if resp.status_code == 403:
        reset_time = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
        sleep_secs = max(0, reset_time - int(time.time())) + 5
        logger.warning(f"GitHub rate limited — sleeping {sleep_secs}s")
        time.sleep(min(sleep_secs, 300))
        resp.raise_for_status()
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _gh_list_org_repos(org: str, page: int = 1, per_page: int = 100) -> list[dict]:
    """List public repos for a GitHub organization."""
    resp = requests.get(
        f"{GH_API_BASE}/orgs/{org}/repos",
        params={"per_page": min(per_page, 100), "page": page, "type": "public"},
        headers=_gh_headers(),
        timeout=20,
    )
    if resp.status_code in (404, 403):
        return []
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _gh_get_tree(owner: str, repo: str, sha: str = "HEAD") -> list[dict]:
    """Get repository file tree."""
    resp = requests.get(
        f"{GH_API_BASE}/repos/{owner}/{repo}/git/trees/{sha}",
        params={"recursive": "1"},
        headers=_gh_headers(),
        timeout=20,
    )
    if resp.status_code in (404, 403, 409):
        return []
    resp.raise_for_status()
    data = resp.json()
    return data.get("tree", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _gh_get_file_content(owner: str, repo: str, path: str) -> str | None:
    """Get file content from GitHub, base64-decoded."""
    resp = requests.get(
        f"{GH_API_BASE}/repos/{owner}/{repo}/contents/{path}",
        headers=_gh_headers(),
        timeout=20,
    )
    if resp.status_code in (404, 403):
        return None
    resp.raise_for_status()
    data = resp.json()
    if data.get("encoding") == "base64":
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None
    return data.get("content")


def _is_writeup_file(path: str) -> bool:
    """Check if a file path matches writeup/solution patterns."""
    for pattern in WRITEUP_FILE_PATTERNS:
        if re.search(pattern, path):
            return True
    return False


def _extract_writeup_record(
    owner: str,
    repo_name: str,
    file_path: str,
    content: str,
    repo_meta: dict,
) -> dict[str, Any] | None:
    """Parse a writeup file into a structured record."""
    if not content or len(content) < 100:
        return None

    classification = _classify_challenge(content)
    flag_patterns = _extract_flag_patterns(content)
    exploit_code = _extract_exploit_code(content)

    # Extract challenge name from path
    parts = file_path.split("/")
    challenge_name = parts[-2] if len(parts) >= 2 else parts[0]
    challenge_name = challenge_name.replace("-", " ").replace("_", " ")

    return {
        "source": "github",
        "repo": f"{owner}/{repo_name}",
        "repo_stars": repo_meta.get("stargazers_count", 0),
        "file_path": file_path,
        "challenge_name": challenge_name,
        "content": content[:8000],  # Cap at 8KB per writeup
        "content_length": len(content),
        "category": classification["primary_category"],
        "all_categories": classification["categories"],
        "vulnerability_types": classification["vulnerability_types"],
        "difficulty": classification["difficulty"],
        "flag_patterns": flag_patterns,
        "exploit_code_snippets": exploit_code,
        "has_exploit_code": len(exploit_code) > 0,
        "ctf_name": repo_meta.get("name", ""),
        "url": f"https://github.com/{owner}/{repo_name}/blob/HEAD/{file_path}",
        "repo_description": repo_meta.get("description", ""),
        "repo_topics": repo_meta.get("topics", []),
    }


class GitHubCTFCrawler:
    """
    Searches GitHub for CTF writeup repositories and extracts writeup content.

    Output:
      data/raw/github_ctf/repos.jsonl      — repository metadata
      data/raw/github_ctf/writeups.jsonl   — individual writeup records
    """

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._seen_repos: set[str] = set()

    def run(
        self,
        max_repos: int = 5000,
        max_files_per_repo: int = 50,
    ) -> dict[str, int]:
        repos: list[dict] = []

        # Phase 1: GitHub search
        logger.info("Phase 1: Searching GitHub for CTF writeup repos...")
        repos_per_query = max_repos // len(GITHUB_SEARCH_QUERIES)
        for query in GITHUB_SEARCH_QUERIES:
            batch = self._search_repos(query, limit=repos_per_query)
            repos.extend(batch)
            logger.info(f"  '{query[:50]}...': {len(batch)} repos")
            time.sleep(REQUEST_DELAY * 2)

        # Phase 2: Known CTF org repos
        logger.info("Phase 2: Crawling known CTF organization accounts...")
        for org in KNOWN_CTF_ORGS:
            try:
                org_repos = _gh_list_org_repos(org)
                for r in org_repos:
                    full_name = r.get("full_name", "")
                    if full_name not in self._seen_repos:
                        self._seen_repos.add(full_name)
                        repos.append(r)
                logger.debug(f"  {org}: {len(org_repos)} repos")
                time.sleep(REQUEST_DELAY)
            except Exception as exc:
                logger.debug(f"  {org}: {exc}")

        # Save repo list
        repos = repos[:max_repos]
        repos_path = self.output_dir / "repos.jsonl"
        with repos_path.open("w") as fh:
            for r in repos:
                fh.write(json.dumps({
                    "full_name": r.get("full_name", ""),
                    "name": r.get("name", ""),
                    "owner": r.get("owner", {}).get("login", "") if isinstance(r.get("owner"), dict) else "",
                    "stars": r.get("stargazers_count", 0),
                    "description": r.get("description", ""),
                    "topics": r.get("topics", []),
                    "url": r.get("html_url", ""),
                    "default_branch": r.get("default_branch", "HEAD"),
                }) + "\n")

        logger.info(f"Total repos: {len(repos)}")

        # Phase 3: Extract writeups from repos
        logger.info("Phase 3: Extracting writeup content from repos...")
        writeups: list[dict] = []
        for repo in repos[:max_repos]:
            owner_info = repo.get("owner", {})
            owner = owner_info.get("login", "") if isinstance(owner_info, dict) else ""
            repo_name = repo.get("name", "")
            if not owner or not repo_name:
                continue

            try:
                batch = self._extract_repo_writeups(
                    owner, repo_name, repo, max_files=max_files_per_repo
                )
                writeups.extend(batch)
                if batch:
                    logger.debug(f"  {owner}/{repo_name}: {len(batch)} writeups")
                time.sleep(REQUEST_DELAY)
            except Exception as exc:
                logger.debug(f"  {owner}/{repo_name}: {exc}")

        # Save writeups
        writeups_path = self.output_dir / "writeups.jsonl"
        with writeups_path.open("w") as fh:
            for w in writeups:
                fh.write(json.dumps(w) + "\n")

        # Category stats
        category_counts: dict[str, int] = {}
        for w in writeups:
            cat = w.get("category", "misc")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        stats = {
            "repos_found": len(repos),
            "writeups_extracted": len(writeups),
            "writeups_with_code": sum(1 for w in writeups if w.get("has_exploit_code")),
            "categories": category_counts,
        }
        logger.info(f"GitHub CTF crawl complete: {stats}")
        return stats

    def _search_repos(self, query: str, limit: int = 100) -> list[dict]:
        """Search for repos and return metadata list."""
        repos: list[dict] = []
        page = 1
        per_page = min(limit, 100)

        while len(repos) < limit:
            try:
                result = _gh_search_repos(query, page=page, per_page=per_page)
                items = result.get("items", [])
                if not items:
                    break
                for item in items:
                    full_name = item.get("full_name", "")
                    if full_name not in self._seen_repos:
                        self._seen_repos.add(full_name)
                        repos.append(item)
                if len(items) < per_page:
                    break
                page += 1
                time.sleep(REQUEST_DELAY)
            except Exception as exc:
                logger.debug(f"  Search error: {exc}")
                break

        return repos[:limit]

    def _extract_repo_writeups(
        self,
        owner: str,
        repo_name: str,
        repo_meta: dict,
        max_files: int = 50,
    ) -> list[dict]:
        """Extract writeup records from a single repository."""
        writeups: list[dict] = []
        try:
            tree = _gh_get_tree(owner, repo_name)
        except Exception:
            return []

        writeup_files = [
            item["path"] for item in tree
            if item.get("type") == "blob" and _is_writeup_file(item.get("path", ""))
        ][:max_files]

        for file_path in writeup_files:
            try:
                content = _gh_get_file_content(owner, repo_name, file_path)
                if content:
                    record = _extract_writeup_record(
                        owner, repo_name, file_path, content, repo_meta
                    )
                    if record:
                        writeups.append(record)
                time.sleep(0.3)
            except Exception as exc:
                logger.debug(f"    {file_path}: {exc}")

        return writeups


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl GitHub for CTF writeup repositories")
    parser.add_argument("--output", default="data/raw/github_ctf")
    parser.add_argument("--max-repos", type=int, default=5000)
    parser.add_argument("--max-files-per-repo", type=int, default=50)
    args = parser.parse_args()

    crawler = GitHubCTFCrawler(output_dir=args.output)
    stats = crawler.run(
        max_repos=args.max_repos,
        max_files_per_repo=args.max_files_per_repo,
    )
    logger.info("=== GitHub CTF Crawl Summary ===")
    for key, val in stats.items():
        if isinstance(val, dict):
            for subkey, subval in val.items():
                logger.info(f"  {key}/{subkey:<25} {subval:>5}")
        else:
            logger.info(f"  {key:<30} {val:>5}")
