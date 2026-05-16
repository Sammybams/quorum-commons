"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { apiDelete, apiGet, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Member = {
  id: number;
  workspace_id?: number;
  full_name: string;
  level?: string | null;
  email?: string | null;
  role: string;
  trade_category?: string | null;
  location?: string | null;
  languages?: string[];
  availability?: string | null;
  contribution_capacity?: string | null;
  dues_status?: string;
};
type Role = { id: number; name: string; key: string; is_system_role: boolean };
type Integration = {
  provider: string;
  status: string;
  configured: boolean;
  metadata: Record<string, string>;
};
type Invitation = {
  id: number;
  email: string;
  phone_number?: string | null;
  role_name: string;
  token: string;
  status: string;
  email_delivery_status?: string | null;
  email_delivery_provider?: string | null;
  email_delivery_sender?: string | null;
  expires_at?: string | null;
};
type InviteLink = { id: number; token: string; role_name: string; is_active: boolean };

export default function MembersClient({
  workspace,
  initialMembers,
}: {
  workspace: Workspace;
  initialMembers: Member[];
}) {
  const [members, setMembers] = useState(initialMembers);
  const [roles, setRoles] = useState<Role[]>([]);
  const [pendingInvitations, setPendingInvitations] = useState<Invitation[]>([]);
  const [inviteLinks, setInviteLinks] = useState<InviteLink[]>([]);
  const [googleIntegration, setGoogleIntegration] = useState<Integration | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [roleId, setRoleId] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [copiedInviteId, setCopiedInviteId] = useState<number | null>(null);
  const [removingInvitationId, setRemovingInvitationId] = useState<number | null>(null);

  useEffect(() => {
    async function loadInviteData() {
      try {
        const [loadedRoles, loadedInvitations, loadedInviteLinks] = await Promise.all([
          apiGet<Role[]>(`/workspaces/${workspace.id}/roles`),
          apiGet<Invitation[]>(`/workspaces/${workspace.id}/invitations`),
          apiGet<InviteLink[]>(`/workspaces/${workspace.id}/invite-links`),
        ]);
        setRoles(loadedRoles);
        setPendingInvitations(loadedInvitations);
        setInviteLinks(loadedInviteLinks);
        const coreRole = loadedRoles.find((item) => item.key === "member") || loadedRoles[0] || null;
        setRoleId(coreRole?.id || null);
        try {
          const loadedIntegrations = await apiGet<Integration[]>(`/workspaces/${workspace.id}/integrations`);
          setGoogleIntegration(loadedIntegrations.find((item) => item.provider === "google_workspace") || null);
        } catch {
          setGoogleIntegration(null);
        }
      } catch {
        // Role/invite loading requires a logged-in admin token; the page itself can still render read-only.
      }
    }

    loadInviteData();
  }, [workspace.id]);

  const inviteUrl = useMemo(() => {
    const token = inviteLinks.find((link) => link.is_active)?.token;
    if (!token) {
      return null;
    }
    if (typeof window === "undefined") {
      return `/join/${token}`;
    }
    return `${window.location.origin}/join/${token}`;
  }, [inviteLinks]);
  const selectedRole = useMemo(
    () => roles.find((item) => item.id === roleId) || null,
    [roleId, roles],
  );
  const googleConnected = googleIntegration?.status === "connected";
  const gmailReady = googleConnected && googleIntegration?.metadata?.gmail === "available";
  const visiblePendingInvitations = useMemo(
    () => pendingInvitations.filter((invitation) => invitation.status === "pending"),
    [pendingInvitations],
  );

  async function copyInviteLink() {
    if (!inviteUrl) {
      setError("Generate a bulk invite link before copying.");
      return;
    }
    await navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  function directInviteUrl(invitation: Invitation) {
    if (typeof window === "undefined") {
      return `/invites/${invitation.token}`;
    }
    return `${window.location.origin}/invites/${invitation.token}`;
  }

  async function copyDirectInvite(invitation: Invitation) {
    await navigator.clipboard.writeText(directInviteUrl(invitation));
    setCopiedInviteId(invitation.id);
    window.setTimeout(() => setCopiedInviteId(null), 1800);
  }

  async function reloadInvitations() {
    const [loadedInvitations, loadedInviteLinks] = await Promise.all([
      apiGet<Invitation[]>(`/workspaces/${workspace.id}/invitations`),
      apiGet<InviteLink[]>(`/workspaces/${workspace.id}/invite-links`),
    ]);
    setPendingInvitations(loadedInvitations);
    setInviteLinks(loadedInviteLinks);
  }

  async function createInviteLink() {
    if (!roleId) {
      setError("Select a role before creating an invite link.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const link = await apiPost<InviteLink, { role_id: number }>(`/workspaces/${workspace.id}/invite-links`, {
        role_id: roleId,
      });
      setInviteLinks((current) => [link, ...current.filter((item) => item.id !== link.id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create invite link.");
    } finally {
      setLoading(false);
    }
  }

  async function removeInvitation(invitationId: number) {
    setRemovingInvitationId(invitationId);
    setError(null);
    try {
      await apiDelete(`/workspaces/${workspace.id}/invitations/${invitationId}`);
      await reloadInvitations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove invitation.");
    } finally {
      setRemovingInvitationId(null);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!roleId) {
      setError("Select a role before sending an invitation.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const invitation = await apiPost<Invitation, { email: string; phone_number?: string; role_id: number; note?: string }>(
        `/workspaces/${workspace.id}/invitations`,
        {
          email: email.trim().toLowerCase(),
          phone_number: phoneNumber.trim() || undefined,
          role_id: roleId,
          note: note.trim() || undefined,
        },
      );

      setPendingInvitations((current) => [invitation, ...current]);
      setEmail("");
      setPhoneNumber("");
      setNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to send invitation.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Members</p>
          <h1>Member registry</h1>
          <p>
            {members.length} registered {members.length === 1 ? "member" : "members"}
          </p>
        </div>
        <div className="page-actions">
          {!gmailReady ? (
            <Link href={`/${workspace.slug}/settings/integrations`} className="btn-ghost">
              <span className="material-symbols-outlined" aria-hidden="true">
                hub
              </span>
              {googleConnected ? "Reconnect Google" : "Connect Google"}
            </Link>
          ) : null}
          <button type="button" className="btn-secondary" onClick={() => setInviteOpen(true)}>
            <span className="material-symbols-outlined" aria-hidden="true">
              person_add
            </span>
            Invite
          </button>
          <button type="button" className="btn-ghost">
            Export CSV
          </button>
        </div>
      </header>

      {visiblePendingInvitations.length > 0 ? (
        <section className="panel-card pending-invites-card">
          <div className="card-head compact">
            <div>
              <h2>Pending invitations</h2>
              <p>{visiblePendingInvitations.length} {visiblePendingInvitations.length === 1 ? "person has" : "people have"} not accepted yet.</p>
            </div>
            <div className="pending-invites-actions">
              {inviteUrl ? (
                <button type="button" className="btn-ghost" onClick={copyInviteLink}>
                  {copied ? "Copied" : "Copy link"}
                </button>
              ) : null}
              <button type="button" className="btn-secondary" onClick={() => setInviteOpen(true)}>
                Manage invites
              </button>
            </div>
          </div>
          <div className="pending-invite-list">
            {visiblePendingInvitations.map((invitation) => (
              <div className="pending-invite-row" key={invitation.id}>
                <div>
                  <strong>{invitation.email}</strong>
                  <span>
                    {invitation.role_name} · {deliveryLabel(invitation.email_delivery_status, invitation.email_delivery_provider, invitation.email_delivery_sender)}
                    {invitation.phone_number ? ` · WhatsApp ${invitation.phone_number}` : ""}
                    {invitation.expires_at ? ` · expires ${new Date(invitation.expires_at).toLocaleDateString()}` : ""}
                  </span>
                </div>
                <span className={`status-pill ${invitation.email_delivery_status === "sent" ? "ok" : "pending"}`}>
                  {invitation.status}
                </span>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => removeInvitation(invitation.id)}
                  disabled={removingInvitationId === invitation.id}
                >
                  {removingInvitationId === invitation.id ? "Removing..." : "Remove"}
                </button>
                <button type="button" className="btn-secondary" onClick={() => copyDirectInvite(invitation)}>
                  {copiedInviteId === invitation.id ? "Copied" : "Copy invite link"}
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel-card">
        {members.length === 0 ? (
          <div className="empty-state">
            <span className="material-symbols-outlined" aria-hidden="true">
              group
            </span>
            <h2>No members yet</h2>
            <p>Send an email invitation or create a bulk invite link for your community.</p>
            <button type="button" className="btn-primary" onClick={() => setInviteOpen(true)}>
              Invite first member
            </button>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Profile</th>
                  <th>Role</th>
                  <th>Readiness</th>
                  <th>Email</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <div className="member-name">
                        <span className="member-avatar">{initials(member.full_name)}</span>
                        <div>
                          <strong>{member.full_name}</strong>
                          {member.level ? <div>{member.level}</div> : null}
                        </div>
                      </div>
                    </td>
                    <td>
                      {member.trade_category || member.location || member.languages?.length ? (
                        <>
                          <div>{member.trade_category || "General member"}</div>
                          <small>{member.location || member.languages?.join(", ") || "-"}</small>
                        </>
                      ) : (
                        member.level || "-"
                      )}
                    </td>
                    <td>{member.role}</td>
                    <td>
                      <div>
                        <span className={`status-pill ${member.dues_status?.toLowerCase() === "paid" ? "ok" : "pending"}`}>
                          {member.dues_status || "Pending"}
                        </span>
                        {member.availability || member.contribution_capacity ? (
                          <small>{member.availability || member.contribution_capacity}</small>
                        ) : null}
                      </div>
                    </td>
                    <td>{member.email || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {inviteOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setInviteOpen(false)}>
          <section
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="invite-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="card-head compact">
              <div>
                <p className="eyebrow">Invite</p>
                <h2 id="invite-title">Invite members</h2>
              </div>
              <button type="button" className="icon-button" aria-label="Close invite modal" onClick={() => setInviteOpen(false)}>
                <span className="material-symbols-outlined" aria-hidden="true">
                  close
                </span>
              </button>
            </div>

            <div className="invite-link-box">
              <div className="invite-link-summary">
                <strong>{inviteUrl ? "Bulk invite link ready" : "No bulk invite link yet"}</strong>
                <span>{inviteUrl || "Generate a /join link for standard member onboarding."}</span>
                <small className="muted-copy">
                  {gmailReady
                    ? "Invite emails will send through the connected Gmail account."
                    : googleConnected
                      ? "Reconnect Google to enable Gmail invite sending."
                      : "Connect Google if you want invite emails sent through Gmail."}
                </small>
              </div>
              <div className="invite-link-actions">
                <Link href={`/${workspace.slug}/settings/integrations`} className="btn-ghost">
                  {gmailReady ? "Manage Google" : googleConnected ? "Reconnect Google" : "Connect Google"}
                </Link>
                <button type="button" className="btn-secondary" onClick={createInviteLink} disabled={loading || !roleId}>
                  {inviteUrl ? "Regenerate link" : "Generate link"}
                </button>
              </div>
            </div>

            <form className="form-stack" onSubmit={onSubmit}>
              <label>
                Email
                <input
                  type="email"
                  placeholder="jane@school.edu.ng"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </label>
              <label>
                Phone number
                <input
                  type="tel"
                  placeholder="+2348012345678"
                  value={phoneNumber}
                  onChange={(event) => setPhoneNumber(event.target.value)}
                />
                <small className="muted-copy">
                  Optional. If added, Quorum can send WhatsApp alerts for assigned tasks and matched opportunities.
                </small>
              </label>
              <label>
                Role
                <span className="select-shell">
                  <select value={roleId || ""} onChange={(event) => setRoleId(Number(event.target.value))}>
                    {roles.map((role) => (
                      <option key={role.id} value={role.id}>
                        {role.name}
                      </option>
                    ))}
                  </select>
                  <span className="material-symbols-outlined" aria-hidden="true">
                    expand_more
                  </span>
                </span>
                <small className="muted-copy">
                  {selectedRole?.key === "member"
                    ? "Use Member for standard access."
                    : "Use another role only for leads or admins."}
                </small>
              </label>
              <label>
                Personal note
                <textarea
                  rows={3}
                  placeholder="Optional message shown in the invitation email"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                />
              </label>

              {error ? <p className="form-error">{error}</p> : null}

              {visiblePendingInvitations.length > 0 ? (
                <div className="invite-modal-list">
                  {visiblePendingInvitations.slice(0, 4).map((invitation) => (
                    <div className="invite-modal-row" key={invitation.id}>
                      <div>
                        <span>{invitation.email}</span>
                        <strong>
                          {invitation.role_name} · {deliveryLabel(invitation.email_delivery_status, invitation.email_delivery_provider, invitation.email_delivery_sender)}
                          {invitation.phone_number ? ` · WhatsApp ${invitation.phone_number}` : ""}
                        </strong>
                      </div>
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => removeInvitation(invitation.id)}
                        disabled={removingInvitationId === invitation.id}
                      >
                        {removingInvitationId === invitation.id ? "Removing..." : "Remove"}
                      </button>
                      <button type="button" className="btn-secondary" onClick={() => copyDirectInvite(invitation)}>
                        {copiedInviteId === invitation.id ? "Copied" : "Copy link"}
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="form-actions">
                <button type="button" className="btn-ghost" onClick={() => setInviteOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={loading}>
                  {loading ? "Sending..." : "Send invitation"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function deliveryLabel(status?: string | null, provider?: string | null, sender?: string | null) {
  if (status === "sent") {
    if (provider === "google") {
      return sender ? `sent from Gmail (${sender})` : "sent from Gmail";
    }
    if (provider === "smtp_fallback") {
      return sender ? `sent by Quorum mail after Gmail fallback (${sender})` : "sent by Quorum mail after Gmail fallback";
    }
    return sender ? `sent by Quorum mail (${sender})` : "email sent";
  }
  if (status === "failed") {
    if (provider === "google") {
      return "Gmail send failed";
    }
    return "email failed";
  }
  if (status === "not_configured") {
    return "Google or SMTP delivery not configured";
  }
  return "email pending";
}

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
