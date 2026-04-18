# Production Deployment Recommendation

To take this single-machine prototype into production, the first step is to
split the monolith along its natural seams. The crawler should run as a
horizontally scalable worker pool that pulls jobs from a durable broker
(Kafka, RabbitMQ, or a managed cloud queue) instead of from an in-process
`asyncio.Queue`, and the back pressure mechanism should move from a process
local counter to a broker-enforced concurrency cap plus per-domain token
buckets so we can honor `robots.txt`, per-domain crawl budgets, and a global
"kill switch" without coordinating Python objects across machines. Page
storage should move from SQLite to a managed transactional store
(PostgreSQL or DynamoDB) for the page metadata and crawl-state tables, and a
dedicated object store (S3) for raw HTML snapshots; the lexical inverted
index should move into a real search engine (OpenSearch / Elasticsearch with
BM25, or a managed equivalent) and the semantic vectors should move into a
purpose-built vector store (pgvector, Pinecone, Weaviate, etc.). The
`search` API can then become a stateless HTTP service that fans queries out
to both engines and merges the results, so it scales independently from the
crawl fleet and can serve queries even while indexing is active.

Operationally the system needs the controls a public-internet crawler must
have: `robots.txt` parsing and obedience, per-domain rate limiting and crawl
budgets, polite-`User-Agent` identification with contact info, retry/backoff
with circuit breakers, a kill switch for misbehaving jobs, and authentication
+ authorization on all admin endpoints. We should run the services in
containers under Kubernetes (or an equivalent orchestrator) with structured
logs, metrics (queue depth, fetch latency, error rate, per-domain QPS), and
distributed traces shipped to Prometheus/Grafana + OpenTelemetry. The CI
pipeline should run linting, type checks, unit tests for the URL normalizer
and tokenizer, and integration tests for end-to-end crawl/search behavior on
a synthetic site, blocking deploys on regressions. With these in place, the
multi-agent development workflow we used here remains valuable in
production: the same agent roles can be reused to spec, review, and update
each independent service over time, with a human acting as the system
designer and final reviewer for every change.
