"""
defcon_crawler.py - DEFCON/HITCON challenge data crawler stub.

FF-8 FIX: This stub replaces a missing file that was imported in pipeline.py:
  from discovery.defcon_crawler import DefconCrawler

Without this file, running pipeline.py raised ModuleNotFoundError immediately,
making the entire data collection pipeline non-functional for the "defcon" source.

TODO: Implement DefconCrawler to collect:
  - DEFCON CTF challenge archives (https://github.com/o-o-overflow)
  - HITCON CTF writeups and challenge files
  - Quals and Finals challenge sets with categories and point values
"""

from loguru import logger
from pathlib import Path


class DefconCrawler:
    """
    Crawler for DEFCON and HITCON CTF challenge archives.

    Currently a stub — raises NotImplementedError to make missing functionality
    explicit rather than silently producing no data.

    TODO: Implement crawling of:
      - https://github.com/o-o-overflow (DEFCON CTF archives)
      - https://ctftime.org/event/list/?year=XXXX (DEFCON events)
      - HITCON challenge repositories
    """

    def __init__(self, output_dir: Path, workers: int = 10):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workers = workers
        logger.warning(
            "DefconCrawler is a stub. "
            "Implement DEFCON/HITCON challenge collection to use the 'defcon' data source."
        )

    def crawl_all(self) -> int:
        """
        Crawl all DEFCON/HITCON challenge data.

        FF-28 FIX: The previous stub raised NotImplementedError, which crashed
        pipeline.py even though the stub's purpose was to prevent ModuleNotFoundError.
        Now returns 0 and logs a warning so the pipeline can continue with other sources.

        TODO: Implement GitHub archive crawling of o-o-overflow repos and HITCON data.
        """
        logger.warning(
            "DefconCrawler.crawl_all() is not yet implemented — "
            "returning 0. Implement DEFCON/HITCON challenge crawling to collect this data."
        )
        return 0
