"use client";

import { useEffect, useState } from "react";

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
  created_at: string;
};

export default function CommunityInboxPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [messages, setMessages] = useState<ChannelMessage[]>([]);
  const [artifacts, setArtifacts] = useState<MessageArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const found = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        setWorkspace(found);
        const [loadedMessages, loadedArtifacts] = await Promise.all([
          apiGet<ChannelMessage[]>(`/workspaces/${found.id}/community-channels/messages`),
          apiGet<MessageArtifact[]>(`/workspaces/${found.id}/community-channels/artifacts`),
        ]);
        setMessages(loadedMessages);
        setArtifacts(loadedArtifacts);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load community inbox.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.workspaceSlug]);

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

  const artifactByMessage = new Map(artifacts.map((artifact) => [artifact.message_id, artifact]));

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Community Inbox</p>
          <h1>Channel intelligence</h1>
          <p>{workspace?.name || params.workspaceSlug}</p>
        </div>
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
      </section>

      <article className="panel-card">
        <div className="card-head">
          <h2>Recent messages</h2>
          <span className="status-pill">{loading ? "Loading" : `${messages.length} items`}</span>
        </div>
        {messages.length === 0 ? (
          <div className="empty-block">
            <span className="material-symbols-outlined" aria-hidden="true">
              forum
            </span>
            <h3>No synced messages yet</h3>
            <p>Enable a Telegram or WhatsApp group in Integrations and new messages will appear here.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Sender</th>
                  <th>Message</th>
                  <th>AI extraction</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {messages.map((message) => {
                  const artifact = artifactByMessage.get(message.id);
                  return (
                    <tr key={message.id}>
                      <td>
                        <div>{message.group_name || message.external_group_id}</div>
                        <small>{message.provider}</small>
                      </td>
                      <td>{message.sender_name || message.sender_handle || "-"}</td>
                      <td>{message.text}</td>
                      <td>
                        {artifact ? (
                          <>
                            <div>{artifact.artifact_type}</div>
                            <small>{Math.round(artifact.confidence * 100)}% confidence</small>
                          </>
                        ) : (
                          "Not analyzed yet"
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={analyzingId === message.id}
                          onClick={() => analyzeMessage(message.id)}
                        >
                          {analyzingId === message.id ? "Analyzing..." : artifact ? "Re-run" : "Analyze"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
