"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";

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
type CommunityChannel = {
  id: number;
  workspace_id: number;
  provider: string;
  label: string;
  status: string;
  connected_at?: string | null;
  created_at: string;
  metadata: Record<string, string | number | boolean | null>;
};
type ChannelGroup = {
  id: number;
  workspace_id: number;
  channel_id: number;
  provider: string;
  external_group_id: string;
  group_name: string;
  sync_enabled: boolean;
  last_seen_at?: string | null;
  last_message_at?: string | null;
  message_count: number;
  created_at: string;
};

function IntegrationsPageContent({ params }: { params: { workspaceSlug: string } }) {
  const searchParams = useSearchParams();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [googleIntegration, setGoogleIntegration] = useState<Integration | null>(null);
  const [squadIntegration, setSquadIntegration] = useState<Integration | null>(null);
  const [fireflies, setFireflies] = useState<Integration | null>(null);
  const [channels, setChannels] = useState<CommunityChannel[]>([]);
  const [groupsByChannel, setGroupsByChannel] = useState<Record<number, ChannelGroup[]>>({});
  const [error, setError] = useState<string | null>(searchParams.get("message"));
  const [loading, setLoading] = useState(true);
  const [connectingGoogle, setConnectingGoogle] = useState(false);
  const [savingSquad, setSavingSquad] = useState(false);
  const [savingTelegram, setSavingTelegram] = useState(false);
  const [savingWhatsApp, setSavingWhatsApp] = useState(false);
  const [merchantName, setMerchantName] = useState("");
  const [beneficiaryAccount, setBeneficiaryAccount] = useState("");
  const [durationSeconds, setDurationSeconds] = useState("3600");
  const [telegramLabel, setTelegramLabel] = useState("Community Telegram");
  const [telegramToken, setTelegramToken] = useState("");
  const [whatsAppLabel, setWhatsAppLabel] = useState("Community WhatsApp");
  const [whatsAppGatewayAccountId, setWhatsAppGatewayAccountId] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const found = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        setWorkspace(found);
        const [integrations, loadedChannels] = await Promise.all([
          apiGet<Integration[]>(`/workspaces/${found.id}/integrations`),
          apiGet<CommunityChannel[]>(`/workspaces/${found.id}/community-channels`),
        ]);
        const google = integrations.find((item) => item.provider === "google_workspace") || null;
        const squad = integrations.find((item) => item.provider === "squad") || null;
        setGoogleIntegration(google);
        setSquadIntegration(squad);
        setFireflies(integrations.find((item) => item.provider === "fireflies") || null);
        setChannels(loadedChannels);
        setMerchantName(squad?.metadata?.merchant_name || "");
        setBeneficiaryAccount(squad?.metadata?.beneficiary_account || "");
        setDurationSeconds(squad?.metadata?.default_duration_seconds || "3600");
        const groupEntries = await Promise.all(
          loadedChannels.map(async (channel) => [
            channel.id,
            await apiGet<ChannelGroup[]>(`/workspaces/${found.id}/community-channels/${channel.id}/groups`),
          ]),
        );
        setGroupsByChannel(Object.fromEntries(groupEntries));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load integrations.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.workspaceSlug]);

  const needsGoogleReconnect = useMemo(
    () => googleIntegration?.status === "connected" && googleIntegration?.metadata?.gmail !== "available",
    [googleIntegration],
  );

  async function reloadChannels(currentWorkspace = workspace) {
    if (!currentWorkspace) {
      return;
    }
    const loadedChannels = await apiGet<CommunityChannel[]>(`/workspaces/${currentWorkspace.id}/community-channels`);
    setChannels(loadedChannels);
    const groupEntries = await Promise.all(
      loadedChannels.map(async (channel) => [
        channel.id,
        await apiGet<ChannelGroup[]>(`/workspaces/${currentWorkspace.id}/community-channels/${channel.id}/groups`),
      ]),
    );
    setGroupsByChannel(Object.fromEntries(groupEntries));
  }

  async function connectGoogle() {
    if (!workspace) {
      return;
    }
    setConnectingGoogle(true);
    setError(null);
    try {
      const result = await apiPost<{ authorization_url: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/integrations/google/oauth/start`,
        {},
      );
      window.location.href = result.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start Google connection.");
      setConnectingGoogle(false);
    }
  }

  async function disconnectGoogle() {
    if (!workspace) {
      return;
    }
    setConnectingGoogle(true);
    setError(null);
    try {
      await apiDelete(`/workspaces/${workspace.id}/integrations/google`);
      setGoogleIntegration((current) =>
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
      setConnectingGoogle(false);
    }
  }

  async function saveSquad() {
    if (!workspace) {
      return;
    }
    setSavingSquad(true);
    setError(null);
    try {
      const saved = await apiPost<Integration, { merchant_name?: string; beneficiary_account?: string; default_duration_seconds: number; collection_mode: string }>(
        `/workspaces/${workspace.id}/integrations/squad`,
        {
          merchant_name: merchantName.trim() || undefined,
          beneficiary_account: beneficiaryAccount.trim() || undefined,
          default_duration_seconds: Number(durationSeconds) || 3600,
          collection_mode: "dynamic_virtual_account",
        },
      );
      setSquadIntegration(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save Squad settings.");
    } finally {
      setSavingSquad(false);
    }
  }

  async function disconnectSquad() {
    if (!workspace) {
      return;
    }
    setSavingSquad(true);
    setError(null);
    try {
      await apiDelete(`/workspaces/${workspace.id}/integrations/squad`);
      setSquadIntegration({
        provider: "squad",
        status: "not_connected",
        configured: true,
        scopes: [],
        metadata: {},
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disconnect Squad.");
    } finally {
      setSavingSquad(false);
    }
  }

  async function connectTelegram() {
    if (!workspace) {
      return;
    }
    setSavingTelegram(true);
    setError(null);
    try {
      await apiPost<CommunityChannel, { label: string; bot_token: string }>(
        `/workspaces/${workspace.id}/community-channels/telegram`,
        { label: telegramLabel.trim(), bot_token: telegramToken.trim() },
      );
      setTelegramToken("");
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to configure Telegram.");
    } finally {
      setSavingTelegram(false);
    }
  }

  async function connectWhatsApp() {
    if (!workspace) {
      return;
    }
    setSavingWhatsApp(true);
    setError(null);
    try {
      await apiPost<CommunityChannel, { label: string; gateway_account_id?: string }>(
        `/workspaces/${workspace.id}/community-channels/whatsapp`,
        {
          label: whatsAppLabel.trim(),
          gateway_account_id: whatsAppGatewayAccountId.trim() || undefined,
        },
      );
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to prepare WhatsApp sync.");
    } finally {
      setSavingWhatsApp(false);
    }
  }

  async function disconnectChannel(channelId: number) {
    if (!workspace) {
      return;
    }
    setError(null);
    try {
      await apiDelete(`/workspaces/${workspace.id}/community-channels/${channelId}`);
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disconnect channel.");
    }
  }

  async function toggleGroupSync(channelId: number, groupId: number, syncEnabled: boolean) {
    if (!workspace) {
      return;
    }
    setError(null);
    try {
      const updated = await apiPatch<ChannelGroup, { sync_enabled: boolean }>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/groups/${groupId}`,
        { sync_enabled: syncEnabled },
      );
      setGroupsByChannel((current) => ({
        ...current,
        [channelId]: (current[channelId] || []).map((group) => (group.id === groupId ? updated : group)),
      }));
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update group sync.");
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
      <p className="status-note">For privacy, Quorum only stores and processes messages from groups you explicitly enable below. Unselected groups are discovered for approval and then ignored.</p>
      {error ? <p className="form-error">{error}</p> : null}

      <section className="content-grid">
        <article className="panel-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Squad</p>
              <h2>Collections and virtual accounts</h2>
            </div>
            <span className={`status-pill ${squadIntegration?.status === "connected" ? "ok" : "pending"}`}>
              {loading ? "Loading" : squadIntegration?.status === "connected" ? "Connected" : "Not connected"}
            </span>
          </div>
          <p>Squad is now the only payment rail in Quorum. Configure it once for the workspace and all dues and campaign collections will use Squad virtual accounts.</p>
          <div className="mini-list">
            <div>
              <span>Mode</span>
              <strong>{squadIntegration?.metadata?.collection_mode || "dynamic_virtual_account"}</strong>
            </div>
            <div>
              <span>Merchant</span>
              <strong>{squadIntegration?.metadata?.merchant_name || "Not set"}</strong>
            </div>
            <div>
              <span>Beneficiary account</span>
              <strong>{squadIntegration?.metadata?.beneficiary_account || "Not set"}</strong>
            </div>
            <div>
              <span>Expiry window</span>
              <strong>{squadIntegration?.metadata?.default_duration_seconds || "3600"}s</strong>
            </div>
          </div>
          <div className="form-stack">
            <label>
              Merchant label
              <input value={merchantName} onChange={(event) => setMerchantName(event.target.value)} placeholder="Quorum Cooperative Collections" />
            </label>
            <label>
              Beneficiary account
              <input value={beneficiaryAccount} onChange={(event) => setBeneficiaryAccount(event.target.value)} placeholder="0123456789" />
            </label>
            <label>
              Virtual account expiry (seconds)
              <input type="number" min="60" max="86400" value={durationSeconds} onChange={(event) => setDurationSeconds(event.target.value)} />
            </label>
          </div>
          <div className="page-actions">
            <button type="button" className="btn-primary" onClick={saveSquad} disabled={savingSquad || !squadIntegration?.configured}>
              {savingSquad ? "Saving..." : squadIntegration?.status === "connected" ? "Update Squad" : "Connect Squad"}
            </button>
            {squadIntegration?.status === "connected" ? (
              <button type="button" className="btn-secondary" onClick={disconnectSquad} disabled={savingSquad}>
                Disconnect
              </button>
            ) : null}
          </div>
          {!squadIntegration?.configured ? <p className="muted-copy">Set `SQUAD_SECRET_KEY` on the backend before connecting Squad.</p> : null}
        </article>

        <article className="panel-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Telegram</p>
              <h2>Selected-group sync</h2>
            </div>
            <span className="status-pill ok">{channels.filter((channel) => channel.provider === "telegram").length} connected</span>
          </div>
          <p>Connect a Telegram bot, add it to your community groups, and then enable only the groups Quorum should sync.</p>
          <div className="form-stack">
            <label>
              Channel label
              <input value={telegramLabel} onChange={(event) => setTelegramLabel(event.target.value)} />
            </label>
            <label>
              Bot token
              <input value={telegramToken} onChange={(event) => setTelegramToken(event.target.value)} placeholder="123456:ABC..." />
            </label>
          </div>
          <div className="page-actions">
            <button type="button" className="btn-primary" onClick={connectTelegram} disabled={savingTelegram || !telegramToken.trim()}>
              {savingTelegram ? "Connecting..." : "Connect Telegram"}
            </button>
          </div>
        </article>

        <article className="panel-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">WhatsApp</p>
              <h2>Gateway-selected groups</h2>
            </div>
            <span className="status-pill pending">{channels.filter((channel) => channel.provider === "whatsapp").length} prepared</span>
          </div>
          <p>Prepare a WhatsApp sync target here, then point the Baileys gateway at the generated inbound URL and secret. Quorum will only persist messages from groups you enable.</p>
          <div className="form-stack">
            <label>
              Channel label
              <input value={whatsAppLabel} onChange={(event) => setWhatsAppLabel(event.target.value)} />
            </label>
            <label>
              Gateway account id
              <input value={whatsAppGatewayAccountId} onChange={(event) => setWhatsAppGatewayAccountId(event.target.value)} placeholder="optional external account id" />
            </label>
          </div>
          <div className="page-actions">
            <button type="button" className="btn-primary" onClick={connectWhatsApp} disabled={savingWhatsApp}>
              {savingWhatsApp ? "Preparing..." : "Prepare WhatsApp"}
            </button>
          </div>
        </article>

        {channels.map((channel) => {
          const groups = groupsByChannel[channel.id] || [];
          return (
            <article className="panel-card" key={channel.id}>
              <div className="card-head">
                <div>
                  <p className="eyebrow">{channel.provider === "telegram" ? "Telegram" : "WhatsApp"}</p>
                  <h2>{channel.label}</h2>
                </div>
                <span className={`status-pill ${channel.status === "connected" ? "ok" : "pending"}`}>{channel.status}</span>
              </div>
              <div className="mini-list">
                <div>
                  <span>Inbound URL</span>
                  <strong>{String(channel.metadata.webhook_url || "-")}</strong>
                </div>
                {channel.provider === "telegram" ? (
                  <div>
                    <span>Bot</span>
                    <strong>{String(channel.metadata.bot_username || channel.metadata.display_name || "Unknown bot")}</strong>
                  </div>
                ) : (
                  <div>
                    <span>Gateway secret</span>
                    <strong>{String(channel.metadata.webhook_secret || "-")}</strong>
                  </div>
                )}
                <div>
                  <span>Groups discovered</span>
                  <strong>{String(channel.metadata.discovered_group_count || 0)}</strong>
                </div>
                <div>
                  <span>Groups syncing</span>
                  <strong>{String(channel.metadata.selected_group_count || 0)}</strong>
                </div>
              </div>
              {channel.metadata.last_error ? <p className="form-error">{String(channel.metadata.last_error)}</p> : null}
              <div className="page-actions">
                <button type="button" className="btn-secondary" onClick={() => disconnectChannel(channel.id)}>
                  Disconnect channel
                </button>
              </div>
              <div className="mini-list roomy">
                {groups.length === 0 ? (
                  <div>
                    <span>Groups</span>
                    <strong>No groups discovered yet. Add the bot or gateway account to the group first.</strong>
                  </div>
                ) : (
                  groups.map((group) => (
                    <div key={group.id}>
                      <span>{group.group_name}</span>
                      <strong>{group.message_count} synced messages</strong>
                      <button
                        type="button"
                        className={group.sync_enabled ? "btn-primary" : "btn-secondary"}
                        onClick={() => toggleGroupSync(channel.id, group.id, !group.sync_enabled)}
                      >
                        {group.sync_enabled ? "Sync enabled" : "Enable sync"}
                      </button>
                    </div>
                  ))
                )}
              </div>
            </article>
          );
        })}

        <article className="panel-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Google Workspace</p>
              <h2>Meet, Drive, and Gmail</h2>
            </div>
            <span className={`status-pill ${googleIntegration?.status === "connected" ? "ok" : "pending"}`}>
              {loading ? "Loading" : googleIntegration?.status === "connected" ? "Connected" : "Not connected"}
            </span>
          </div>
          <p>Connect a Google account once per workspace to create Meet links, sync transcripts, and send member invitations from the connected Gmail account.</p>
          <div className="mini-list">
            <div>
              <span>Account</span>
              <strong>{googleIntegration?.connected_email || "No account connected"}</strong>
            </div>
            <div>
              <span>Scopes</span>
              <strong>{googleIntegration?.scopes?.length ? googleIntegration.scopes.length : 0}</strong>
            </div>
            <div>
              <span>Connected at</span>
              <strong>{googleIntegration?.connected_at || "-"}</strong>
            </div>
            <div>
              <span>Invitations</span>
              <strong>{needsGoogleReconnect ? "Reconnect Google to grant Gmail sending" : googleIntegration?.metadata?.gmail === "available" ? "Send from Gmail" : "Waiting for Google connection"}</strong>
            </div>
          </div>
          {needsGoogleReconnect ? (
            <div className="status-note">
              This workspace was connected before Gmail sending was added. Reconnect Google once so Quorum can request the Gmail permission and send invitations from <strong>{googleIntegration?.connected_email}</strong>.
            </div>
          ) : null}
          <div className="page-actions">
            <button type="button" className="btn-primary" onClick={connectGoogle} disabled={connectingGoogle || !googleIntegration?.configured}>
              {connectingGoogle
                ? "Opening..."
                : needsGoogleReconnect
                  ? "Reconnect for Gmail"
                  : googleIntegration?.status === "connected"
                    ? "Reconnect Google"
                    : "Connect Google"}
            </button>
            {googleIntegration?.status === "connected" ? (
              <button type="button" className="btn-secondary" onClick={disconnectGoogle} disabled={connectingGoogle}>
                Disconnect
              </button>
            ) : null}
          </div>
          {!googleIntegration?.configured ? <p className="muted-copy">Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on the backend before connecting.</p> : null}
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
              <p className="eyebrow">Squad</p>
              <h2>Collections and virtual accounts</h2>
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
