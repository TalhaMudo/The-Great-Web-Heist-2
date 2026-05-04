import React, { useEffect, useRef, useState } from "react";

type JobSummary = {
  id: string;
  origin_url: string;
  max_depth: number;
  max_urls_to_visit?: number | null;
  created_at: string;
  updated_at: string;
  status: string;
  processed_urls: number;
  queued_urls: number;
  backpressure_state: string;
  rate_limit_per_sec: number;
};

type JobEvent = {
  created_at: string;
  level: string;
  message: string;
  url?: string | null;
  depth?: number | null;
};

type JobDetail = {
  id: string;
  origin_url: string;
  max_depth: number;
  max_urls_to_visit?: number | null;
  created_at: string;
  updated_at: string;
  status: string;
  error_message?: string | null;
  rate_limit_per_sec: number;
  stats: {
    processed_urls: number;
    discovered_urls: number;
    duplicate_urls: number;
    failed_urls: number;
    queued_urls: number;
    queue_max: number;
    active_workers: number;
    backpressure_state: string;
  };
  visited_count: number;
  frontier_count: number;
  frontier_preview: Array<{
    url: string;
    depth: number;
    origin_url: string;
  }>;
  recent_events: JobEvent[];
};

type Metrics = {
  processed_urls: number;
  discovered_urls: number;
  duplicate_urls: number;
  failed_urls: number;
  queued_urls: number;
  queue_max: number;
  backpressure_state: string;
  active_workers: number;
  jobs_summary: JobSummary[];
};

type SearchTriple = {
  relevant_url: string;
  origin_url: string;
  depth: number;
};

type SearchResultDetail = SearchTriple & {
  score?: number | null;
  title?: string | null;
};

type SearchResponse = {
  triples: SearchTriple[];
  results: SearchResultDetail[];
};

type EmbeddingStatus = {
  updated_at: string;
  status: string;
  model_name: string;
  rate_limit_per_sec: number;
  max_pages?: number | null;
  total_pages: number;
  embedded_pages: number;
  failed_pages: number;
  remaining_pages: number;
  progress_percent: number;
  error_message?: string | null;
};

type RagChunk = {
  id: string;
  document: string;
  entity?: string | null;
  search_type?: string | null;
  distance?: number | null;
};

type RagToolCall = {
  name: string;
  arguments: Record<string, string>;
};

type RagChatMessage = {
  role: string;
  content: string;
};

type RagChatResponse = {
  session_id: string;
  answer: string;
  tool_calls: RagToolCall[];
  chunks_retrieved: RagChunk[];
  history: RagChatMessage[];
};

type RagEntityStatus = {
  name: string;
  category: string;
  chunks: number;
  ingested: boolean;
};

