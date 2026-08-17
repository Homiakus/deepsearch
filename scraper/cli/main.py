import sys
import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper.config import settings, ExecutionMode
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.acquisition.engine import AdaptiveAcquisitionEngine
from scraper.extraction.engine import ExtractionEngine
from scraper.search.search_engine import SearchEngine
from scraper.application.models import ResearchRequest, RunLifecycleState, FeatureAvailabilityState
from scraper.application.research_service import research_service

app = typer.Typer(
    name="scraper",
    help="Adaptive Web Scraping & Retrieval Platform (§100 UX Principle: simple commands, auto strategy selection)",
    add_completion=False
)
console = Console(legacy_windows=False)



@app.command()
def crawl(
    url: str = typer.Argument(..., help="Target URL to crawl"),
    depth: int = typer.Option(5, "--depth", "-d", help="Maximum crawl depth"),
    max_pages: int = typer.Option(100, "--max-pages", "-m", help="Maximum pages to process"),
    mode: str = typer.Option("balanced", "--mode", help="Execution mode: fast|balanced|complete|research|archive")
):
    """Crawl a URL or website using adaptive strategy selection (§56)."""
    console.print(Panel(f"[bold green]Starting Adaptive Crawl[/bold green]\nTarget: {url}\nDepth: {depth}\nMax Pages: {max_pages}\nMode: {mode}", title="DeepSearch Scraper"))
    c_url = canonicalize_url(url)
    engine = AdaptiveAcquisitionEngine()

    async def _run():
        artifact = await engine.acquire_page(url, c_url, mode=ExecutionMode(mode))
        console.print(f"[bold cyan]Acquired URL:[/bold cyan] {artifact.url}")
        console.print(f"[bold cyan]Strategy Used:[/bold cyan] {artifact.strategy_used}")
        console.print(f"[bold cyan]Status Code:[/bold cyan] {artifact.status_code}")
        console.print(f"[bold cyan]Static Score:[/bold cyan] {artifact.page_intelligence.static_score * 100:.1f}%")
        console.print(f"[bold cyan]JS Dependency Score:[/bold cyan] {artifact.page_intelligence.js_dependency_score * 100:.1f}%")

    asyncio.run(_run())


@app.command()
def inspect(url: str = typer.Argument(..., help="URL to inspect (§57)")):
    """Inspect Mode (§57): Analyzes a URL and prints diagnostic page metrics and recommended strategy."""
    c_url = canonicalize_url(url)
    engine = AdaptiveAcquisitionEngine()

    async def _run():
        artifact = await engine.acquire_page(url, c_url, mode=ExecutionMode.BALANCED)
        pi = artifact.page_intelligence

        table = Table(title=f"Inspect Report for {url}")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        rec_strategy = "HTTP"
        if pi.js_dependency_score >= settings.adaptive.browser_threshold:
            rec_strategy = "PLAYWRIGHT BROWSER"
        if pi.api_score >= 0.7:
            rec_strategy = "DIRECT API"

        table.add_row("HTTP Status", str(artifact.status_code))
        table.add_row("Content Type", artifact.content_type)
        table.add_row("Static Content", f"{pi.static_score * 100:.1f}%")
        table.add_row("JS Dependency", f"{pi.js_dependency_score * 100:.1f}%")
        table.add_row("Detected APIs", str(len(pi.detected_apis)))
        table.add_row("Tables Count", str(pi.tables_count))
        table.add_row("Canvas Detected", "Yes" if pi.has_canvas else "No")
        table.add_row("Visual Score", f"{pi.visual_score * 100:.1f}%")
        table.add_row("Recommended Strategy", f"[bold green]{rec_strategy}[/bold green]")
        table.add_row("Estimated Cost", "LOW" if rec_strategy == "HTTP" else "HIGH")

        console.print(table)

    asyncio.run(_run())


@app.command()
def extract(
    url: str = typer.Argument(..., help="Target URL"),
    schema: Optional[str] = typer.Option(None, "--schema", "-s", help="JSON schema file path")
):
    """Extract content and structured data from URL (§56)."""
    c_url = canonicalize_url(url)
    engine = AdaptiveAcquisitionEngine()

    async def _run():
        artifact = await engine.acquire_page(url, c_url, mode=ExecutionMode.BALANCED)
        result = ExtractionEngine.extract_from_html(url, artifact.text_content)
        console.print(Panel(result.clean_markdown[:1000], title="Extract Result (Clean Markdown)"))

    asyncio.run(_run())


