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
  linked_record_type?: string | null;
  linked_record_label?: string | null;
  verification_state?: string | null;
  provider_verification_status?: string | null;
  provider_verification_note?: string | null;
  provider_verified_amount?: number | null;
  linked_task_id?: number | null;
  linked_task_title?: string | null;
  suggested_assignee_member_id?: number | null;
  suggested_assignee_name?: string | null;
  created_at: string;
};
type CommunityInboxAuditItem = {
  item_type: string;
  title: string;
  detail: string;
  actor_name?: string | null;
  created_at: string;
};
type CommunityInboxFeed = {
  highlights: CommunityHighlight[];
  review_queue: CommunityHighlight[];
  audit_trail: CommunityInboxAuditItem[];
  refreshed_at: string;
};

type ArtifactWithOptionalLink = {
  artifact_type: string;
  linked_record_label?: string | null;
  verification_state?: string | null;
  provider_verification_status?: string | null;
  provider_verification_note?: string | null;
  provider_verified_amount?: number | null;
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
  const [allArtifacts, setAllArtifacts] = useState<MessageArtifact[] | null>(null);
  const [highlights, setHighlights] = useState<CommunityHighlight[]>([]);
  const [reviewQueue, setReviewQueue] = useState<CommunityHighlight[]>([]);
  const [auditTrail, setAuditTrail] = useState<CommunityInboxAuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [reviewingArtifactId, setReviewingArtifactId] = useState<number | null>(null);
  const [creatingTaskArtifactId, setCreatingTaskArtifactId] = useState<number | null>(null);
  const [bulkReviewing, setBulkReviewing] = useState<"approve" | "reject" | null>(null);
  const [loadingAllMessages, setLoadingAllMessages] = useState(false);
  const [viewFilter, setViewFilter] = useState<"highlights" | "all" | "whatsapp" | "telegram" | "needs_review" | "opportunities" | "tasks" | "receipts">("highlights");

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
      setAuditTrail(feed.audit_trail || []);
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

  async function loadAllArtifacts(workspaceId: number) {
    try {
      const loadedArtifacts = await apiGet<MessageArtifact[]>(`/workspaces/${workspaceId}/community-channels/artifacts`);
      setAllArtifacts(loadedArtifacts);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load analyzed message window.");
    }
  }

  useEffect(() => {
    async function load() {
      const cachedFeed = readCachedFeed(params.workspaceSlug);
      if (cachedFeed) {
        setHighlights(cachedFeed.highlights);
        setReviewQueue(cachedFeed.review_queue);
        setAuditTrail(cachedFeed.audit_trail || []);
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
      if (viewFilter === "all") {
        Promise.all([
          loadAllMessages(workspace.id, { background: true }),
          loadAllArtifacts(workspace.id),
        ]).catch(() => {});
        return;
      }
      loadFeed(workspace.id, { background: true }).catch(() => {});
    }, 12000);
    return () => window.clearInterval(timer);
  }, [viewFilter, workspace]);

  useEffect(() => {
    if (!workspace || viewFilter !== "all" || (messages && allArtifacts)) {
      return;
    }
    Promise.all([
      loadAllMessages(workspace.id),
      loadAllArtifacts(workspace.id),
    ]).catch(() => {});
  }, [allArtifacts, messages, viewFilter, workspace]);

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
        await loadAllArtifacts(workspace.id);
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

  async function createTaskFromArtifact(artifactId: number) {
    if (!workspace) {
      return;
    }
    setCreatingTaskArtifactId(artifactId);
    setError(null);
    try {
      await apiPost(
        `/workspaces/${workspace.id}/community-channels/artifacts/${artifactId}/create-task`,
        {},
      );
      await loadFeed(workspace.id, { background: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create task from this artifact.");
    } finally {
      setCreatingTaskArtifactId(null);
    }
  }

  async function bulkReview(action: "approve" | "reject") {
    if (!workspace || reviewQueue.length === 0) {
      return;
    }
    setBulkReviewing(action);
    setError(null);
    try {
      await apiPost(
        `/workspaces/${workspace.id}/community-channels/artifacts/review-bulk`,
        { artifact_ids: reviewQueue.map((item) => item.artifact_id), action },
      );
      await loadFeed(workspace.id, { background: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to ${action} the review queue.`);
    } finally {
      setBulkReviewing(null);
    }
  }

  const artifactByMessage = new Map<number, MessageArtifact | CommunityHighlight>()
  for (const artifact of allArtifacts || []) {
    artifactByMessage.set(artifact.message_id, artifact)
  }
  for (const highlight of highlights) {
    artifactByMessage.set(highlight.message_id, highlight)
  }
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
    if (viewFilter === "opportunities") {
      return highlights.filter((highlight) => highlight.artifact_type === "opportunity");
    }
    if (viewFilter === "tasks") {
      return highlights.filter((highlight) => highlight.artifact_type === "task_signal");
    }
    if (viewFilter === "receipts") {
      return highlights.filter((highlight) => ["payment_receipt", "contribution_signal"].includes(highlight.artifact_type));
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

  function renderFinancialLinkLine(item: ArtifactWithOptionalLink) {
    if (!["payment_receipt", "contribution_signal"].includes(item.artifact_type)) {
      return null;
    }
    if (item.provider_verification_status === "verified") {
      return <small className="muted-copy">{item.provider_verification_note || "Matched against Squad transaction data"}</small>;
    }
    if (item.provider_verification_status === "amount_mismatch") {
      return <small className="muted-copy">{item.provider_verification_note || "Squad found this reference, but the amount does not match."}</small>;
    }
    if (item.provider_verification_status === "reference_not_confirmed" || item.provider_verification_status === "reference_not_found") {
      return <small className="muted-copy">{item.provider_verification_note || "Squad could not confirm this transaction reference yet."}</small>;
    }
    if (item.linked_record_label) {
      return <small className="muted-copy">Matched to {item.linked_record_label}</small>;
    }
    if (item.verification_state === "needs_review") {
      return <small className="muted-copy">Possible match found, review before trusting it</small>;
    }
    if (item.verification_state === "unlinked") {
      return <small className="muted-copy">Receipt captured, not linked yet</small>;
    }
    return null;
  }

  function canCreateTask(item: CommunityHighlight) {
    return item.artifact_type === "task_signal" && !item.linked_task_id;
  }

  function artifactIdentifier(item: MessageArtifact | CommunityHighlight) {
    return "artifact_id" in item ? item.artifact_id : item.id;
  }

  const clusteredHighlights = useMemo(() => {
    if (viewFilter === "all") {
      return [];
    }
    const buckets = new Map<string, { label: string; items: CommunityHighlight[] }>();
    for (const item of filteredHighlights) {
      const day = new Date(item.received_at).toLocaleDateString("en-NG", { day: "numeric", month: "short" });
      const label = `${item.group_name || item.external_group_id} · ${day}`;
      const key = `${item.external_group_id}:${day}`;
      if (!buckets.has(key)) {
        buckets.set(key, { label, items: [] });
      }
      buckets.get(key)?.items.push(item);
    }
    return Array.from(buckets.values());
  }, [filteredHighlights, viewFilter]);

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
            <button type="button" className={`filter-chip ${viewFilter === "opportunities" ? "active" : ""}`} onClick={() => setViewFilter("opportunities")}>
              Opportunities
            </button>
            <button type="button" className={`filter-chip ${viewFilter === "tasks" ? "active" : ""}`} onClick={() => setViewFilter("tasks")}>
              Tasks
            </button>
            <button type="button" className={`filter-chip ${viewFilter === "receipts" ? "active" : ""}`} onClick={() => setViewFilter("receipts")}>
              Receipts
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
                            <div>
                              <div className="artifact-inline">
                                <span className="tag-pill">{humanizeArtifactType(artifact.artifact_type)}</span>
                                {artifact.status !== "ready" && artifact.status !== "approved" ? (
                                  <span className={`status-pill ${artifactTone(artifact.status)}`}>{artifact.status.replaceAll("_", " ")}</span>
                                ) : null}
                              </div>
                              {renderFinancialLinkLine(artifact)}
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
                : clusteredHighlights.map((cluster) => (
                    <section key={cluster.label} className="community-cluster">
                      <div className="community-cluster-head">
                        <h3>{cluster.label}</h3>
                        <small>{cluster.items.length} items</small>
                      </div>
                      {cluster.items.map((message) => {
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
                              <div>
                                <div className="artifact-inline">
                                  <span className="tag-pill">{humanizeArtifactType(artifact.artifact_type)}</span>
                                  {artifact.status !== "ready" && artifact.status !== "approved" ? (
                                    <span className={`status-pill ${artifactTone(artifact.status)}`}>{artifact.status.replaceAll("_", " ")}</span>
                                  ) : null}
                                </div>
                                {renderFinancialLinkLine(artifact)}
                                {artifact.linked_task_title ? <small className="muted-copy">Task created: {artifact.linked_task_title}</small> : null}
                                {artifact.suggested_assignee_name && !artifact.linked_task_id ? (
                                  <small className="muted-copy">Suggested assignee: {artifact.suggested_assignee_name}</small>
                                ) : null}
                              </div>
                              {artifact.artifact_type === "task_signal" && !artifact.linked_task_id ? (
                                <button
                                  type="button"
                                  className="btn-secondary"
                                  disabled={creatingTaskArtifactId === artifactIdentifier(artifact)}
                                  onClick={() => createTaskFromArtifact(artifactIdentifier(artifact))}
                                >
                                  {creatingTaskArtifactId === artifactIdentifier(artifact) ? "Creating..." : "Create task"}
                                </button>
                              ) : null}
                            </div>
                          </article>
                        );
                      })}
                    </section>
                  ))}
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
          {reviewQueue.length ? (
            <div className="card-actions">
              <button type="button" className="btn-primary" disabled={bulkReviewing !== null} onClick={() => bulkReview("approve")}>
                {bulkReviewing === "approve" ? "Approving..." : "Approve all shown"}
              </button>
              <button type="button" className="btn-secondary" disabled={bulkReviewing !== null} onClick={() => bulkReview("reject")}>
                {bulkReviewing === "reject" ? "Rejecting..." : "Reject all shown"}
              </button>
            </div>
          ) : null}
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
                    {renderFinancialLinkLine(artifact)}
                    {artifact.linked_task_title ? <small className="muted-copy">Task created: {artifact.linked_task_title}</small> : null}
                    {artifact.suggested_assignee_name && !artifact.linked_task_id ? <small className="muted-copy">Suggested assignee: {artifact.suggested_assignee_name}</small> : null}
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
                      {canCreateTask(artifact) ? (
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={creatingTaskArtifactId === artifact.artifact_id}
                          onClick={() => createTaskFromArtifact(artifact.artifact_id)}
                        >
                          {creatingTaskArtifactId === artifact.artifact_id ? "Creating..." : "Create task"}
                        </button>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          <div className="community-audit-block">
            <div className="card-head compact">
              <h2>Audit trail</h2>
            </div>
            {auditTrail.length === 0 ? (
              <p className="muted-copy">Reviews and task conversions will appear here.</p>
            ) : (
              <div className="activity-list">
                {auditTrail.map((item) => (
                  <div key={`${item.item_type}-${item.created_at}-${item.title}`} className="activity-item">
                    <div>
                      <h3>{item.title}</h3>
                      <p>{item.detail}</p>
                      {item.actor_name ? <p className="muted-copy">By {item.actor_name}</p> : null}
                    </div>
                    <span>{formatTime(item.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      </section>
    </section>
  );
}
