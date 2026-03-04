"""
github_poc_crawler.py - GitHub CVE PoC exploit crawler stub.

FF-8 FIX: This stub replaces a missing file that was imported in pipeline.py:
  from discovery.github_poc_crawler import GitHubPoCCrawler

Without this file, running pipeline.py raised ModuleNotFoundError immediately,
making the entire data collection pipeline non-functional for the "cve_poc" source.

TODO: Implement GitHubPoCCrawler to collect:
  - CVE PoC exploits from https://github.com/trickest/cve
  - ExploitDB entries via GitHub mirror
  - NVD CVE data paired with public PoC repositories
  - Nuclei template repository for web vulnerability patterns
"""

from loguru import logger
from pathlib import Path


class GitHubPoCCrawler:
    """
    Crawler for GitHub CVE Proof-of-Concept exploit repositories.

    Currently a stub — raises NotImplementedError to make missing functionality
    explicit rather than silently producing no data.

    TODO: Implement crawling of:
      - https://github.com/trickest/cve (comprehensive CVE PoC collection)
      - https://github.com/offensive-security/exploitdb
      - GitHub code search for CVE-* pattern repositories
      - Nuclei templates (https://github.com/projectdiscovery/nuclei-templates)
    """

    def __init__(self, output_dir: Path, limit: int = 10000, workers: int = 10):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.limit = limit
        self.workers = workers
        logger.warning(
            "GitHubPoCCrawler is a stub. "
            "Implement CVE PoC collection to use the 'cve_poc' data source."
        )

    def crawl(self) -> int:
        """
        Crawl GitHub CVE PoC repositories.

        FF-29 FIX: The previous stub raised NotImplementedError, which crashed
        pipeline.py even though the stub's purpose was to prevent ModuleNotFoundError.
        Now returns 0 and logs a warning so the pipeline can continue with other sources.

        TODO: Implement GitHub API search for CVE PoC repositories,
        trickest/cve archive downloading, and ExploitDB mirroring.
        """
        logger.warning(
            "GitHubPoCCrawler.crawl() is not yet implemented — "
            "returning 0. Implement CVE PoC collection to collect this data."
        )
        return 0
