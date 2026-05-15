"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api";
import { resolveWorkspace } from "@/lib/workspace-client";

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
type TelegramSetupStatus = {
  ready: boolean;
  missing_fields: string[];
  message: string;
  instructions_url?: string | null;
};

function formatChannelStatus(status: string) {
  return status.replaceAll("_", " ");
}

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
  const [telegramActionChannelId, setTelegramActionChannelId] = useState<number | null>(null);
  const [whatsAppActionChannelId, setWhatsAppActionChannelId] = useState<number | null>(null);
  const [telegramSetup, setTelegramSetup] = useState<TelegramSetupStatus | null>(null);
  const [merchantName, setMerchantName] = useState("");
  const [beneficiaryAccount, setBeneficiaryAccount] = useState("");
  const [durationSeconds, setDurationSeconds] = useState("3600");
  const [telegramLabel, setTelegramLabel] = useState("Community Telegram");
  const [telegramPhoneNumber, setTelegramPhoneNumber] = useState("");
  const [telegramCodes, setTelegramCodes] = useState<Record<number, string>>({});
  const [telegramPasswords, setTelegramPasswords] = useState<Record<number, string>>({});
  const [groupFilters, setGroupFilters] = useState<Record<number, string>>({});
  const [whatsAppLabel, setWhatsAppLabel] = useState("Community WhatsApp");

  useEffect(() => {
    async function load() {
      try {
        const found = await resolveWorkspace(params.workspaceSlug);
        setWorkspace(found);
        const [integrations, loadedChannels, telegramSetupStatus] = await Promise.all([
          apiGet<Integration[]>(`/workspaces/${found.id}/integrations`),
          apiGet<CommunityChannel[]>(`/workspaces/${found.id}/community-channels`),
          apiGet<TelegramSetupStatus>(`/workspaces/${found.id}/community-channels/telegram/setup-status`),
        ]);
        const google = integrations.find((item) => item.provider === "google_workspace") || null;
        const squad = integrations.find((item) => item.provider === "squad") || null;
        setGoogleIntegration(google);
        setSquadIntegration(squad);
        setFireflies(integrations.find((item) => item.provider === "fireflies") || null);
        setChannels(loadedChannels);
        setTelegramSetup(telegramSetupStatus);
        setMerchantName(squad?.metadata?.merchant_name || "");
        setBeneficiaryAccount(squad?.metadata?.beneficiary_account || "");
        setDurationSeconds(squad?.metadata?.default_duration_seconds || "3600");
        setGroupsByChannel({});
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load integrations.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.workspaceSlug]);

  useEffect(() => {
    if (!workspace) {
      return;
    }
    const shouldPollWhatsApp = channels.some(
      (channel) => channel.provider === "whatsapp" && ["connecting", "qr_pending"].includes(channel.status),
    );
    if (!shouldPollWhatsApp) {
      return;
    }
    const timer = window.setInterval(() => {
      reloadChannels(workspace, { includeGroups: false }).catch(() => {});
    }, 4000);
    return () => window.clearInterval(timer);
  }, [channels, workspace]);

  const needsGoogleReconnect = useMemo(
    () => googleIntegration?.status === "connected" && googleIntegration?.metadata?.gmail !== "available",
    [googleIntegration],
  );
  const telegramChannels = useMemo(() => channels.filter((channel) => channel.provider === "telegram"), [channels]);
  const whatsAppChannels = useMemo(() => channels.filter((channel) => channel.provider === "whatsapp"), [channels]);

  async function refreshChannelGroups(workspaceId: number, channelId: number) {
    const groups = await apiGet<ChannelGroup[]>(`/workspaces/${workspaceId}/community-channels/${channelId}/groups`);
    setGroupsByChannel((current) => ({ ...current, [channelId]: groups }));
  }

  async function ensureChannelGroups(channelId: number) {
    if (!workspace || groupsByChannel[channelId]) {
      return;
    }
    await refreshChannelGroups(workspace.id, channelId);
  }

  async function reloadChannels(currentWorkspace = workspace, options?: { includeGroups?: boolean }) {
    if (!currentWorkspace) {
      return;
    }
    const includeGroups = options?.includeGroups ?? true;
    const loadedChannels = await apiGet<CommunityChannel[]>(`/workspaces/${currentWorkspace.id}/community-channels`);
    setChannels(loadedChannels);
    if (!includeGroups) {
      setGroupsByChannel((current) =>
        Object.fromEntries(
          Object.entries(current).filter(([channelId]) => loadedChannels.some((channel) => channel.id === Number(channelId))),
        ),
      );
      return;
    }
    const channelIds = Object.keys(groupsByChannel).map(Number).filter((channelId) => loadedChannels.some((channel) => channel.id === channelId));
    const groupEntries = await Promise.all(
      channelIds.map(async (channelId) => [
        channelId,
        await apiGet<ChannelGroup[]>(`/workspaces/${currentWorkspace.id}/community-channels/${channelId}/groups`),
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
      await apiPost<CommunityChannel, { label: string; phone_number: string }>(
        `/workspaces/${workspace.id}/community-channels/telegram`,
        {
          label: telegramLabel.trim(),
          phone_number: telegramPhoneNumber.trim(),
        },
      );
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to configure Telegram.");
    } finally {
      setSavingTelegram(false);
    }
  }

  async function startTelegramLogin(channelId: number) {
    if (!workspace) {
      return;
    }
    setTelegramActionChannelId(channelId);
    setError(null);
    try {
      await apiPost<{ ok: boolean; message: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/telegram/session/start`,
        {},
      );
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start Telegram login.");
    } finally {
      setTelegramActionChannelId(null);
    }
  }

  async function completeTelegramLogin(channelId: number) {
    if (!workspace) {
      return;
    }
    setTelegramActionChannelId(channelId);
    setError(null);
    try {
      await apiPost<CommunityChannel, { code: string; password?: string }>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/telegram/session/complete`,
        {
          code: (telegramCodes[channelId] || "").trim(),
          password: (telegramPasswords[channelId] || "").trim() || undefined,
        },
      );
      setTelegramCodes((current) => ({ ...current, [channelId]: "" }));
      setTelegramPasswords((current) => ({ ...current, [channelId]: "" }));
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to complete Telegram login.");
    } finally {
      setTelegramActionChannelId(null);
    }
  }

  async function discoverTelegramGroups(channelId: number) {
    if (!workspace) {
      return;
    }
    setTelegramActionChannelId(channelId);
    setError(null);
    try {
      await apiPost<{ ok: boolean; message: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/telegram/discover-groups`,
        {},
      );
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh Telegram groups.");
    } finally {
      setTelegramActionChannelId(null);
    }
  }

  async function syncTelegramChannel(channelId: number) {
    if (!workspace) {
      return;
    }
    setTelegramActionChannelId(channelId);
    setError(null);
    try {
      await apiPost<{ ok: boolean; message: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/telegram/sync`,
        {},
      );
      await reloadChannels(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sync Telegram messages.");
    } finally {
      setTelegramActionChannelId(null);
    }
  }

  async function connectWhatsApp() {
    if (!workspace) {
      return;
    }
    const normalizedLabel = whatsAppLabel.trim().toLowerCase();
    if (whatsAppChannels.some((channel) => channel.label.trim().toLowerCase() === normalizedLabel)) {
      setError("A WhatsApp source with this label already exists.");
      return;
    }
    setSavingWhatsApp(true);
    setError(null);
    try {
      await apiPost<CommunityChannel, { label: string }>(
        `/workspaces/${workspace.id}/community-channels/whatsapp`,
        {
          label: whatsAppLabel.trim(),
        },
      );
      await reloadChannels(workspace, { includeGroups: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to prepare WhatsApp sync.");
    } finally {
      setSavingWhatsApp(false);
    }
  }

  async function startWhatsAppSession(channelId: number) {
    if (!workspace) {
      return;
    }
    setWhatsAppActionChannelId(channelId);
    setError(null);
    try {
      await apiPost<CommunityChannel, Record<string, never>>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/whatsapp/session/start`,
        {},
      );
      await reloadChannels(workspace, { includeGroups: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start WhatsApp connection.");
    } finally {
      setWhatsAppActionChannelId(null);
    }
  }

  async function refreshWhatsAppSession(channelId: number) {
    if (!workspace) {
      return;
    }
    setWhatsAppActionChannelId(channelId);
    setError(null);
    try {
      await apiGet<CommunityChannel>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/whatsapp/session/status`,
      );
      await reloadChannels(workspace, { includeGroups: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh WhatsApp status.");
    } finally {
      setWhatsAppActionChannelId(null);
    }
  }

  async function discoverWhatsAppGroups(channelId: number) {
    if (!workspace) {
      return;
    }
    setWhatsAppActionChannelId(channelId);
    setError(null);
    try {
      await apiPost<{ ok: boolean; message: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/whatsapp/discover-groups`,
        {},
      );
      await reloadChannels(workspace, { includeGroups: false });
      await refreshChannelGroups(workspace.id, channelId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh WhatsApp groups.");
    } finally {
      setWhatsAppActionChannelId(null);
    }
  }

  async function syncWhatsAppChannel(channelId: number) {
    if (!workspace) {
      return;
    }
    setWhatsAppActionChannelId(channelId);
    setError(null);
    try {
      await apiPost<{ ok: boolean; message: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/whatsapp/sync`,
        {},
      );
      await reloadChannels(workspace, { includeGroups: false });
      await refreshChannelGroups(workspace.id, channelId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to import WhatsApp history.");
    } finally {
      setWhatsAppActionChannelId(null);
    }
  }

  async function disconnectWhatsAppSession(channelId: number) {
    if (!workspace) {
      return;
    }
    setWhatsAppActionChannelId(channelId);
    setError(null);
    try {
      await apiPost<{ ok: boolean; message: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/community-channels/${channelId}/whatsapp/session/disconnect`,
        {},
      );
      await reloadChannels(workspace, { includeGroups: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disconnect WhatsApp session.");
    } finally {
      setWhatsAppActionChannelId(null);
    }
  }

  async function disconnectChannel(channelId: number) {
    if (!workspace) {
      return;
    }
    setError(null);
    try {
      await apiDelete(`/workspaces/${workspace.id}/community-channels/${channelId}`);
      await reloadChannels(workspace, { includeGroups: false });
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
      await reloadChannels(workspace, { includeGroups: false });
      const channel = channels.find((item) => item.id === channelId)
      if (syncEnabled && channel?.provider === "whatsapp" && channel.status === "connected") {
        await syncWhatsAppChannel(channelId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update group sync.");
    }
  }

  function renderChannelCard(channel: CommunityChannel) {
    const groupsLoaded = Array.isArray(groupsByChannel[channel.id]);
    const groups = groupsByChannel[channel.id] || [];
    const selectedGroups = groups.filter((group) => group.sync_enabled);
    const discoverableGroups = groups.filter((group) => !group.sync_enabled);
    const groupFilter = (groupFilters[channel.id] || "").trim().toLowerCase();
    const filteredDiscoverableGroups = discoverableGroups.filter((group) =>
      group.group_name.toLowerCase().includes(groupFilter),
    );
    const statusTone = channel.status === "connected" ? "ok" : channel.status === "error" ? "danger" : "pending";

    return (
      <article className="panel-card integration-channel-card" key={channel.id}>
        <div className="card-head">
          <div>
            <p className="eyebrow">{channel.provider === "telegram" ? "Telegram" : "WhatsApp"}</p>
            <h2>{channel.label}</h2>
          </div>
          <span className={`status-pill ${statusTone}`}>{formatChannelStatus(channel.status)}</span>
        </div>
        <div className="integration-summary-grid">
          {channel.provider === "telegram" ? (
            <div className="integration-summary-item">
              <span>Account</span>
              <strong>{String(channel.metadata.telegram_username || channel.metadata.display_name || channel.metadata.phone_number || "Not connected")}</strong>
            </div>
          ) : (
            <div className="integration-summary-item">
              <span>Account</span>
              <strong>{String(channel.metadata.display_name || channel.metadata.phone_number || channel.metadata.whatsapp_jid || "Waiting for QR connection")}</strong>
            </div>
          )}
          <div className="integration-summary-item">
            <span>Groups discovered</span>
            <strong>{String(channel.metadata.discovered_group_count || 0)}</strong>
          </div>
          <div className="integration-summary-item">
            <span>Groups syncing</span>
            <strong>{String(channel.metadata.selected_group_count || 0)}</strong>
          </div>
          {channel.provider === "whatsapp" ? (
            <div className="integration-summary-item">
              <span>Connection</span>
              <strong>{channel.status === "connected" ? "Connected" : channel.status === "qr_pending" ? "Waiting for QR scan" : "Not connected"}</strong>
            </div>
          ) : null}
        </div>
        {channel.metadata.last_error ? <p className="form-error">{String(channel.metadata.last_error)}</p> : null}
        {channel.provider === "telegram" ? (
          <div className="integration-inline-auth">
            <label>
              Telegram code
              <input
                value={telegramCodes[channel.id] || ""}
                onChange={(event) => setTelegramCodes((current) => ({ ...current, [channel.id]: event.target.value }))}
                placeholder="Code from Telegram"
              />
            </label>
            <label>
              Two-step password
              <input
                value={telegramPasswords[channel.id] || ""}
                onChange={(event) => setTelegramPasswords((current) => ({ ...current, [channel.id]: event.target.value }))}
                placeholder="Optional unless Telegram asks for it"
              />
            </label>
          </div>
        ) : null}
        {channel.provider === "whatsapp" ? (
          <p className="muted-copy integration-inline-note">
            Scan the QR with the WhatsApp account for this workspace, choose the groups to watch, then import recent messages once after enabling a group.
          </p>
        ) : null}
        {channel.provider === "whatsapp" && typeof channel.metadata.qr_code_data_url === "string" && channel.metadata.qr_code_data_url ? (
          <div className="whatsapp-qr-panel">
            <img src={String(channel.metadata.qr_code_data_url)} alt="WhatsApp QR code" className="whatsapp-qr-image" />
            <p className="muted-copy">Scan this QR with the WhatsApp account you want this workspace to use.</p>
          </div>
        ) : null}
        <div className="integration-toolbar">
          {channel.provider === "telegram" ? (
            <>
              <button
                type="button"
                className="btn-primary"
                onClick={() => startTelegramLogin(channel.id)}
                disabled={telegramActionChannelId === channel.id}
              >
                {telegramActionChannelId === channel.id ? "Working..." : "Send login code"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => completeTelegramLogin(channel.id)}
                disabled={telegramActionChannelId === channel.id || !(telegramCodes[channel.id] || "").trim()}
              >
                Complete login
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => discoverTelegramGroups(channel.id)}
                disabled={telegramActionChannelId === channel.id || channel.status !== "connected"}
              >
                Refresh groups
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => syncTelegramChannel(channel.id)}
                disabled={telegramActionChannelId === channel.id || channel.status !== "connected"}
              >
                Sync enabled groups
              </button>
            </>
          ) : null}
          {channel.provider === "whatsapp" ? (
            <>
              <button
                type="button"
                className="btn-primary"
                onClick={() => startWhatsAppSession(channel.id)}
                disabled={whatsAppActionChannelId === channel.id}
              >
                {whatsAppActionChannelId === channel.id ? "Working..." : channel.status === "connected" ? "Reconnect WhatsApp" : "Connect WhatsApp"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => refreshWhatsAppSession(channel.id)}
                disabled={whatsAppActionChannelId === channel.id}
              >
                Refresh status
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => discoverWhatsAppGroups(channel.id)}
                disabled={whatsAppActionChannelId === channel.id || channel.status !== "connected"}
              >
                Refresh groups
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => syncWhatsAppChannel(channel.id)}
                disabled={whatsAppActionChannelId === channel.id || channel.status !== "connected" || selectedGroups.length === 0}
              >
                Import recent messages
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => disconnectWhatsAppSession(channel.id)}
                disabled={whatsAppActionChannelId === channel.id || channel.status === "configured"}
              >
                Disconnect session
              </button>
            </>
          ) : null}
          <button type="button" className="btn-secondary" onClick={() => disconnectChannel(channel.id)}>
            Remove channel
          </button>
        </div>
        {!groupsLoaded ? (
          <div className="integration-empty-state">
            <p>
              Group lists are loaded on demand for this source so the Integrations page stays fast.
            </p>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => ensureChannelGroups(channel.id)}
              disabled={channel.provider === "whatsapp" && channel.status !== "connected"}
            >
              Load groups
            </button>
          </div>
        ) : groups.length === 0 ? (
          <div className="integration-empty-state">
            {channel.provider === "telegram"
              ? "No groups discovered yet. Complete login, then refresh groups."
              : channel.status === "connected"
                ? "No groups discovered yet. Refresh groups after the connected account has joined the target WhatsApp groups."
                : "Connect WhatsApp first, then refresh groups once the account has joined the target groups."}
          </div>
        ) : (
          <div className="group-picker-layout">
            <div className="group-picker-selected">
              <div className="group-picker-head">
                <strong>Selected groups</strong>
                <span>{selectedGroups.length}</span>
              </div>
              {channel.provider === "whatsapp" ? (
                <p className="muted-copy">New messages in selected groups are monitored live. Older chat messages are imported when you run the history import.</p>
              ) : null}
              {selectedGroups.length ? (
                <div className="group-chip-list">
                  {selectedGroups.map((group) => (
                    <button
                      key={group.id}
                      type="button"
                      className="group-chip"
                      onClick={() => toggleGroupSync(channel.id, group.id, false)}
                    >
                      <span>{group.group_name}</span>
                      <small>{group.message_count} synced messages</small>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="muted-copy">No groups enabled yet.</p>
              )}
            </div>

            <details className="group-picker">
              <summary>
                <span>Choose groups to sync</span>
                <small>{discoverableGroups.length} available</small>
              </summary>
              <div className="group-picker-panel">
                <label className="group-search">
                  <span>Find a group</span>
                  <input
                    value={groupFilters[channel.id] || ""}
                    onChange={(event) => setGroupFilters((current) => ({ ...current, [channel.id]: event.target.value }))}
                    placeholder="Search discovered groups"
                  />
                </label>
                <div className="group-picker-list">
                  {filteredDiscoverableGroups.length ? (
                    filteredDiscoverableGroups.map((group) => (
                      <button
                        key={group.id}
                        type="button"
                        className="group-picker-row"
                        onClick={() => toggleGroupSync(channel.id, group.id, true)}
                      >
                        <div>
                          <strong>{group.group_name}</strong>
                          <span>{group.message_count} synced messages</span>
                        </div>
                        <small>Add</small>
                      </button>
                    ))
                  ) : (
                    <p className="muted-copy">No groups match this search.</p>
                  )}
                </div>
              </div>
            </details>
          </div>
        )}
      </article>
    );
  }

  return (
    <section className="page-stack integrations-page">
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

      <section className="integrations-columns">
        <div className="side-stack">
        <article className="panel-card integrations-setup-card">
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

        <article className="panel-card integrations-setup-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">WhatsApp</p>
              <h2>{whatsAppChannels.length ? "Add another WhatsApp account" : "Add a WhatsApp account"}</h2>
            </div>
            <span className="status-pill pending">{whatsAppChannels.length} source{whatsAppChannels.length === 1 ? "" : "s"}</span>
          </div>
          <p>Create a WhatsApp source for this workspace. Each source links one WhatsApp account and the specific groups that account should sync into Quorum.</p>
          <div className="form-stack">
            <label>
              Channel label
              <input value={whatsAppLabel} onChange={(event) => setWhatsAppLabel(event.target.value)} />
            </label>
          </div>
          <div className="page-actions">
            <button type="button" className="btn-primary" onClick={connectWhatsApp} disabled={savingWhatsApp}>
              {savingWhatsApp ? "Creating..." : "Create WhatsApp source"}
            </button>
          </div>
        </article>

        {whatsAppChannels.map(renderChannelCard)}

        <article className="panel-card integrations-setup-card">
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
        </div>

        <div className="side-stack">
        <article className="panel-card integrations-setup-card">
          <div className="card-head">
            <div>
              <p className="eyebrow">Telegram</p>
              <h2>{telegramChannels.length ? "Add another Telegram account" : "Selected-group sync"}</h2>
            </div>
            <span className="status-pill ok">{telegramChannels.length} connected</span>
          </div>
          <p>{telegramChannels.length ? "Add a separate Telegram account if this workspace needs another source of group messages." : "Connect a Telegram account, discover its groups, then choose only the ones Quorum should sync."}</p>
          {telegramSetup && telegramSetup.ready === false ? <div className="status-note">{telegramSetup.message}</div> : null}
          <div className="form-stack">
            <label>
              Channel label
              <input value={telegramLabel} onChange={(event) => setTelegramLabel(event.target.value)} />
            </label>
            <label>
              Phone number
              <input value={telegramPhoneNumber} onChange={(event) => setTelegramPhoneNumber(event.target.value)} placeholder="+2348012345678" />
            </label>
          </div>
          <div className="page-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={connectTelegram}
              disabled={savingTelegram || telegramSetup?.ready === false || !telegramPhoneNumber.trim()}
            >
              {savingTelegram ? "Saving..." : "Save Telegram account"}
            </button>
          </div>
          {telegramSetup?.ready === false ? (
            <p className="muted-copy">
              Backend owner action needed: add {telegramSetup.missing_fields.join(", ")} to the backend environment, then reload this page.
            </p>
          ) : (
            <p className="muted-copy integration-hint">Save the number, then use the Telegram card below to finish sign-in.</p>
          )}
        </article>

        {telegramChannels.map(renderChannelCard)}

        <article className="panel-card integrations-setup-card">
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
        </div>
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
