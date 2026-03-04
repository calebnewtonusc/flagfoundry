"""
flagbench.py - FlagBench: 500-challenge evaluation suite for CTF AI models.

FlagBench is the first standardized benchmark for AI-assisted CTF solving.
500 challenges across 7 categories, each verified by Docker sandbox execution.

The benchmark covers:
  Web:      100 challenges (SQLi, XSS, SSRF, SSTI, LFI, IDOR, OAuth, JWT, XXE, ...)
  Pwn:      100 challenges (BOF, ROP, heap, format string, shellcode, ...)
  Crypto:   100 challenges (RSA, AES, ECC, XOR, hash, custom crypto, ...)
  Forensics: 75 challenges (PCAP, memory, disk, file carving, ...)
  Rev:       75 challenges (static analysis, decompile, anti-debug, ...)
  OSINT:     25 challenges (domain, social, geolocation, ...)
  Steg:      25 challenges (LSB, DCT, audio, spectral, ...)

Usage:
  python evaluation/flagbench.py --model checkpoints/flagfoundry-final --all
  python evaluation/flagbench.py --model checkpoints/flagfoundry-final --category web
  python evaluation/flagbench.py --model checkpoints/flagfoundry-final --category crypto --limit 10
"""

import argparse
import json
import signal
import time
from pathlib import Path
from typing import Optional

from loguru import logger


class _SolveTimeout(Exception):
    """Raised when orchestrator.solve() exceeds the per-challenge timeout."""


def _timeout_handler(signum, frame):
    raise _SolveTimeout("solve() timed out")


BENCHMARK_DIR = Path(__file__).parent / "challenges"
RESULTS_DIR = Path(__file__).parents[1] / "results"

CATEGORY_TARGETS = {
    "web":      {"count": 100, "target_solve_rate": 0.75},
    "pwn":      {"count": 100, "target_solve_rate": 0.55},
    "crypto":   {"count": 100, "target_solve_rate": 0.80},
    "forensics": {"count": 75, "target_solve_rate": 0.70},
    "rev":      {"count": 75,  "target_solve_rate": 0.60},
    "osint":    {"count": 25,  "target_solve_rate": 0.60},
    "steg":     {"count": 25,  "target_solve_rate": 0.65},
}


