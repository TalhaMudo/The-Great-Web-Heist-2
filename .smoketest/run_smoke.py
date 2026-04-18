"""End-to-end smoke test for the multi-agent crawler.

Crawls the local fixture site at http://127.0.0.1:8765, runs lexical search
while the crawler is still active, and then verifies triples and
resumability behaviour.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force a clean DB for the smoke test.
import backend.storage as storage  # noqa: E402

storage.DB_PATH = ROOT / ".smoketest" / "smoke.db"
if storage.DB_PATH.exists():
    storage.DB_PATH.unlink()

from backend.crawler import crawler_service  # noqa: E402
from backend.indexer import index_service  # noqa: E402
from backend.models import CrawlJob, JobStatus  # noqa: E402


async def main() -> int:
    storage.init_db()

    job = CrawlJob(
        id=str(uuid.uuid4()),
        origin_url="http://127.0.0.1:8765/index.html",
        max_depth=2,
        max_urls_to_visit=20,
        created_at=datetime.utcnow(),
        status=JobStatus.PENDING,
    )

    # Slow rate so we can observe search-while-indexing on a tiny fixture.
    await crawler_service.start_job(job, rate_limit_per_sec=1.0)

    # Search while indexing is still active.
    saw_results_during_crawl = False
    deadline = asyncio.get_running_loop().time() + 30.0
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.2)
        ctx = crawler_service.get_job_context(job.id)
        if ctx is None:
            break
        results = index_service.search("heist", limit=10)
        if results and not saw_results_during_crawl and ctx.job.status == JobStatus.RUNNING:
            saw_results_during_crawl = True
            print(
                f"  live search saw {len(results)} result(s) while crawler "
                f"status={ctx.job.status.value} processed={ctx.job.stats.processed_urls}"
            )
        if ctx.job.status == JobStatus.COMPLETED:
            break

    final_ctx = crawler_service.get_job_context(job.id)
    assert final_ctx is not None, "job context disappeared"
    assert final_ctx.job.status == JobStatus.COMPLETED, (
        f"job did not complete: {final_ctx.job.status} err={final_ctx.job.error_message}"
    )
    assert final_ctx.job.stats.processed_urls >= 4, (
        f"expected >=4 pages processed, got {final_ctx.job.stats.processed_urls}"
    )
    assert final_ctx.job.stats.duplicate_urls >= 1, (
        f"expected duplicate detection (Page C is reachable from A and B), got {final_ctx.job.stats.duplicate_urls}"
    )

    print(
        f"crawler finished: processed={final_ctx.job.stats.processed_urls} "
        f"discovered={final_ctx.job.stats.discovered_urls} "
        f"duplicates={final_ctx.job.stats.duplicate_urls} "
        f"failed={final_ctx.job.stats.failed_urls} "
        f"backpressure={final_ctx.job.stats.backpressure_state}"
    )

    # Search should return triples.
    results = index_service.search("queue", limit=10)
    triples = [(r[0], r[1], r[2]) for r in results]
    print("search('queue') triples:")
    print(json.dumps([{"relevant_url": u, "origin_url": o, "depth": d} for u, o, d in triples], indent=2))
    assert any("b.html" in u for u, _, _ in triples), "expected page B in results"

    results2 = index_service.search("back pressure", limit=10)
    assert results2, "expected at least one result for 'back pressure'"
    print(f"search('back pressure') -> {len(results2)} result(s); top={results2[0][0]}")

    # The triples must contain the origin_url and depth, with depth in [0, 2].
    for url, origin_url, depth, _score, _title in results:
        assert origin_url == job.origin_url, f"origin_url mismatch for {url}: {origin_url}"
        assert 0 <= depth <= job.max_depth, f"depth out of range for {url}: {depth}"
    assert saw_results_during_crawl, "search did not return any results during the active crawl"

    # Verify resumability path: pause + resume cycle on a brand-new job.
    job2 = CrawlJob(
        id=str(uuid.uuid4()),
        origin_url="http://127.0.0.1:8765/index.html",
        max_depth=2,
        max_urls_to_visit=20,
        created_at=datetime.utcnow(),
        status=JobStatus.PENDING,
    )
    await crawler_service.start_job(job2, rate_limit_per_sec=1.0)
    await asyncio.sleep(0.05)
    paused = await crawler_service.pause_job(job2.id)
    assert paused is not None and paused.status == JobStatus.PAUSED, "pause failed"
    ctx2 = crawler_service.get_job_context(job2.id)
    visited_after_pause = len(ctx2.visited)
    queue_after_pause = ctx2.queue.qsize()
    print(f"after pause: visited={visited_after_pause} queue={queue_after_pause}")
    # Verify state was persisted to SQLite while paused, so a real restart
    # would also see this state.
    persisted_visited, persisted_frontier = storage.load_job_state(job2.id)
    print(f"persisted: visited={len(persisted_visited)} frontier={len(persisted_frontier)}")
    assert persisted_visited == ctx2.visited, "persisted visited disagrees with in-memory"

    resumed = await crawler_service.resume_job(job2.id)
    assert resumed is not None and resumed.status == JobStatus.RUNNING, "resume failed"
    deadline = asyncio.get_running_loop().time() + 20.0
    while asyncio.get_running_loop().time() < deadline:
        ctx = crawler_service.get_job_context(job2.id)
        if ctx and ctx.job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            break
        await asyncio.sleep(0.2)
    final2 = crawler_service.get_job_context(job2.id)
    assert final2, "missing final ctx"
    assert final2.job.status == JobStatus.COMPLETED, (
        f"second job did not complete: status={final2.job.status} err={final2.job.error_message}"
    )
    print(
        f"resumed job finished: processed={final2.job.stats.processed_urls} "
        f"visited={len(final2.visited)}"
    )

    print("\nALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