type RagSessionInfo = {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

type RagStatus = {
  people_chunks: number;
  places_chunks: number;
  total_chunks: number;
  people_count: number;
  places_count: number;
  entities: RagEntityStatus[];
};

export const App: React.FC = () => {
  const [viewMode, setViewMode] = useState<"crawler" | "search" | "embeddings" | "rag">("crawler");
  const [origin, setOrigin] = useState("");
  const [depthInput, setDepthInput] = useState("2");
  const [maxUrlsToVisit, setMaxUrlsToVisit] = useState("500");
  const [rateLimitInput, setRateLimitInput] = useState("1.0");
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [query, setQuery] = useState("");
  const [classicResults, setClassicResults] = useState<SearchResultDetail[]>([]);
  const [classicTriples, setClassicTriples] = useState<SearchTriple[]>([]);
  const [semanticResults, setSemanticResults] = useState<SearchResultDetail[]>([]);
  const [isIndexing, setIsIndexing] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isMutatingJob, setIsMutatingJob] = useState(false);
  const [globalQueueLimitInput, setGlobalQueueLimitInput] = useState("1000");
  const [isEditingGlobalQueueLimit, setIsEditingGlobalQueueLimit] = useState(false);
  const [jobRateInputs, setJobRateInputs] = useState<Record<string, string>>({});
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatus | null>(null);
  const [embeddingRateLimit, setEmbeddingRateLimit] = useState("1.0");
  const [embeddingMaxPages, setEmbeddingMaxPages] = useState("500");
  const [isMutatingEmbeddingJob, setIsMutatingEmbeddingJob] = useState(false);

  // RAG Chat state
  const [ragSessionId, setRagSessionId] = useState<string | null>(null);
  const [ragInput, setRagInput] = useState("");
  const [ragHistory, setRagHistory] = useState<RagChatMessage[]>([]);
  const [ragChunks, setRagChunks] = useState<RagChunk[]>([]);
  const [ragToolCalls, setRagToolCalls] = useState<RagToolCall[]>([]);
  const [ragLoading, setRagLoading] = useState(false);
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null);
  const [ragIngesting, setRagIngesting] = useState(false);
  const [ragChunksExpanded, setRagChunksExpanded] = useState<Record<number, boolean>>({});
  const [ragSessions, setRagSessions] = useState<RagSessionInfo[]>([]);
  const [ragEntitiesOpen, setRagEntitiesOpen] = useState(false);
  const ragChatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchMetrics = () => {
      fetch("/metrics")
        .then((res) => res.json())
        .then((data: Metrics) => {
          setMetrics(data);
          if (!isEditingGlobalQueueLimit) {
            setGlobalQueueLimitInput(String(data.queue_max));
          }
          setJobRateInputs((prev) => {
            const next = { ...prev };
            for (const job of data.jobs_summary) {
              if (!next[job.id]) {
                next[job.id] = String(job.rate_limit_per_sec);
              }
            }
            return next;
          });
          if (!selectedJobId && data.jobs_summary.length > 0) {
            setSelectedJobId(data.jobs_summary[0].id);
          }
        })
        .catch(() => {});
    };
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 2000);
    return () => clearInterval(interval);
  }, [selectedJobId, isEditingGlobalQueueLimit]);

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJob(null);
      return;
    }
    const fetchJob = () => {
      fetch(`/jobs/${selectedJobId}`)
        .then((res) => res.json())
        .then((data: JobDetail) => setSelectedJob(data))
        .catch(() => {});
    };
    fetchJob();
    const interval = setInterval(fetchJob, 2000);
    return () => clearInterval(interval);
  }, [selectedJobId]);

  useEffect(() => {
    const fetchEmbeddingStatus = () => {
      fetch("/embeddings/status")
        .then((res) => res.json())
        .then((data: EmbeddingStatus) => {
          setEmbeddingStatus((prev) => {
            if (prev === null) {
              setEmbeddingRateLimit(String(data.rate_limit_per_sec));
            }
            return data;
          });
        })
        .catch(() => {});
    };
    fetchEmbeddingStatus();
    const interval = setInterval(fetchEmbeddingStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const startIndex = async () => {
    setError(null);
    try {
      const trimmedDepth = depthInput.trim();
      const parsedDepth = Number(trimmedDepth);
      if (!trimmedDepth || !Number.isInteger(parsedDepth) || parsedDepth < 0 || parsedDepth > 8) {
        throw new Error("Max depth (k) must be an integer between 0 and 8.");
      }

      const trimmedRate = rateLimitInput.trim();
      const parsedRateLimit = Number(trimmedRate);
      if (!trimmedRate || !Number.isFinite(parsedRateLimit) || parsedRateLimit <= 0) {
        throw new Error("Crawler speed (req/s) must be a positive number.");
      }

      const trimmedMaxUrls = maxUrlsToVisit.trim();
      const parsedMaxUrls = trimmedMaxUrls ? Number(trimmedMaxUrls) : null;
      if (
        trimmedMaxUrls &&
        (!Number.isInteger(parsedMaxUrls) || parsedMaxUrls === null || parsedMaxUrls <= 0)
      ) {
        throw new Error("Max URLs to Visit must be a positive integer.");
      }

      setIsIndexing(true);
      const res = await fetch("/index", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin,
          k: parsedDepth,
          max_urls_to_visit: parsedMaxUrls,
          rate_limit_per_sec: parsedRateLimit,
        }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Failed to start indexing");
      }
      const data = await res.json();
      setCurrentJobId(data.job_id);
      setSelectedJobId(data.job_id);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setIsIndexing(false);
    }
  };

  const runSearch = async () => {
    setError(null);
    setIsSearching(true);
    try {
      const [classicRes, semanticRes] = await Promise.all([
        fetch(`/search?query=${encodeURIComponent(query)}`),
        fetch(`/search/semantic?query=${encodeURIComponent(query)}`),
      ]);
      if (!classicRes.ok || !semanticRes.ok) {
        const failing = classicRes.ok ? semanticRes : classicRes;
        const data = await failing.json();
        throw new Error(data.detail ?? "Search failed");
      }
      const classicData: SearchResponse = await classicRes.json();
      const semanticData: SearchResponse = await semanticRes.json();
      setClassicResults(classicData.results ?? []);
      setClassicTriples(classicData.triples ?? []);
      setSemanticResults(semanticData.results ?? []);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setIsSearching(false);
    }
  };

  const mutateJob = async (action: "pause" | "resume") => {
    if (!selectedJobId) return;
    setError(null);
    try {
      setIsMutatingJob(true);
      const res = await fetch(`/jobs/${selectedJobId}/${action}`, { method: "POST" });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? `Failed to ${action} job`);
      }
      const data = await res.json();
      setSelectedJob(data);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setIsMutatingJob(false);
    }
  };

  const startEmbedding = async () => {
    setError(null);
    try {
      setIsMutatingEmbeddingJob(true);
      const res = await fetch("/embeddings/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rate_limit_per_sec: Number(embeddingRateLimit),
          max_pages: embeddingMaxPages ? Number(embeddingMaxPages) : null,
        }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Failed to start embedding engine");
      }
      const status: EmbeddingStatus = await res.json();
      setEmbeddingStatus(status);
      setEmbeddingRateLimit(String(status.rate_limit_per_sec));
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setIsMutatingEmbeddingJob(false);
    }
  };

  const pauseEmbedding = async () => {
    setError(null);
    try {
      setIsMutatingEmbeddingJob(true);
      const res = await fetch("/embeddings/pause", { method: "POST" });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Failed to pause embedding engine");
      }
      const status: EmbeddingStatus = await res.json();
      setEmbeddingStatus(status);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setIsMutatingEmbeddingJob(false);
    }
  };

  const updateEmbeddingRateLimit = async () => {
    setError(null);
    try {
      setIsMutatingEmbeddingJob(true);
      const res = await fetch("/embeddings/rate-limit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rate_limit_per_sec: Number(embeddingRateLimit) }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Failed to update embedding speed");
      }
      const status: EmbeddingStatus = await res.json();
      setEmbeddingStatus(status);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setIsMutatingEmbeddingJob(false);
    }
  };

  const clearAllEmbeddings = async () => {
    const confirmed = window.confirm(
      "Delete all stored embeddings? Semantic search will be empty until you embed again."
    );
    if (!confirmed) return;
    setError(null);
    try {
      setIsMutatingEmbeddingJob(true);
      const res = await fetch("/embeddings/clear", { method: "POST" });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Failed to clear embeddings");
      }
      const status: EmbeddingStatus = await res.json();
      setEmbeddingStatus(status);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setIsMutatingEmbeddingJob(false);
    }
  };

  // RAG status polling
  useEffect(() => {
    if (viewMode !== "rag") return;
    const fetchStatus = () => {
      fetch("/rag/status")
        .then((res) => res.json())
        .then((data: RagStatus) => setRagStatus(data))
        .catch(() => {});
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [viewMode]);

  // RAG session list polling
  useEffect(() => {
    if (viewMode !== "rag") return;
    const fetchSessions = () => {
      fetch("/rag/sessions")
        .then((res) => res.json())
        .then((data: { sessions: RagSessionInfo[] }) => setRagSessions(data.sessions))
        .catch(() => {});
    };
    fetchSessions();
    const interval = setInterval(fetchSessions, 3000);
    return () => clearInterval(interval);
  }, [viewMode]);

  // Auto-scroll chat
  useEffect(() => {
    ragChatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [ragHistory]);

  const sendRagMessage = async () => {
    const msg = ragInput.trim();
    if (!msg || ragLoading) return;
    setRagInput("");
    setRagLoading(true);
    setError(null);
    setRagChunks([]);
    setRagToolCalls([]);
    setRagChunksExpanded({});
    try {
      const res = await fetch("/rag/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, session_id: ragSessionId }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Chat failed");
      }
      const data: RagChatResponse = await res.json();
      setRagSessionId(data.session_id);
      setRagHistory(data.history);
      setRagChunks(data.chunks_retrieved);
      setRagToolCalls(data.tool_calls);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setRagLoading(false);
    }
  };

  const newRagChat = () => {
    setRagSessionId(null);
    setRagHistory([]);
    setRagChunks([]);
    setRagToolCalls([]);
    setRagChunksExpanded({});
  };

  const deleteRagChat = async (sid: string) => {
    await fetch(`/rag/chat/clear?session_id=${sid}`, { method: "POST" }).catch(() => {});
    if (ragSessionId === sid) newRagChat();
    setRagSessions((prev) => prev.filter((s) => s.session_id !== sid));
  };

  const loadRagSession = async (sid: string) => {
    if (sid === ragSessionId) return;
    setRagChunks([]);
    setRagToolCalls([]);
    setRagChunksExpanded({});
    try {
      const res = await fetch(`/rag/sessions/${sid}`);
      if (!res.ok) return;
      const data: { session_id: string; history: RagChatMessage[] } = await res.json();
      setRagSessionId(data.session_id);
      setRagHistory(data.history);
    } catch {
      // ignore
    }
  };

  const runRagIngest = async () => {
    setError(null);
    setRagIngesting(true);
    try {
      const res = await fetch("/rag/ingest", { method: "POST" });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Ingestion failed");
      }
      const data = await res.json();
      alert(`Ingestion complete: ${data.total_ok} entities, ${data.total_chunks} chunks.`);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setRagIngesting(false);
    }
  };

  const searchPanel = (
    <section className="panel">
      <div className="search-header">
        <h2>Search</h2>
        <p className="search-subtitle">
          Returns triples <code>(relevant_url, origin_url, depth)</code> from indexed pages. Search runs against the
          live in-memory index, so newly crawled URLs appear as soon as they are indexed.
        </p>
      </div>
      <label className="field">
        <span>Query</span>
        <input
          className="search-input"
          type="text"
          placeholder="Type a keyword or phrase to search indexed pages"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query) runSearch();
          }}
        />
      </label>
      <div className="search-actions">
        <button onClick={runSearch} disabled={!query || isSearching}>
          {isSearching ? "Searching..." : "Search"}
        </button>
      </div>
      {classicTriples.length > 0 && (
        <div className="triple-block" aria-label="Assignment-required triples">
          {classicTriples
            .slice(0, 25)
            .map((t) => `("${t.relevant_url}", "${t.origin_url}", ${t.depth})`)
            .join("\n")}
        </div>
      )}
      <div className="dual-results-grid">
        <div className="results-panel">
          <h3>Lexical (TF-IDF)</h3>
          <div className="results">
            {classicResults.length === 0 ? (
              <p className="hint">No lexical results yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th style={{ width: "45%" }}>Relevant URL</th>
                    <th style={{ width: "25%" }}>Origin</th>
                    <th style={{ width: "10%" }}>Depth</th>
                    <th style={{ width: "10%" }}>Score</th>
                    <th style={{ width: "10%" }}>Title</th>
                  </tr>
                </thead>
                <tbody>
                  {classicResults.map((r) => (
                    <tr key={`classic-${r.relevant_url}`}>
                      <td className="url-cell">
                        <a className="result-link" href={r.relevant_url} target="_blank" rel="noreferrer">
                          {r.relevant_url}
                        </a>
                      </td>
                      <td className="url-cell">{r.origin_url}</td>
                      <td>{r.depth}</td>
                      <td>{r.score?.toFixed(3)}</td>
                      <td>{r.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
        <div className="results-panel">
          <h3>Semantic (MiniLM)</h3>
          <div className="results">
            {semanticResults.length === 0 ? (
              <p className="hint">No semantic results yet. Run the embedding engine first if needed.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th style={{ width: "45%" }}>Relevant URL</th>
                    <th style={{ width: "25%" }}>Origin</th>
                    <th style={{ width: "10%" }}>Depth</th>
                    <th style={{ width: "10%" }}>Similarity</th>
                    <th style={{ width: "10%" }}>Title</th>
                  </tr>
                </thead>
                <tbody>
                  {semanticResults.map((r) => (
                    <tr key={`semantic-${r.relevant_url}`}>
                      <td className="url-cell">
                        <a className="result-link" href={r.relevant_url} target="_blank" rel="noreferrer">
                          {r.relevant_url}
                        </a>
                      </td>
                      <td className="url-cell">{r.origin_url}</td>
                      <td>{r.depth}</td>
                      <td>{r.score?.toFixed(4)}</td>
                      <td>{r.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </section>
  );

  const embeddingsPanel = (
    <section className="panel">
      <h2>Embeddings Engine</h2>
      <p className="search-subtitle">
        Generate semantic vectors from already crawled pages with controlled speed and a per-run cap.
      </p>
      <div className="embedding-control-grid">
        <label className="field">
          <span>Model</span>
          <input type="text" value="all-MiniLM-L6-v2" readOnly />
        </label>
        <label className="field">
          <span>Embedding speed (pages/s)</span>
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={embeddingRateLimit}
            onChange={(e) => setEmbeddingRateLimit(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Max pages this run</span>
          <input
            type="number"
            min={1}
            value={embeddingMaxPages}
            onChange={(e) => setEmbeddingMaxPages(e.target.value)}
          />
        </label>
      </div>
      <div className="search-actions">
        <button onClick={startEmbedding} disabled={isMutatingEmbeddingJob}>
          {embeddingStatus?.status === "running" ? "Embedding..." : "Start Embedding"}
        </button>
        <button
          className="button-secondary"
          onClick={pauseEmbedding}
          disabled={!embeddingStatus || embeddingStatus.status !== "running" || isMutatingEmbeddingJob}
        >
          Pause
        </button>
        <button className="button-secondary" onClick={updateEmbeddingRateLimit} disabled={isMutatingEmbeddingJob}>
          Update Speed
        </button>
        <button className="button-secondary" onClick={clearAllEmbeddings} disabled={isMutatingEmbeddingJob}>
          Delete All
        </button>
      </div>
      <p className="hint">
        First run loads the MiniLM model into memory (~10s). Progress and counts update afterwards.
      </p>
      <div className="metrics-grid">
        <div className="metric">
          <span className="label">Status</span>
          <span className={`badge badge-${embeddingStatus?.status ?? "idle"}`}>
            {embeddingStatus?.status ?? "idle"}
          </span>
        </div>
        <div className="metric">
          <span className="label">Progress</span>
          <span className="value">
            {embeddingStatus ? `${embeddingStatus.progress_percent.toFixed(1)}% embedded` : "Loading..."}
          </span>
          <div className="progress-track" aria-label="Embedding progress">
            <div
              className="progress-fill"
              style={{ width: `${Math.min(100, Math.max(0, embeddingStatus?.progress_percent ?? 0))}%` }}
            />
          </div>
        </div>
        <div className="metric">
          <span className="label">Embedded pages</span>
          <span className="value">{embeddingStatus?.embedded_pages ?? 0}</span>
        </div>
        <div className="metric">
          <span className="label">Remaining pages</span>
          <span className="value">{embeddingStatus?.remaining_pages ?? 0}</span>
        </div>
        <div className="metric">
          <span className="label">Total crawled pages</span>
          <span className="value">{embeddingStatus?.total_pages ?? 0}</span>
        </div>
        <div className="metric">
          <span className="label">Failed this run</span>
          <span className="value">{embeddingStatus?.failed_pages ?? 0}</span>
        </div>
      </div>
      {embeddingStatus?.error_message && <p className="hint">Engine error: {embeddingStatus.error_message}</p>}
    </section>
  );

  return (
    <div className="app">
      <header className="header">
        <h1>The Great Web Heist</h1>
        <p>Multi-agent crawler and search dashboard</p>
        <p className="subtitle">
          Returns assignment-required triples <code>(relevant_url, origin_url, depth)</code> over a depth-limited,
          back-pressured crawl.
        </p>
        <div className="mode-switch" role="tablist" aria-label="Application mode">
          <button
            className={`mode-btn ${viewMode === "crawler" ? "mode-btn-active" : ""}`}
            onClick={() => setViewMode("crawler")}
            role="tab"
            aria-selected={viewMode === "crawler"}
          >
            Crawler
          </button>
          <button
            className={`mode-btn ${viewMode === "search" ? "mode-btn-active" : ""}`}
            onClick={() => setViewMode("search")}
            role="tab"
            aria-selected={viewMode === "search"}
          >
            Search
          </button>
          <button
            className={`mode-btn ${viewMode === "embeddings" ? "mode-btn-active" : ""}`}
            onClick={() => setViewMode("embeddings")}
            role="tab"
            aria-selected={viewMode === "embeddings"}
          >
            Embeddings
          </button>
          <button
            className={`mode-btn ${viewMode === "rag" ? "mode-btn-active" : ""}`}
            onClick={() => setViewMode("rag")}
            role="tab"
            aria-selected={viewMode === "rag"}
          >
            Chat (RAG)
          </button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className={`layout ${viewMode !== "crawler" ? "layout-search" : ""}`}>
        {viewMode === "crawler" && (
          <div className="sidebar">
            <section className="panel">
              <h2>Index Control</h2>
              <label className="field">
                <span>Origin URL</span>
                <input
                  type="url"
                  placeholder="https://example.com"
                  value={origin}
                  onChange={(e) => setOrigin(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Max depth (k)</span>
                <input
                  type="number"
                  min={0}
                  max={8}
                  value={depthInput}
                  onChange={(e) => setDepthInput(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Max URLs to visit</span>
                <input
                  type="number"
                  min={1}
                  value={maxUrlsToVisit}
                  onChange={(e) => setMaxUrlsToVisit(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Crawler speed (req/s)</span>
                <input
                  type="number"
                  min={0.1}
                  step={0.1}
                  value={rateLimitInput}
                  onChange={(e) => setRateLimitInput(e.target.value)}
                />
              </label>
              <button onClick={startIndex} disabled={!origin || isIndexing}>
                {isIndexing ? "Starting..." : "Start Indexing"}
              </button>
              {currentJobId && <p className="hint">Active job id: {currentJobId}</p>}
            </section>

            <section className="panel">
              <h2>System Dashboard</h2>
              <label className="field">
                <span>Global queue limit (across all jobs)</span>
                <div className="inline-control">
                  <input
                    type="number"
                    min={1}
                    value={globalQueueLimitInput}
                    onChange={(e) => setGlobalQueueLimitInput(e.target.value)}
                    onFocus={() => setIsEditingGlobalQueueLimit(true)}
                    onBlur={() => setIsEditingGlobalQueueLimit(false)}
                  />
                  <button
                    onClick={async () => {
                      setError(null);
                      try {
                        const val = Number(globalQueueLimitInput);
                        const res = await fetch("/settings/queue-limit", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ global_queue_limit: val }),
                        });
                        if (!res.ok) {
                          const data = await res.json();
                          throw new Error(data.detail ?? "Failed to update global queue limit");
                        }
                        const data = await res.json();
                        setMetrics(data);
                      } catch (e: any) {
                        setError(e.message ?? String(e));
                      }
                    }}
                  >
                    Apply
                  </button>
                </div>
              </label>
              {metrics ? (
                <>
                  <div className="metrics-grid">
                    <div className="metric">
                      <span className="label">Processed URLs</span>
                      <span className="value">{metrics.processed_urls}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Discovered URLs</span>
                      <span className="value">{metrics.discovered_urls}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Duplicates skipped</span>
                      <span className="value">{metrics.duplicate_urls}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Failed fetches</span>
                      <span className="value">{metrics.failed_urls}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Queue depth</span>
                      <span className="value">
                        {metrics.queued_urls} / {metrics.queue_max}
                      </span>
                    </div>
                    <div className="metric">
                      <span className="label">Backpressure</span>
                      <span className={`badge badge-${metrics.backpressure_state}`}>
                        {metrics.backpressure_state}
                      </span>
                    </div>
                    <div className="metric">
                      <span className="label">Active workers</span>
                      <span className="value">{metrics.active_workers}</span>
                    </div>
                  </div>
                  <h3>Jobs</h3>
                  {metrics.jobs_summary.length === 0 ? (
                    <p className="hint">No jobs yet.</p>
                  ) : (
                    <div className="jobs-list">
                      {metrics.jobs_summary.map((job) => (
                        <article
                          className={`job-card ${selectedJobId === job.id ? "job-card-selected" : ""}`}
                          key={job.id}
                          onClick={() => setSelectedJobId(job.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              setSelectedJobId(job.id);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                        >
                          <div className="job-card-header">
                            <strong>{job.id.slice(0, 8)}…</strong>
                            <span className={`badge badge-${job.status}`}>{job.status}</span>
                          </div>
                          <div className="job-card-url">{job.origin_url}</div>
                          <div className="job-card-meta">
                            <span>k={job.max_depth}</span>
                            <span>max URLs: {job.max_urls_to_visit ?? "∞"}</span>
                            <span>processed: {job.processed_urls}</span>
                            <span>queue: {job.queued_urls}</span>
                            <span>{new Date(job.updated_at).toLocaleTimeString()}</span>
                          </div>
                          <div className="job-card-controls">
                            <label>req/s</label>
                            <input
                              type="number"
                              min={0.1}
                              step={0.1}
                              value={jobRateInputs[job.id] ?? String(job.rate_limit_per_sec)}
                              onChange={(e) =>
                                setJobRateInputs((prev) => ({
                                  ...prev,
                                  [job.id]: e.target.value,
                                }))
                              }
                              onClick={(e) => e.stopPropagation()}
                            />
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                setError(null);
                                try {
                                  const val = Number(jobRateInputs[job.id] ?? job.rate_limit_per_sec);
                                  const res = await fetch(`/jobs/${job.id}/rate-limit`, {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ rate_limit_per_sec: val }),
                                  });
                                  if (!res.ok) {
                                    const data = await res.json();
                                    throw new Error(data.detail ?? "Failed to update job rate");
                                  }
                                  const data = await res.json();
                                  setJobRateInputs((prev) => ({ ...prev, [job.id]: String(val) }));
                                  if (selectedJobId === job.id) {
                                    setSelectedJob(data);
                                  }
                                } catch (err: any) {
                                  setError(err.message ?? String(err));
                                }
                              }}
                            >
                              Set
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="hint">Waiting for metrics from backend…</p>
              )}
            </section>
          </div>
        )}

        <div className={`main ${viewMode !== "crawler" ? "main-search" : ""}`}>
          {viewMode === "crawler" && (
            <section className="panel panel-job-detail">
              <h2>Job Detail</h2>
              {!selectedJob ? (
                <p className="hint">Select a job to inspect its live state and control it.</p>
              ) : (
                <>
                  <div className="job-detail-header">
                    <div>
                      <div className="hint">Job ID</div>
                      <code>{selectedJob.id}</code>
                    </div>
                    <span className={`badge badge-${selectedJob.status}`}>{selectedJob.status}</span>
                  </div>
                  <div className="job-actions">
                    <button
                      onClick={() => mutateJob("pause")}
                      disabled={selectedJob.status !== "running" || isMutatingJob}
                    >
                      Pause Job
                    </button>
                    <button
                      onClick={() => mutateJob("resume")}
                      disabled={selectedJob.status !== "paused" || isMutatingJob}
                    >
                      Resume Job
                    </button>
                  </div>
                  <div className="job-detail-grid">
                    <div className="metric">
                      <span className="label">Origin</span>
                      <span className="value">{selectedJob.origin_url}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Rate limit</span>
                      <span className="value">{selectedJob.rate_limit_per_sec.toFixed(1)} req/s</span>
                    </div>
                    <div className="metric">
                      <span className="label">Max URLs</span>
                      <span className="value">{selectedJob.max_urls_to_visit ?? "unbounded"}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Visited</span>
                      <span className="value">{selectedJob.visited_count}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Frontier</span>
                      <span className="value">{selectedJob.frontier_count}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Processed</span>
                      <span className="value">{selectedJob.stats.processed_urls}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Backpressure</span>
                      <span className={`badge badge-${selectedJob.stats.backpressure_state}`}>
                        {selectedJob.stats.backpressure_state}
                      </span>
                    </div>
                  </div>
                  <h3>Frontier Preview</h3>
                  {selectedJob.frontier_preview.length === 0 ? (
                    <p className="hint">No queued URLs.</p>
                  ) : (
                    <div className="job-frontier">
                      {selectedJob.frontier_preview.map((item) => (
                        <div className="frontier-row" key={`${item.url}-${item.depth}`}>
                          <span className="frontier-depth">d={item.depth}</span>
                          <span className="frontier-url">{item.url}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <h3>Recent Events</h3>
                  {selectedJob.recent_events.length === 0 ? (
                    <p className="hint">No events yet.</p>
                  ) : (
                    <div className="job-events">
                      {selectedJob.recent_events.map((event, idx) => (
                        <div className="event-row" key={`${event.created_at}-${idx}`}>
                          <span className={`badge badge-${event.level === "error" ? "queue_full" : "normal"}`}>
                            {event.level}
                          </span>
                          <span className="event-message">
                            {event.message}
                            {event.url && <span className="event-url"> {event.url}</span>}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {viewMode === "search" && searchPanel}
          {viewMode === "embeddings" && embeddingsPanel}

          {viewMode === "rag" && (
            <div className="rag-layout">
              {/* Session sidebar */}
              <aside className="rag-sidebar">
                <button className="rag-new-chat-btn" onClick={newRagChat}>+ New Chat</button>
                <div className="rag-session-list">
                  {ragSessions.length === 0 && (
                    <p className="hint" style={{ padding: "0.5rem" }}>No conversations yet.</p>
                  )}
                  {ragSessions.map((s) => (
                    <div
                      key={s.session_id}
                      className={`rag-session-item ${ragSessionId === s.session_id ? "rag-session-active" : ""}`}
                      onClick={() => loadRagSession(s.session_id)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === "Enter") loadRagSession(s.session_id); }}
                    >
                      <div className="rag-session-title">{s.title}</div>
                      <div className="rag-session-meta">
                        <span>{s.message_count} msgs</span>
                        <button
                          className="rag-session-delete"
                          title="Delete"
                          onClick={(e) => { e.stopPropagation(); deleteRagChat(s.session_id); }}
                        >×</button>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Ingestion status */}
                <div className="rag-sidebar-status">
                  <div className="rag-status-info-compact">
                    <span>People: <strong>{ragStatus?.people_chunks ?? 0}</strong></span>
                    <span>Places: <strong>{ragStatus?.places_chunks ?? 0}</strong></span>
                    <span>Ingested: <strong>{ragStatus?.entities.filter((e) => e.ingested).length ?? 0}</strong>/{ragStatus?.entities.length ?? 0}</span>
                  </div>
                  <button className="rag-entities-toggle" onClick={() => setRagEntitiesOpen((v) => !v)}>
                    {ragEntitiesOpen ? "▾ Hide entities" : "▸ Show entities"}
                  </button>
                  {ragEntitiesOpen && ragStatus && (
                    <div className="rag-entities-compact">
                      <div className="rag-entity-group-compact">
                        <div className="rag-entity-group-label">People ({ragStatus.entities.filter((e) => e.category === "person" && e.ingested).length}/{ragStatus.entities.filter((e) => e.category === "person").length})</div>
                        {ragStatus.entities.filter((e) => e.category === "person").map((ent) => (
                          <span key={ent.name} className={`rag-entity-tag-sm ${ent.ingested ? "rag-entity-ingested" : "rag-entity-pending"}`}>
                            {ent.name}{ent.ingested ? ` (${ent.chunks})` : ""}
                          </span>
                        ))}
                      </div>
                      <div className="rag-entity-group-compact">
                        <div className="rag-entity-group-label">Places ({ragStatus.entities.filter((e) => e.category === "place" && e.ingested).length}/{ragStatus.entities.filter((e) => e.category === "place").length})</div>
                        {ragStatus.entities.filter((e) => e.category === "place").map((ent) => (
                          <span key={ent.name} className={`rag-entity-tag-sm ${ent.ingested ? "rag-entity-ingested" : "rag-entity-pending"}`}>
                            {ent.name}{ent.ingested ? ` (${ent.chunks})` : ""}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  <button className="rag-ingest-btn" onClick={runRagIngest} disabled={ragIngesting}>
                    {ragIngesting ? "Ingesting..." : "Ingest Wikipedia"}
                  </button>
                </div>
              </aside>

              {/* Main chat area */}
              <section className="panel rag-panel">
                <div className="rag-chat-container">
                <div className="rag-chat-messages">
                  {ragHistory.length === 0 && (
                    <p className="hint" style={{ textAlign: "center", marginTop: 40 }}>
                      Start a conversation. Try: "Who was Nikola Tesla?" or "What is the Colosseum?"
                    </p>
                  )}
                  {ragHistory.map((msg, idx) => (
                    <div key={idx} className={`rag-msg rag-msg-${msg.role}`}>
                      <div className="rag-msg-role">{msg.role === "user" ? "You" : msg.role === "assistant" ? "Assistant" : msg.role}</div>
                      <div className="rag-msg-content">{msg.content || (msg.role === "assistant" ? "..." : "")}</div>

                      {/* Show retrieved chunks panel after the last assistant message */}
                      {msg.role === "assistant" && idx === ragHistory.length - 1 && ragChunks.length > 0 && (
                        <div className="rag-chunks-box">
                          <button
                            className="rag-chunks-toggle"
                            onClick={() => setRagChunksExpanded((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                          >
                            {ragChunksExpanded[idx] ? "Hide" : "Show"} Retrieved Chunks ({ragChunks.length})
                          </button>
                          {ragChunksExpanded[idx] && (
                            <div className="rag-chunks-list">
                              {ragToolCalls.length > 0 && (
                                <div className="rag-tool-calls">
                                  <strong>Tool calls:</strong>
                                  {ragToolCalls.map((tc, ti) => (
                                    <span key={ti} className="rag-tool-call-badge">
                                      {tc.name}({Object.values(tc.arguments).join(", ")})
                                    </span>
                                  ))}
                                </div>
                              )}
                              <div className="dual-results-grid">
                                <div className="results-panel">
                                  <h4>Semantic Search</h4>
                                  {ragChunks.filter((c) => c.search_type === "semantic").length === 0 ? (
                                    <p className="hint">No semantic results.</p>
                                  ) : (
                                    ragChunks
                                      .filter((c) => c.search_type === "semantic")
                                      .map((c, ci) => (
                                        <div key={ci} className="rag-chunk-card">
                                          <div className="rag-chunk-meta">
                                            <span className="badge badge-running">{c.entity}</span>
                                            {c.distance != null && <span>dist: {c.distance.toFixed(4)}</span>}
                                          </div>
                                          <p className="rag-chunk-text">{c.document}</p>
                                        </div>
                                      ))
                                  )}
                                </div>
                                <div className="results-panel">
                                  <h4>Keyword Search</h4>
                                  {ragChunks.filter((c) => c.search_type === "keyword").length === 0 ? (
                                    <p className="hint">No keyword results.</p>
                                  ) : (
                                    ragChunks
                                      .filter((c) => c.search_type === "keyword")
                                      .map((c, ci) => (
                                        <div key={ci} className="rag-chunk-card">
                                          <div className="rag-chunk-meta">
                                            <span className="badge badge-running">{c.entity}</span>
                                          </div>
                                          <p className="rag-chunk-text">{c.document}</p>
                                        </div>
                                      ))
                                  )}
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                  {ragLoading && (
                    <div className="rag-msg rag-msg-assistant">
                      <div className="rag-msg-role">Assistant</div>
                      <div className="rag-msg-content rag-typing">Thinking...</div>
                    </div>
                  )}
                  <div ref={ragChatEndRef} />
                </div>

                {/* Input area */}
                <div className="rag-input-area">
                  <input
                    className="rag-input"
                    type="text"
                    placeholder="Ask about a person or place..."
                    value={ragInput}
                    onChange={(e) => setRagInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        sendRagMessage();
                      }
                    }}
                    disabled={ragLoading}
                  />
                  <button onClick={sendRagMessage} disabled={!ragInput.trim() || ragLoading}>
                    Send
                  </button>
                  <button className="button-secondary" onClick={newRagChat}>
                    New Chat
                  </button>
                </div>
              </div>
            </section>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};