@app.command()
def search(query: str = typer.Argument(..., help="Search query string")):
    """Perform hybrid text and visual multivector search (§56, DS-A03)."""
    se = SearchEngine()
    state = se.get_feature_state()
    results = se.search_hybrid(query)

    if state != FeatureAvailabilityState.READY or not results:
        console.print(f"[yellow]Search status: {state.value}. No documents indexed matching '{query}'.[/yellow]")
        return

    table = Table(title=f"Search Results for '{query}'")
    table.add_column("Title", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("URL", style="magenta")

    for r in results:
        table.add_row(r.title, f"{r.score:.2f}", r.retrieval_type, r.url)

    console.print(table)


@app.command()
def research(
    query: str = typer.Option(..., "--query", "-q", help="Search query or topic to research"),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Subject domain or area filter"),
    sources: Optional[str] = typer.Option(None, "--sources", "-s", help="Comma-separated preferred source URLs"),
    depth: int = typer.Option(3, "--depth", help="Maximum search/crawl depth"),
    max_pages: int = typer.Option(50, "--max-pages", "-m", help="Maximum pages limit"),
    mode: str = typer.Option("balanced", "--mode", help="Execution mode: fast|balanced|complete|research"),
    min_media: int = typer.Option(5, "--min-media", help="Minimum topic media images to archive"),
    max_media: int = typer.Option(25, "--max-media", help="Maximum topic media images to archive"),
    output: Optional[str] = typer.Option("deepsearch_results.zip", "--output", "-o", help="Output ZIP file path")
):
    """DeepSearch Research Pipeline via ResearchApplicationService (DS-A02)."""
    pref_sources = [s.strip() for s in sources.split(",")] if sources else []

    console.print(Panel(
        f"[bold green]Starting DeepSearch Application Service[/bold green]\n"
        f"Query: {query}\n"
        f"Domain: {domain or 'Global'}\n"
        f"Preferred Sources: {pref_sources or 'Auto-discovered'}\n"
        f"Depth: {depth}\n"
        f"Max Pages: {max_pages}\n"
        f"Media Target: {min_media} to {max_media} images\n"
        f"Mode: {mode}\n"
        f"Output Archive: {output}",
        title="DeepSearch Research Engine"
    ))

    req = ResearchRequest(
        query=query,
        domain=domain,
        preferred_sources=pref_sources,
        depth=depth,
        max_pages=max_pages,
        mode=ExecutionMode(mode),
        min_media_count=min_media,
        max_media_count=max_media,
        enable_media_archiving=True,
        output_archive_path=output
    )

    async def _run():
        handle = await research_service.start(req)
        console.print(f"[bold blue]Run ID:[/bold blue] {handle.run_id}")

        # Poll status until completed
        while True:
            await asyncio.sleep(0.5)
            st = await research_service.status(handle.run_id)
            if st.status in (RunLifecycleState.COMPLETED, RunLifecycleState.INSUFFICIENT_EVIDENCE, RunLifecycleState.FAILED, RunLifecycleState.CANCELLED):
                break

        res = await research_service.result(handle.run_id)
        if res and res.status in (RunLifecycleState.COMPLETED, RunLifecycleState.INSUFFICIENT_EVIDENCE):
            total_media = res.manifest.get("summary", {}).get("total_media_files", 0)
            console.print(f"[bold cyan]Total Pages Processed:[/bold cyan] {res.total_pages_processed}")
            console.print(f"[bold cyan]Total RAG Chunks Generated:[/bold cyan] {res.total_rag_chunks}")
            console.print(f"[bold cyan]Total Media Images Archived:[/bold cyan] {total_media}")
            if res.status == RunLifecycleState.COMPLETED:
                console.print(f"[bold green]Archive Generated Successfully at:[/bold green] {res.archive_path or res.dir_path}")
            else:
                console.print(f"[bold yellow]Archive Generated with Insufficient Evidence:[/bold yellow] {res.archive_path or res.dir_path}")
        else:
            st = await research_service.status(handle.run_id)
            console.print(f"[bold red]Research {st.status.value}:[/bold red] {st.error_message}")

    asyncio.run(_run())


@app.command()
def mcp():
    """Start the DeepSearch Model Context Protocol (MCP) server over stdio (§100)."""
    from scraper.mcp.server import run_mcp_server
    run_mcp_server()


@app.command()
def auth_browser(
    url: str = typer.Option("https://annas-archive.cc", "--url", "-u", help="Initial portal URL to open"),
    profile_dir: str = typer.Option(".browser_profile", "--profile", "-p", help="Path to browser user profile directory")
):
    """Launch interactive Playwright browser for user authentication, captcha solving, and session cookie persistence."""
    from scraper.acquisition.authorized_browser import AuthorizedBrowserManager

    console.print(Panel(
        f"[bold green]Starting Authorized Playwright Browser[/bold green]\n"
        f"Target URL: {url}\n"
        f"Profile Dir: {profile_dir}\n\n"
        f"[yellow]Perform any log-in, captcha resolution, or download. Session state will be persisted.[/yellow]",
        title="DeepSearch Browser Auth"
    ))

    mgr = AuthorizedBrowserManager(user_data_dir=profile_dir)
    asyncio.run(mgr.launch_interactive_session(target_url=url))


@app.command()
def download_file(
    url: str = typer.Argument(..., help="Direct download URL or page URL"),
    output_dir: str = typer.Option("laser_research_dataset/pdfs", "--output", "-o", help="Target output folder"),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="CSS selector of download button to click"),
    headed: bool = typer.Option(False, "--headed", help="Run browser in visible headed mode")
):
    """Download file using authorized Playwright browser session."""
    from scraper.acquisition.authorized_browser import AuthorizedBrowserManager

    mgr = AuthorizedBrowserManager()

    async def _run():
        res = await mgr.download_file(url=url, output_dir=output_dir, click_selector=selector, headless=not headed)
        if res.success:
            console.print(f"[bold green]Successfully Downloaded:[/bold green] {res.filename} ({res.file_size_bytes} bytes)")
            console.print(f"[bold cyan]Saved Path:[/bold cyan] {res.saved_path}")
        else:
            console.print(f"[bold red]Download Failed:[/bold red] {res.error_message}")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
