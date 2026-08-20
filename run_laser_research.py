"""Script to execute DeepSearch Research on Laser Cutting Industrial Parameters."""

import asyncio
import os
import logging

from scraper.config import ExecutionMode
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.extraction.engine import ExtractionEngine
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.storage.archive_exporter import ArchiveExporter, SearchRunMetadata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deepsearch_laser_research")

# List of rich scientific & industry technical papers/guides on laser cutting parameters
TARGET_URLS = [
    "https://en.wikipedia.org/wiki/Laser_cutting",
    "https://ru.wikipedia.org/wiki/%D0%9B%D0%B0%D0%B7%D0%B5%D1%80%D0%BD%D0%B0%D1%8F_%D1%80%D0%B5%D0%B7%D0%BA%D0%B0",
    "https://export.arxiv.org/abs/1406.4924",
    "https://export.arxiv.org/abs/1303.5233",
    "https://www.mdpi.com/2075-4701/10/11/1449",  # Fiber Laser Cutting Parameter Optimization
    "https://www.mdpi.com/2075-4701/11/7/1035",  # Optimization of Assist Gas and Focal Position
    "https://www.sciencedirect.com/topics/engineering/laser-cutting-parameter",
    "https://www.sciencedirect.com/topics/materials-science/laser-cutting",
    "https://www.researchgate.net/publication/325791244_Effect_of_laser_cutting_parameters_on_surface_roughness_and_kerf_width",
    "https://www.trumpf.com/en_US/solutions/applications/laser-cutting/",
    "https://www.ipgphotonics.com/en/applications/industrial-laser-applications/cutting",
]


async def run_research():
    engine = AdaptiveAcquisitionEngine()
    acquired_results = []

    logger.info(f"Starting research on {len(TARGET_URLS)} target sources...")

    for url in TARGET_URLS:
        c_url = canonicalize_url(url)
        try:
            logger.info(f"Acquiring: {url}")
            artifact = await engine.acquire_page(
                url, c_url, mode=ExecutionMode.BALANCED
            )
            extraction = ExtractionEngine.extract_from_html(
                artifact.url, artifact.text_content
            )

            acquired_results.append((artifact, extraction))
            logger.info(
                f"Successfully processed {url} (Markdown len: {len(extraction.clean_markdown)})"
            )
        except Exception as e:
            logger.warning(f"Failed to acquire {url}: {e}")

    metadata = SearchRunMetadata(
        query="особенности лазерной резки в промышленности настройки лазеров",
        domain="Engineering / Laser Physics",
        preferred_sources=TARGET_URLS,
        depth=2,
        max_pages=len(acquired_results),
        mode="balanced",
    )

    exporter = ArchiveExporter(metadata=metadata)
    out_dir = os.path.abspath("laser_research_dataset")
    built_dir = exporter.build_archive_structure(acquired_results, output_dir=out_dir)
    zip_path = exporter.pack_zip_archive(built_dir, "laser_cutting_research.zip")

    logger.info(
        f"Archive generated at {zip_path} with {len(acquired_results)} processed sources."
    )


if __name__ == "__main__":
    asyncio.run(run_research())
