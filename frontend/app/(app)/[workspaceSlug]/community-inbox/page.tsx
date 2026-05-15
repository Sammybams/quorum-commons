"use client";

import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";

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

export default function CommunityInboxPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [messages, setMessages] = useState<ChannelMessage[]>([]);
  const [artifacts, setArtifacts] = useState<MessageArtifact[]>([]);
  const [reviewQueue, setReviewQueue] = useState<MessageArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [reviewingArtifactId, setReviewingArtifactId] = useState<number | null>(null);
  const [viewFilter, setViewFilter] = useState<"highlights" | "all" | "whatsapp" | "telegram" | "needs_review">("highlights");

  async function loadInbox(workspaceId: number, options?: { background?: boolean }) {
    if (!options?.background) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    try {
      const [loadedMessages, loadedArtifacts, loadedReviewQueue] = await Promise.all([
        apiGet<ChannelMessage[]>(`/workspaces/${workspaceId}/community-channels/messages`),
        apiGet<MessageArtifact[]>(`/workspaces/${workspaceId}/community-channels/artifacts`),
        apiGet<MessageArtifact[]>(`/workspaces/${workspaceId}/community-channels/review-queue`),
      ]);
      setMessages(loadedMessages);
      setArtifacts(loadedArtifacts);
      setReviewQueue(loadedReviewQueue);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load community inbox.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    async function load() {
      try {
        const found = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        setWorkspace(found);
        await loadInbox(found.id);
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
      loadInbox(workspace.id, { background: true }).catch(() => {});
    }, 12000);
    return () => window.clearInterval(timer);
  }, [workspace]);

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
      setArtifacts((current) => [artifact, ...current.filter((item) => item.message_id !== messageId)]);
      if (artifact.status === "needs_review" || artifact.status === "analysis_failed") {
        setReviewQueue((current) => [artifact, ...current.filter((item) => item.id !== artifact.id)]);
      }
      setMessages((current) =>
        current.map((message) =>
          message.id === messageId ? { ...message, artifact_count: Math.max(message.artifact_count, 1) } : message,
        ),
      );
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
      setArtifacts((current) => [artifact, ...current.filter((item) => item.id !== artifact.id)]);
      setReviewQueue((current) => current.filter((item) => item.id !== artifact.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to ${action} artifact.`);
    } finally {
      setReviewingArtifactId(null);
    }
  }

  const artifactByMessage = new Map(artifacts.map((artifact) => [artifact.message_id, artifact]));
  const messageById = new Map(messages.map((message) => [message.id, message]));
  const filteredMessages = useMemo(() => {
    if (viewFilter === "highlights") {
      return messages.filter((message) => {
        const artifact = artifactByMessage.get(message.id);
        return Boolean(artifact && artifact.status !== "ignored");
      });
    }
    if (viewFilter === "all") {
      return messages;
    }
    if (viewFilter === "needs_review") {
      return messages.filter((message) => {
        const artifact = artifactByMessage.get(message.id);
        return artifact?.status === "needs_review" || artifact?.status === "analysis_failed";
      });
    }
    return messages.filter((message) => message.provider === viewFilter);
  }, [artifactByMessage, messages, viewFilter]);
  const highlightedGroupsCount = useMemo(
    () => new Set(filteredMessages.map((message) => message.external_group_id)).size,
    [filteredMessages],
  );
  const highlightedGroups = useMemo(() => {
    const seen = new Map<string, string>();
    for (const message of filteredMessages) {
      if (!seen.has(message.external_group_id)) {
        seen.set(message.external_group_id, message.group_name || message.external_group_id);
      }
    }
    return Array.from(seen.values());
  }, [filteredMessages]);

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
          onClick={() => (workspace ? loadInbox(workspace.id) : Promise.resolve())}
          disabled={loading || refreshing || !workspace}
        >
          {loading || refreshing ? "Refreshing..." : "Refresh inbox"}
        </button>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="metrics-grid">
        <article className="metric-card primary">
          <small>Messages</small>
          <strong>{messages.length}</strong>
          <p>Recent synced group messages</p>
        </article>
        <article className="metric-card">
          <small>Artifacts</small>
          <strong>{artifacts.length}</strong>
          <p>Extracted structured records</p>
        </article>
        <article className="metric-card">
          <small>Highlights</small>
          <strong>{messages.filter((message) => {
            const artifact = artifactByMessage.get(message.id);
            return Boolean(artifact && artifact.status !== "ignored");
          }).length}</strong>
          <p>Important message signals found</p>
        </article>
        <article className="metric-card">
          <small>Needs review</small>
          <strong>{reviewQueue.length}</strong>
          <p>Queued for human approval</p>
        </article>
      </section>

      <section className="community-inbox-layout">
        <article className="panel-card community-feed-card">
          <div className="card-head">
            <div>
              <h2>Live log</h2>
              <p className="muted-copy">Scroll through tagged highlights from {highlightedGroupsCount || 0} synced group{highlightedGroupsCount === 1 ? "" : "s"}.</p>
            </div>
            <span className="status-pill">{loading ? "Loading" : `${filteredMessages.length} shown`}</span>
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

          {filteredMessages.length === 0 ? (
            <div className="empty-block">
              <span className="material-symbols-outlined" aria-hidden="true">
                forum
              </span>
              <h3>No synced messages yet</h3>
              <p>Enable a Telegram or WhatsApp group in Integrations and refresh this inbox after syncing messages.</p>
            </div>
          ) : (
            <div className="community-feed-list">
              {filteredMessages.map((message) => {
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
                const message = messageById.get(artifact.message_id);
                return (
                  <article key={artifact.id} className="review-queue-item">
                    <div className="review-queue-top">
                      <span className={`status-pill ${artifactTone(artifact.status)}`}>{humanizeArtifactType(artifact.artifact_type)}</span>
                      <small>{Math.round(artifact.confidence * 100)}%</small>
                    </div>
                    <p>{message?.text || "Message unavailable in current inbox window."}</p>
                    <small className="muted-copy">
                      {artifact.status === "analysis_failed" ? "AI analysis failed" : "Confidence below auto-approve threshold"}
                    </small>
                    <div className="review-queue-actions">
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={reviewingArtifactId === artifact.id}
                        onClick={() => reviewArtifact(artifact.id, "approve")}
                      >
                        {reviewingArtifactId === artifact.id ? "Working..." : "Approve"}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={reviewingArtifactId === artifact.id}
                        onClick={() => reviewArtifact(artifact.id, "reject")}
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