class FlagBench:
    """
    FlagBench evaluation runner.

    For each challenge:
      1. Load challenge description + file
      2. Run FlagFoundry model to generate exploit
      3. Execute in Docker sandbox
      4. Record: flag captured (binary), time taken
    """

    def __init__(
        self,
        model_path: str,
        device: str = "auto",
        timeout: int = 60,
        docker_workers: int = 4,
    ):
        self.model_path = model_path
        self.device = device
        self.timeout = timeout
        self.docker_workers = docker_workers

        self._orchestrator = None
        self._sandbox = None

    def _load_orchestrator(self):
        if self._orchestrator is not None:
            return
        from agents.orchestrator_agent import OrchestratorAgent
        self._orchestrator = OrchestratorAgent(model_path=self.model_path, device=self.device)

    def _load_sandbox(self):
        if self._sandbox is not None:
            return
        from core.sandbox_harness import SandboxHarness
        self._sandbox = SandboxHarness(timeout=self.timeout)

    def run(
        self,
        categories: list[str] | None = None,
        limit: Optional[int] = None,
    ) -> dict:
        """
        Run FlagBench evaluation.

        Returns results dict with per-category and overall metrics.
        """
        self._load_orchestrator()
        self._load_sandbox()

        categories = categories or list(CATEGORY_TARGETS.keys())
        all_results = {}

        for category in categories:
            challenges = self._load_challenges(category)
            if limit:
                challenges = challenges[:limit]

            if not challenges:
                logger.warning(f"No challenges found for category: {category}")
                continue

            logger.info(f"\nFlagBench — {category}: {len(challenges)} challenges")
            cat_results = self._run_category(category, challenges)
            all_results[category] = cat_results
            self._print_category_summary(category, cat_results)

        overall = self._compute_overall(all_results)
        self._save_results(all_results, overall)
        self._print_final_summary(all_results, overall)
        return {"categories": all_results, "overall": overall}

    def _run_category(self, category: str, challenges: list[dict]) -> dict:
        """Run all challenges in a category."""
        solved = 0
        total = len(challenges)
        times = []
        failures = []

        for i, challenge in enumerate(challenges):
            logger.debug(f"  [{i+1}/{total}] {challenge.get('title', 'unknown')}")
            start = time.time()

            try:
                # FF-25 FIX: Wrap orchestrator.solve() in a SIGALRM timeout so a
                # hung LLM call or stalled subprocess does not block the benchmark run.
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(self.timeout)
                try:
                    result = self._orchestrator.solve(
                        description=challenge["description"],
                        file_bytes=challenge.get("file_bytes"),
                        filename=challenge.get("filename"),
                        category_override=category,
                    )
                finally:
                    signal.alarm(0)  # Cancel alarm

                elapsed = time.time() - start
                times.append(elapsed)

                # Verify flag via Docker sandbox
                exploit_code = result.get("exploit", "")
                expected_flag = challenge["flag"]

                sandbox_result = self._sandbox.run_exploit(
                    exploit_code=exploit_code,
                    challenge_id=challenge["id"],
                    expected_flag=expected_flag,
                )

                if sandbox_result.reward_score == 1.0:
                    solved += 1
                    logger.debug(f"    ✓ Flag captured in {elapsed:.1f}s")
                else:
                    failures.append({
                        "challenge_id": challenge["id"],
                        "title": challenge.get("title"),
                        "error": sandbox_result.error,
                    })
                    logger.debug(f"    ✗ Not solved ({elapsed:.1f}s)")

            except _SolveTimeout as e:
                logger.warning(f"    Timeout on challenge {challenge.get('id')}: {e}")
                failures.append({"challenge_id": challenge.get("id"), "error": "timeout"})
                times.append(time.time() - start)
            except Exception as e:
                logger.warning(f"    Error on challenge {challenge.get('id')}: {e}")
                failures.append({"challenge_id": challenge.get("id"), "error": str(e)})
                times.append(time.time() - start)

        solve_rate = solved / total if total > 0 else 0.0
        target = CATEGORY_TARGETS.get(category, {}).get("target_solve_rate", 0.5)

        return {
            "category": category,
            "total": total,
            "solved": solved,
            "solve_rate": solve_rate,
            "target_solve_rate": target,
            "meets_target": solve_rate >= target,
            "mean_time": sum(times) / len(times) if times else 0.0,
            "failures": failures[:10],  # cap at 10 for readability
        }

    def _load_challenges(self, category: str) -> list[dict]:
        """Load benchmark challenges for a category."""
        challenges = []
        cat_dir = BENCHMARK_DIR / category

        if not cat_dir.exists():
            # Try loading from embedded manifest
            manifest = BENCHMARK_DIR / "manifest.json"
            if manifest.exists():
                all_challenges = json.loads(manifest.read_text())
                return [c for c in all_challenges if c.get("category") == category]
            return []

        for f in sorted(cat_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                # Only load file_bytes when filename is explicitly specified in the
                # challenge record.  Using f.name as a fallback causes the .json
                # metadata file itself to be read as the challenge binary.
                explicit_filename = data.get("filename")
                if explicit_filename:
                    file_path = cat_dir / explicit_filename
                    if file_path.exists():
                        data["file_bytes"] = file_path.read_bytes()
                challenges.append(data)
            except Exception as e:
                logger.debug(f"Error loading challenge {f}: {e}")

        return challenges

    def _compute_overall(self, all_results: dict) -> dict:
        """Compute overall benchmark statistics."""
        total = sum(r["total"] for r in all_results.values())
        solved = sum(r["solved"] for r in all_results.values())
        categories_passing = sum(1 for r in all_results.values() if r.get("meets_target"))

        return {
            "total_challenges": total,
            "total_solved": solved,
            "overall_solve_rate": solved / total if total > 0 else 0.0,
            "categories_passing_target": categories_passing,
            "total_categories": len(all_results),
        }

    def _print_category_summary(self, category: str, results: dict):
        """Print per-category results."""
        rate = results["solve_rate"]
        target = results["target_solve_rate"]
        status = "PASS" if results["meets_target"] else "FAIL"
        logger.info(
            f"  {category:<12} {results['solved']:>3}/{results['total']} "
            f"({rate:.1%}) target={target:.0%} [{status}]"
        )

    def _print_final_summary(self, all_results: dict, overall: dict):
        """Print final benchmark summary."""
        logger.info("\n" + "=" * 60)
        logger.info("FLAGBENCH RESULTS")
        logger.info("=" * 60)

        for cat, results in all_results.items():
            status = "PASS" if results["meets_target"] else "FAIL"
            logger.info(
                f"  {cat:<12} {results['solved']:>3}/{results['total']:>3} "
                f"({results['solve_rate']:>6.1%})  [{status}]"
            )

        logger.info("-" * 60)
        logger.info(
            f"  {'OVERALL':<12} {overall['total_solved']:>3}/{overall['total_challenges']:>3} "
            f"({overall['overall_solve_rate']:>6.1%})"
        )
        logger.info(
            f"  Categories meeting target: "
            f"{overall['categories_passing_target']}/{overall['total_categories']}"
        )
        logger.info("=" * 60)

    def _save_results(self, all_results: dict, overall: dict):
        """Save results to JSON file."""
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RESULTS_DIR / f"flagbench_{int(time.time())}.json"
        out_path.write_text(json.dumps({
            "model": self.model_path,
            "timestamp": time.time(),
            "categories": all_results,
            "overall": overall,
        }, indent=2))
        logger.info(f"Results saved to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="FlagBench — CTF AI evaluation suite")
    parser.add_argument("--model", required=True, help="Model path or HF model ID")
    parser.add_argument("--all", action="store_true", help="Run all categories")
    parser.add_argument("--category", nargs="+",
                        choices=list(CATEGORY_TARGETS.keys()),
                        help="Specific categories to evaluate")
    parser.add_argument("--limit", type=int, help="Limit challenges per category")
    parser.add_argument("--timeout", type=int, default=60, help="Exploit timeout (seconds)")
    parser.add_argument("--docker-workers", type=int, default=4)
    args = parser.parse_args()

    categories = None
    if args.all:
        categories = list(CATEGORY_TARGETS.keys())
    elif args.category:
        categories = args.category

    if not categories:
        parser.print_help()
        return

    bench = FlagBench(
        model_path=args.model,
        timeout=args.timeout,
        docker_workers=args.docker_workers,
    )
    bench.run(categories=categories, limit=args.limit)


if __name__ == "__main__":
    main()
