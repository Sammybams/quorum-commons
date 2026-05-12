"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { apiDelete, apiGet, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Integration = {
  provider: string;
  status: string;
  configured: boolean;
  connected_email?: string | null;
  scopes: string[];
  connected_at?: string | null;
  expires_at?: string | null;
  metadata: Record<string, string>;
};

function IntegrationsPageContent({ params }: { params: { workspaceSlug: string } }) {
  const searchParams = useSearchParams();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [integration, setIntegration] = useState<Integration | null>(null);
  const [fireflies, setFireflies] = useState<Integration | null>(null);
  const [error, setError] = useState<string | null>(searchParams.get("message"));
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const found = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        setWorkspace(found);
        const integrations = await apiGet<Integration[]>(`/workspaces/${found.id}/integrations`);
        setIntegration(integrations.find((item) => item.provider === "google_workspace") || null);
        setFireflies(integrations.find((item) => item.provider === "fireflies") || null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load integrations.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.workspaceSlug]);

  const needsGoogleReconnect = useMemo(
    () => integration?.status === "connected" && integration?.metadata?.gmail !== "available",
    [integration],
  );

  async function connectGoogle() {
    if (!workspace) {
      return;
    }
    setConnecting(true);
    setError(null);
    try {
      const result = await apiPost<{ authorization_url: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/integrations/google/oauth/start`,
        {},
      );
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start Google connection.");
      setConnecting(false);
    }
  }

  async function disconnectGoogle() {
    if (!workspace) {
      return;
    }
    setConnecting(true);
    setError(null);
    try {
      await apiDelete(`/workspaces/${workspace.id}/integrations/google`);
      setIntegration((current) =>
        current
          ? {
              ...current,
              status: "not_connected",
              connected_email: null,
              connected_at: null,
              metadata: { ...current.metadata, gmail: "available" },
            }
          : current,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disconnect Google Workspace.");
    } finally {
      setConnecting(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Integrations</h1>
          <p>{workspace?.name || params.workspaceSlug}</p>
        </div>
        <Link href={`/${params.workspaceSlug}/settings/workspace`} className="btn-secondary">
          Workspace settings
        </Link>
      </header>

      {searchParams.get("status") === "connected" ? <p className="status-note">Google Workspace connected.</p> : null}
      {error ? <p className="form-error">{error}</p> : null}

      <section className="content-grid">
        <article className="panel-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Google Workspace</p>
              <h2>Meet, Drive, and Gmail</h2>
            </div>
            <span className={`status-pill ${integration?.status === "connected" ? "ok" : "pending"}`}>
              {loading ? "Loading" : integration?.status === "connected" ? "Connected" : "Not connected"}
            </span>
          </div>
          <p>Connect a Google account once per workspace to create Meet links, sync transcripts, and send member invitations from the connected Gmail account.</p>
          <div className="mini-list">
            <div>
              <span>Account</span>
              <strong>{integration?.connected_email || "No account connected"}</strong>
            </div>
            <div>
              <span>Scopes</span>
              <strong>{integration?.scopes?.length ? integration.scopes.length : 0}</strong>
            </div>
            <div>
              <span>Connected at</span>
              <strong>{integration?.connected_at || "-"}</strong>
            </div>
            <div>
              <span>Invitations</span>
              <strong>{needsGoogleReconnect ? "Reconnect Google to grant Gmail sending" : integration?.metadata?.gmail === "available" ? "Send from Gmail" : "Waiting for Google connection"}</strong>
            </div>
          </div>
          {needsGoogleReconnect ? (
            <div className="status-note">
              This workspace was connected before Gmail sending was added. Reconnect Google once so Quorum can request the Gmail permission and send invitations from <strong>{integration?.connected_email}</strong>.
            </div>
          ) : null}
          <div className="page-actions">
            <button type="button" className="btn-primary" onClick={connectGoogle} disabled={connecting || !integration?.configured}>
              {connecting
                ? "Opening..."
                : needsGoogleReconnect
                  ? "Reconnect for Gmail"
                  : integration?.status === "connected"
                    ? "Reconnect Google"
                    : "Connect Google"}
            </button>
            {integration?.status === "connected" ? (
              <button type="button" className="btn-secondary" onClick={disconnectGoogle} disabled={connecting}>
                Disconnect
              </button>
            ) : null}
          </div>
          {!integration?.configured ? (
            <p className="muted-copy">Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_OAUTH_REDIRECT_URI` on the backend before connecting.</p>
          ) : null}
        </article>

        <article className="panel-card">
          <p className="eyebrow">What this unlocks</p>
          <h2>Connected workflow</h2>
          <div className="mini-list">
            <div>
              <span>Meet</span>
              <strong>Create meeting links directly from Quorum meetings</strong>
            </div>
            <div>
              <span>Drive</span>
              <strong>Foundation for transcript and artifact syncing</strong>
            </div>
            <div>
              <span>Gmail</span>
              <strong>Workspace invitations can come from the connected Google account</strong>
            </div>
            <div>
              <span>Next</span>
              <strong>Automatic transcript ingestion after meetings</strong>
            </div>
          </div>
        </article>

        <article className="panel-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Fireflies</p>
              <h2>Transcript fallback</h2>
            </div>
            <span className={`status-pill ${fireflies?.configured ? "ok" : "pending"}`}>
              {fireflies?.configured ? "Configured" : "Not configured"}
            </span>
          </div>
          <p>Fireflies is available as a server-side fallback. Once configured, admins can import a transcript ID directly into a Quorum meeting and run the same Claude minutes pipeline.</p>
          <div className="mini-list">
            <div>
              <span>Mode</span>
              <strong>{fireflies?.metadata?.mode || "server_key"}</strong>
            </div>
            <div>
              <span>Import</span>
              <strong>{fireflies?.metadata?.import || "transcript_id"}</strong>
            </div>
          </div>
          {!fireflies?.configured ? <p className="muted-copy">Set `FIREFLIES_API_KEY` on the backend to enable transcript import.</p> : null}
        </article>
      </section>
    </section>
  );
}

function IntegrationsPageFallback({ params }: { params: { workspaceSlug: string } }) {
  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Integrations</h1>
          <p>{params.workspaceSlug}</p>
        </div>
      </header>
      <section className="content-grid">
        <article className="panel-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Google Workspace</p>
              <h2>Meet, Drive, and Gmail</h2>
            </div>
            <span className="status-pill pending">Loading</span>
          </div>
          <p>Loading integration status...</p>
        </article>
      </section>
    </section>
  );
}

export default function IntegrationsPage({ params }: { params: { workspaceSlug: string } }) {
  return (
    <Suspense fallback={<IntegrationsPageFallback params={params} />}>
      <IntegrationsPageContent params={params} />
    </Suspense>
  );
}
