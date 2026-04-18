"""Optional command-line interface for The Great Web Heist 2.

The CLI is a thin convenience wrapper around the same in-process services that
the FastAPI app uses, so behavior (back pressure, persistence, dedupe, etc.)
matches the dashboard exactly.

Examples:
    python -m backend.cli index https://example.com 2 --max-urls 200
    python -m backend.cli search "search engine"
    python -m backend.cli status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime

from .crawler import crawler_service
from .indexer import index_service
from .models import CrawlJob, JobStatus
from .storage import init_db, load_jobs, load_pages


def _bootstrap() -> None:
    init_db()
    for url, origin_url, depth, title, body_snippet in load_pages():
        index_service.add_snapshot_page(
            url=url,
            origin_url=origin_url,
            depth=depth,
            title=title,
            body_snippet=body_snippet,
        )
    for job in load_jobs():
        crawler_service.register_job(job)


async def _run_index(origin: str, k: int, max_urls: int | None, rate: float) -> None:
    job = CrawlJob(
        id=str(uuid.uuid4()),
        origin_url=origin,
        max_depth=k,
        max_urls_to_visit=max_urls,
        created_at=datetime.utcnow(),
        status=JobStatus.PENDING,
    )
    await crawler_service.start_job(job, rate_limit_per_sec=rate)
    print(f"Started crawl job {job.id} (origin={origin}, k={k}, rate={rate} req/s)")
    print("Workers running in the background; press Ctrl+C to exit.")
    while True:
        await asyncio.sleep(2)
        ctx = crawler_service.get_job_context(job.id)
        if ctx is None:
            break
        s = ctx.job.stats
        print(
            f"  status={ctx.job.status.value} processed={s.processed_urls} "
            f"queued={s.queued_urls}/{s.queue_max} discovered={s.discovered_urls} "
            f"failed={s.failed_urls} backpressure={s.backpressure_state}"
        )
        if ctx.job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            break


def _cmd_search(query: str, limit: int) -> None:
    raw = index_service.search(query, limit=limit)
    if not raw:
        print("No results.")
        return
    payload = [
        {"relevant_url": url, "origin_url": origin_url, "depth": depth}
        for url, origin_url, depth, _score, _title in raw
    ]
    print(json.dumps(payload, indent=2))


def _cmd_status() -> None:
    jobs = crawler_service.all_jobs()
    if not jobs:
        print("No jobs registered.")
        return
    for job in jobs.values():
        s = job.stats
        print(
            f"job={job.id[:8]}… origin={job.origin_url} k={job.max_depth} "
            f"status={job.status.value} processed={s.processed_urls} queued={s.queued_urls}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The Great Web Heist 2 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="Start a crawl job")
    p_index.add_argument("origin", help="Seed URL")
    p_index.add_argument("k", type=int, help="Maximum crawl depth")
    p_index.add_argument("--max-urls", type=int, default=None, help="Max URLs to visit")
    p_index.add_argument("--rate", type=float, default=1.0, help="Per-job request rate (req/s)")

    p_search = sub.add_parser("search", help="Search the in-memory index")
    p_search.add_argument("query", help="Free-text query")
    p_search.add_argument("--limit", type=int, default=20)

    sub.add_parser("status", help="Print current job status")

    args = parser.parse_args(argv)

    _bootstrap()

    if args.cmd == "index":
        try:
            asyncio.run(_run_index(args.origin, args.k, args.max_urls, args.rate))
        except KeyboardInterrupt:
            print("\nInterrupted; current state has been checkpointed to crawler.db.")
        return 0
    if args.cmd == "search":
        _cmd_search(args.query, args.limit)
        return 0
    if args.cmd == "status":
        _cmd_status()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
