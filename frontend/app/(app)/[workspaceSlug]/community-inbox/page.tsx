"use client";

import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";
import { resolveWorkspace } from "@/lib/workspace-client";

type Workspace = { id: number; slug: string; name: string };
type ChannelMessage = {
  id: number;
  workspace_id: number;
  channel_id: number;
  provider: string;
  external_group_id: string;
  group_name?: string | null;
  sender_name?: string | null;
  sender_handle?: string | null;
  message_type: string;
  text: string;
  artifact_count: number;
  received_at: string;
  created_at: string;
};
type MessageArtifact = {
  id: number;
  workspace_id: number;
  message_id: number;
  artifact_type: string;
  confidence: number;
  summary?: string | null;
  extracted_payload: Record<string, unknown>;
  status: string;
  reviewed_at?: string | null;
  reviewed_by_user_id?: number | null;
  review_note?: string | null;
  created_at: string;
};
type CommunityHighlight = {
  message_id: number;
  workspace_id: number;
  channel_id: number;
  provider: string;
  external_group_id: string;
  group_name?: string | null;
  sender_name?: string | null;
  sender_handle?: string | null;
  message_type: string;
  text: string;
  received_at: string;
  artifact_id: number;
  artifact_type: string;
  confidence: number;
  summary?: string | null;
  extracted_payload: Record<string, unknown>;
  status: string;
  reviewed_at?: string | null;
  reviewed_by_user_id?: number | null;
  review_note?: string | null;
  created_at: string;
};
type CommunityInboxFeed = {
  highlights: CommunityHighlight[];
  review_queue: CommunityHighlight[];
  refreshed_at: string;
};

const HIGHLIGHTS_CACHE_PREFIX = "community-inbox-highlights:";

function highlightsCacheKey(workspaceSlug: string) {
  return `${HIGHLIGHTS_CACHE_PREFIX}${workspaceSlug}`;
}

function readCachedFeed(workspaceSlug: string): CommunityInboxFeed | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(highlightsCacheKey(workspaceSlug));
    return raw ? (JSON.parse(raw) as CommunityInboxFeed) : null;
  } catch {
    return null;
  }
}

function writeCachedFeed(workspaceSlug: string, feed: CommunityInboxFeed) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(highlightsCacheKey(workspaceSlug), JSON.stringify(feed));
  } catch {
    // Ignore storage failures and still show the live response.
  }
}

