"""
pipeline.py - End-to-end FlagFoundry dataset pipeline.

Usage:
    python pipeline.py                   # full run: collect + synthesize
    python pipeline.py --collect-only    # only collect writeups
    python pipeline.py --synth-only      # only run synthesis on existing raw files
    python pipeline.py --stats           # print dataset statistics
    python pipeline.py --solve           # interactive: solve a single challenge

This is the main entry point for building the FlagFoundry training dataset.
"""

import argparse
import json
from pathlib import Path

RAW_DIR = Path(__file__).parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).parent / "data" / "processed"
MASTER_JSONL = PROCESSED_DIR / "dataset.jsonl"


def run_collect(sources: list[str] | None = None, workers: int = 30):
    """Collect writeups from all configured sources."""
    if sources is None:
        sources = ["ctftime", "htb", "picoctf", "defcon", "cve_poc"]

    total_collected = 0

    if "ctftime" in sources:
        from discovery.ctftime_crawler import CTFtimeCrawler

        crawler = CTFtimeCrawler(output_dir=RAW_DIR / "ctftime", workers=workers)
        n = crawler.crawl_all(years=range(2010, 2026))
        print(f"CTFtime: {n:,} writeups collected")
        total_collected += n

    if "htb" in sources:
        from discovery.htb_crawler import HTBCrawler

        crawler = HTBCrawler(output_dir=RAW_DIR / "htb")
        n = crawler.crawl_all()
        print(f"HackTheBox: {n:,} writeups collected")
        total_collected += n

    if "picoctf" in sources:
        from discovery.picoctf_downloader import PicoCTFDownloader

        dl = PicoCTFDownloader(output_dir=RAW_DIR / "picoctf")
        n = dl.download_all()
        print(f"picoCTF: {n:,} problems downloaded")
        total_collected += n

    if "defcon" in sources:
        from discovery.defcon_crawler import DefconCrawler

        crawler = DefconCrawler(output_dir=RAW_DIR / "defcon")
        n = crawler.crawl_all()
        print(f"DEFCON/HITCON: {n:,} challenges collected")
        total_collected += n

    if "cve_poc" in sources:
        from discovery.github_poc_crawler import GitHubPoCCrawler

        crawler = GitHubPoCCrawler(output_dir=RAW_DIR / "cve_poc", limit=10000)
        n = crawler.crawl()
        print(f"CVE PoC: {n:,} exploits collected")
        total_collected += n

    print(f"\nTotal collected: {total_collected:,} items")
    return total_collected


def run_synthesize(backend: str = "claude", vllm_urls: list[str] | None = None):
    """Synthesize (challenge, reasoning, exploit) triples from raw writeups."""
    from synthesis.synthesize_bulk import SynthesisPipeline

    pipeline = SynthesisPipeline(
        raw_dir=RAW_DIR,
        output_dir=PROCESSED_DIR,
        backend=backend,
        vllm_urls=vllm_urls or [],
    )
    n = pipeline.run()
    print(f"\nSynthesis complete: {n:,} triples → {MASTER_JSONL}")
    return n


def print_stats():
    """Print current dataset statistics."""
    print("=== FLAGFOUNDRY DATASET STATS ===\n")

    category_counts: dict[str, int] = {}
    total = 0

    for cat_file in PROCESSED_DIR.glob("*.jsonl"):
        if cat_file == MASTER_JSONL:
            continue
        count = sum(1 for line in cat_file.read_text().splitlines() if line.strip())
        category_counts[cat_file.stem] = count
        total += count

    print(f"Total triples: {total:,}\n")
    print("By category:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        bar = "#" * (count // max(1, total // 50))
        print(f"  {cat:<20} {count:>6,}  {bar}")

    if MASTER_JSONL.exists():
        lines = [line for line in MASTER_JSONL.read_text().splitlines() if line.strip()]
        print(f"\nMaster dataset: {len(lines):,} triples")

        # Quality score distribution
        scores = []
        for line in lines[:1000]:  # sample
            try:
                d = json.loads(line)
                scores.append(d.get("quality_score", 0))
            except Exception:
                pass  # intentional: skip malformed lines in quality score sample

        if scores:
            avg = sum(scores) / len(scores)
            print(f"Avg quality score (sample): {avg:.3f}")


def solve_interactive():
    """Interactively solve a single CTF challenge."""
    from agents.orchestrator_agent import OrchestratorAgent

    agent = OrchestratorAgent(model_path="checkpoints/flagfoundry-final")

    print("FlagFoundry Interactive Solver")
    print("=" * 40)
    description = input("Challenge description: ").strip()
    file_path = input("Challenge file path (or press Enter to skip): ").strip()

    file_content = None
    if file_path and Path(file_path).exists():
        file_content = Path(file_path).read_bytes()

    result = agent.solve(description=description, file_bytes=file_content)

    print(f"\nCategory: {result['category']}")
    print("\nReasoning:")
    for i, step in enumerate(result["reasoning"], 1):
        print(f"  {i}. {step}")
    print("\nExploit:")
    print(result["exploit"])
    print(f"\nFlag: {result.get('flag', 'Not captured — check exploit output')}")


def main():
    parser = argparse.ArgumentParser(description="FlagFoundry dataset pipeline")
    parser.add_argument(
        "--collect-only", action="store_true", help="Only collect writeups"
    )
    parser.add_argument("--synth-only", action="store_true", help="Only run synthesis")
    parser.add_argument("--stats", action="store_true", help="Print dataset statistics")
    parser.add_argument(
        "--solve", action="store_true", help="Interactive challenge solver"
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["ctftime", "htb", "picoctf", "defcon", "cve_poc"],
        help="Data sources to collect (default: all)",
    )
    parser.add_argument(
        "--backend",
        default="claude",
        choices=["claude", "vllm"],
        help="Synthesis backend",
    )
    parser.add_argument("--vllm-urls", nargs="+", help="vLLM server URLs")
    parser.add_argument(
        "--workers", type=int, default=30, help="Parallel collection workers"
    )
    args = parser.parse_args()

    if args.stats:
        print_stats()
    elif args.solve:
        solve_interactive()
    elif args.collect_only:
        run_collect(sources=args.sources, workers=args.workers)
    elif args.synth_only:
        run_synthesize(backend=args.backend, vllm_urls=args.vllm_urls)
    else:
        run_collect(sources=args.sources, workers=args.workers)
        run_synthesize(backend=args.backend, vllm_urls=args.vllm_urls)


if __name__ == "__main__":
    main()