export default function CommunityInboxPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [messages, setMessages] = useState<ChannelMessage[] | null>(null);
  const [highlights, setHighlights] = useState<CommunityHighlight[]>([]);
  const [reviewQueue, setReviewQueue] = useState<CommunityHighlight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [reviewingArtifactId, setReviewingArtifactId] = useState<number | null>(null);
  const [loadingAllMessages, setLoadingAllMessages] = useState(false);
  const [viewFilter, setViewFilter] = useState<"highlights" | "all" | "whatsapp" | "telegram" | "needs_review">("highlights");

  async function loadFeed(workspaceId: number, options?: { background?: boolean }) {
    if (!options?.background) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    try {
      const feed = await apiGet<CommunityInboxFeed>(`/workspaces/${workspaceId}/community-channels/feed`);
      setHighlights(feed.highlights);
      setReviewQueue(feed.review_queue);
      writeCachedFeed(params.workspaceSlug, feed);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load community inbox.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  async function loadAllMessages(workspaceId: number, options?: { background?: boolean }) {
    if (!options?.background) {
      setLoadingAllMessages(true);
    }
    try {
      const loadedMessages = await apiGet<ChannelMessage[]>(`/workspaces/${workspaceId}/community-channels/messages`);
      setMessages(loadedMessages);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load recent message window.");
    } finally {
      setLoadingAllMessages(false);
    }
  }

  useEffect(() => {
    async function load() {
      const cachedFeed = readCachedFeed(params.workspaceSlug);
      if (cachedFeed) {
        setHighlights(cachedFeed.highlights);
        setReviewQueue(cachedFeed.review_queue);
        setLoading(false);
      }
      try {
        const found = await resolveWorkspace(params.workspaceSlug);
        setWorkspace(found);
        await loadFeed(found.id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load community inbox.");
      }
    }

    load();
  }, [params.workspaceSlug]);

  useEffect(() => {
    if (!workspace) {
      return;
    }
    const timer = window.setInterval(() => {
      loadFeed(workspace.id, { background: true }).catch(() => {});
    }, 12000);
    return () => window.clearInterval(timer);
  }, [workspace]);

  useEffect(() => {
    if (!workspace || viewFilter !== "all" || messages) {
      return;
    }
    loadAllMessages(workspace.id).catch(() => {});
  }, [messages, viewFilter, workspace]);

  async function analyzeMessage(messageId: number) {
    if (!workspace) {
      return;
    }
    setAnalyzingId(messageId);
    setError(null);
    try {
      const artifact = await apiPost<MessageArtifact, Record<string, never>>(
        `/workspaces/${workspace.id}/community-channels/messages/${messageId}/analyze`,
        {},
      );
      setMessages((current) =>
        current
          ? current.map((message) =>
          message.id === messageId ? { ...message, artifact_count: Math.max(message.artifact_count, 1) } : message,
            )
          : null,
      );
      await loadFeed(workspace.id, { background: true });
      if (viewFilter === "all") {
        setMessages((current) =>
          current?.map((message) =>
            message.id === messageId ? { ...message, artifact_count: Math.max(message.artifact_count, 1) } : message,
          ) || null,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to analyze message.");
    } finally {
      setAnalyzingId(null);
    }
  }

  async function reviewArtifact(artifactId: number, action: "approve" | "reject") {
    if (!workspace) {
      return;
    }
    setReviewingArtifactId(artifactId);
    setError(null);
    try {
      const artifact = await apiPost<MessageArtifact, { note?: string }>(
        `/workspaces/${workspace.id}/community-channels/artifacts/${artifactId}/${action}`,
        {},
      );
      await loadFeed(workspace.id, { background: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to ${action} artifact.`);
    } finally {
      setReviewingArtifactId(null);
    }
  }

  const artifactByMessage = new Map(highlights.map((highlight) => [highlight.message_id, highlight]));
  const filteredHighlights = useMemo(() => {
    if (viewFilter === "highlights") {
      return highlights;
    }
    if (viewFilter === "needs_review") {
      return reviewQueue;
    }
    if (viewFilter === "whatsapp" || viewFilter === "telegram") {
      return highlights.filter((highlight) => highlight.provider === viewFilter);
    }
    return highlights;
  }, [highlights, reviewQueue, viewFilter]);
  const visibleMessages = viewFilter === "all" ? messages || [] : filteredHighlights;
  const highlightedGroupsCount = useMemo(
    () => new Set(visibleMessages.map((message) => message.external_group_id)).size,
    [visibleMessages],
  );
  const highlightedGroups = useMemo(() => {
    const seen = new Map<string, string>();
    for (const message of visibleMessages) {
      if (!seen.has(message.external_group_id)) {
        seen.set(message.external_group_id, message.group_name || message.external_group_id);
      }
    }
    return Array.from(seen.values());
  }, [visibleMessages]);
  const todaysHighlightCount = useMemo(() => {
    const today = new Date().toDateString();
    return highlights.filter((highlight) => new Date(highlight.received_at).toDateString() === today).length;
  }, [highlights]);

  function formatTime(value: string) {
    try {
      return new Date(value).toLocaleString("en-NG", {
        day: "numeric",
        month: "short",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch {
      return value;
    }
  }

  function humanizeArtifactType(value: string) {
    return value.replaceAll("_", " ");
  }

  function artifactTone(status: string) {
    if (status === "approved" || status === "ready") return "ok";
    if (status === "needs_review") return "pending";
    if (status === "analysis_failed" || status === "rejected") return "danger";
    return "neutral";
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Community Inbox</p>
          <h1>Channel intelligence</h1>
          <p>{workspace?.name || params.workspaceSlug}</p>
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={() =>
            workspace
              ? Promise.all([
                  loadFeed(workspace.id),
                  viewFilter === "all" ? loadAllMessages(workspace.id, { background: true }) : Promise.resolve(),
                ])
              : Promise.resolve()
          }
          disabled={loading || refreshing || !workspace}
        >
          {loading || refreshing ? "Refreshing..." : "Refresh inbox"}
        </button>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="metrics-grid">
        <article className="metric-card primary">
          <small>Highlights</small>
          <strong>{highlights.length}</strong>
          <p>Saved actionable signals ready to read</p>
        </article>
        <article className="metric-card">
          <small>Needs review</small>
          <strong>{reviewQueue.length}</strong>
          <p>Queued for quick human approval</p>
        </article>
        <article className="metric-card">
          <small>Groups covered</small>
          <strong>{new Set(highlights.map((highlight) => highlight.external_group_id)).size}</strong>
          <p>Synced groups with meaningful extracted items</p>
        </article>
        <article className="metric-card">
          <small>Today</small>
          <strong>{todaysHighlightCount}</strong>
          <p>Highlights analyzed so far today</p>
        </article>
      </section>

      <section className="community-inbox-layout">
        <article className="panel-card community-feed-card">
          <div className="card-head">
            <div>
              <h2>Live log</h2>
              <p className="muted-copy">Recent meaningful signals stay visible here while Quorum keeps updating them in the background.</p>
            </div>
            <span className="status-pill">{loading ? "Loading" : `${visibleMessages.length} shown`}</span>
          </div>

          {highlightedGroups.length ? (
            <div className="community-group-strip">
              <span className="muted-copy">Watching</span>
              {highlightedGroups.slice(0, 4).map((groupName) => (
                <span key={groupName} className="group-chip">
                  {groupName}
                </span>
              ))}
              {highlightedGroups.length > 4 ? (
                <span className="muted-copy">+{highlightedGroups.length - 4} more</span>
              ) : null}
            </div>
          ) : null}

          <div className="community-filter-row">
            <button type="button" className={`filter-chip ${viewFilter === "highlights" ? "active" : ""}`} onClick={() => setViewFilter("highlights")}>
              Highlights
            </button>
            <button type="button" className={`filter-chip ${viewFilter === "all" ? "active" : ""}`} onClick={() => setViewFilter("all")}>
              All
            </button>
            <button type="button" className={`filter-chip ${viewFilter === "whatsapp" ? "active" : ""}`} onClick={() => setViewFilter("whatsapp")}>
              WhatsApp
            </button>
            <button type="button" className={`filter-chip ${viewFilter === "telegram" ? "active" : ""}`} onClick={() => setViewFilter("telegram")}>
              Telegram
            </button>
            <button type="button" className={`filter-chip ${viewFilter === "needs_review" ? "active" : ""}`} onClick={() => setViewFilter("needs_review")}>
              Needs review
            </button>
          </div>

          {visibleMessages.length === 0 ? (
            <div className="empty-block">
              <span className="material-symbols-outlined" aria-hidden="true">
                forum
              </span>
              <h3>{viewFilter === "all" && loadingAllMessages ? "Loading recent message window" : "No synced messages yet"}</h3>
              <p>
                {viewFilter === "all"
                  ? "Quorum loads the broader raw message window only when you ask for it."
                  : "Enable a Telegram or WhatsApp group in Integrations and refresh this inbox after syncing messages."}
              </p>
            </div>
          ) : (
            <div className="community-feed-list">
              {viewFilter === "all"
                ? (messages || []).map((message) => {
                    const artifact = artifactByMessage.get(message.id);
                    return (
                      <article key={message.id} className="community-log-item">
                        <div className="community-log-meta">
                          <div className="community-log-source">
                            <span className={`source-pill ${message.provider}`}>{message.provider}</span>
                          </div>
                          <small>{formatTime(message.received_at)}</small>
                        </div>

                        <div className="community-log-body">
                          <div className="community-log-sender">{message.sender_name || message.sender_handle || "Unknown sender"}</div>
                          <p>{message.text}</p>
                        </div>

                        <div className="community-log-footer">
                          {artifact ? (
                            <div className="artifact-inline">
                              <span className="tag-pill">{humanizeArtifactType(artifact.artifact_type)}</span>
                              {artifact.status !== "ready" && artifact.status !== "approved" ? (
                                <span className={`status-pill ${artifactTone(artifact.status)}`}>{artifact.status.replaceAll("_", " ")}</span>
                              ) : null}
                            </div>
                          ) : (
                            <span className="muted-copy">Awaiting analysis</span>
                          )}

                          {!artifact ? (
                            <button
                              type="button"
                              className="btn-secondary"
                              disabled={analyzingId === message.id}
                              onClick={() => analyzeMessage(message.id)}
                            >
                              {analyzingId === message.id ? "Analyzing..." : "Analyze"}
                            </button>
                          ) : null}
                        </div>
                      </article>
                    );
                  })
                : filteredHighlights.map((message) => {
                    const artifact = message;
                    return (
                      <article key={message.artifact_id} className="community-log-item">
                        <div className="community-log-meta">
                          <div className="community-log-source">
                            <span className={`source-pill ${message.provider}`}>{message.provider}</span>
                          </div>
                          <small>{formatTime(message.received_at)}</small>
                        </div>

                        <div className="community-log-body">
                          <div className="community-log-sender">{message.sender_name || message.sender_handle || "Unknown sender"}</div>
                          <p>{message.text}</p>
                        </div>

                        <div className="community-log-footer">
                          <div className="artifact-inline">
                            <span className="tag-pill">{humanizeArtifactType(artifact.artifact_type)}</span>
                            {artifact.status !== "ready" && artifact.status !== "approved" ? (
                              <span className={`status-pill ${artifactTone(artifact.status)}`}>{artifact.status.replaceAll("_", " ")}</span>
                            ) : null}
                          </div>
                        </div>
                      </article>
                    );
                  })}
            </div>
          )}
        </article>

        <aside className="panel-card community-review-card">
          <div className="card-head">
            <div>
              <h2>Review queue</h2>
              <p className="muted-copy">Approve uncertain extractions before Quorum turns them into structured records.</p>
            </div>
            <span className="status-pill">{reviewQueue.length} pending</span>
          </div>
          {reviewQueue.length === 0 ? (
            <p className="muted-copy">No pending review items right now.</p>
          ) : (
            <div className="review-queue-list">
              {reviewQueue.map((artifact) => {
                return (
                  <article key={artifact.artifact_id} className="review-queue-item">
                    <div className="review-queue-top">
                      <span className={`status-pill ${artifactTone(artifact.status)}`}>{humanizeArtifactType(artifact.artifact_type)}</span>
                      <small>{Math.round(artifact.confidence * 100)}%</small>
                    </div>
                    <p>{artifact.text || "Message unavailable in current inbox window."}</p>
                    <small className="muted-copy">
                      {artifact.status === "analysis_failed" ? "AI analysis failed" : "Confidence below auto-approve threshold"}
                    </small>
                    <div className="review-queue-actions">
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={reviewingArtifactId === artifact.artifact_id}
                        onClick={() => reviewArtifact(artifact.artifact_id, "approve")}
                      >
                        {reviewingArtifactId === artifact.artifact_id ? "Working..." : "Approve"}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={reviewingArtifactId === artifact.artifact_id}
                        onClick={() => reviewArtifact(artifact.artifact_id, "reject")}
                      >
                        Reject
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </aside>
      </section>
    </section>
  );
}
