"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { apiGet, apiPatch, apiPost } from "@/lib/api";

type Workspace = { id: number; name: string; slug: string; description?: string };
type Member = { id: number; full_name: string; email?: string | null; role: string };
type Role = { id: number; name: string; key: string };

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export default function WorkspaceSettingsPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [members, setMembers] = useState<Member[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [targetMemberId, setTargetMemberId] = useState<number | null>(null);
  const [fallbackRoleId, setFallbackRoleId] = useState<number | null>(null);
  const [confirmPassword, setConfirmPassword] = useState("");
  const [transferLoading, setTransferLoading] = useState(false);
  const [transferMessage, setTransferMessage] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const found = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        setWorkspace(found);
        setName(found.name);
        setSlug(found.slug);
        setDescription(found.description || "");
        const [loadedMembers, loadedRoles] = await Promise.all([
          apiGet<Member[]>(`/workspaces/${found.id}/members`),
          apiGet<Role[]>(`/workspaces/${found.id}/roles`),
        ]);
        setMembers(loadedMembers);
        setRoles(loadedRoles);
        setTargetMemberId(loadedMembers[0]?.id || null);
        const fallback = loadedRoles.find((role) => role.key === "secretary") || loadedRoles.find((role) => role.key === "core_member") || loadedRoles[0] || null;
        setFallbackRoleId(fallback?.id || null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load workspace.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.workspaceSlug]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace) {
      return;
    }

    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const updated = await apiPatch<Workspace, { name: string; slug: string; description?: string }>(
        `/workspaces/${workspace.id}`,
        {
          name,
          slug: slugify(slug),
          description,
        },
      );
      setWorkspace(updated);
      setName(updated.name);
      setSlug(updated.slug);
      setDescription(updated.description || "");
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save workspace.");
    } finally {
      setSaving(false);
    }
  }

  async function transferOwnership(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !targetMemberId) {
      return;
    }
    setTransferLoading(true);
    setTransferMessage(null);
    setError(null);
    try {
      const response = await apiPost<{ message: string }, { target_member_id: number; password: string; fallback_role_id?: number }>(
        `/workspaces/${workspace.id}/transfer-ownership`,
        {
          target_member_id: targetMemberId,
          password: confirmPassword,
          fallback_role_id: fallbackRoleId || undefined,
        },
      );
      setTransferMessage(response.message);
      setConfirmPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to transfer ownership.");
    } finally {
      setTransferLoading(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Workspace settings</h1>
          <p>Manage the public identity and URL for this student body.</p>
        </div>
        <div className="page-actions">
          <Link href={`/${params.workspaceSlug}/settings/integrations`} className="btn-secondary">
            Integrations
          </Link>
          <Link href={`/${params.workspaceSlug}/settings/roles`} className="btn-secondary">
            Roles & permissions
          </Link>
        </div>
      </header>

      <section className="content-grid">
        <article className="panel-card">
          <h2>Workspace profile</h2>
          <form className="form-stack" onSubmit={save}>
            <label>
              Workspace name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              Workspace slug
              <span className="slug-field">
                <span>quorum.ng/</span>
                <input value={slug} onChange={(event) => setSlug(slugify(event.target.value))} required />
              </span>
            </label>
            <label>
              Portal tagline / description
              <textarea rows={4} value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            {error ? <p className="form-error">{error}</p> : null}
            {saved ? <p className="status-note">Workspace settings saved.</p> : null}
            <button type="submit" className="btn-primary" disabled={saving || loading}>
              {saving ? "Saving..." : "Save settings"}
            </button>
          </form>
        </article>

        <article className="panel-card">
          <p className="eyebrow">Public portal</p>
          <h2>{name || "Workspace name"}</h2>
          <p>{description || "Your public portal tagline will appear here."}</p>
          <div className="portal-preview">quorum.ng/{slug || "workspace"}</div>
        </article>

        <article className="panel-card">
          <p className="eyebrow">Ownership</p>
          <h2>Transfer workspace ownership</h2>
          <p>Move the owner role to another active member when leadership changes.</p>
          <form className="form-stack" onSubmit={transferOwnership}>
            <label>
              New owner
              <span className="select-shell">
                <select value={targetMemberId || ""} onChange={(event) => setTargetMemberId(Number(event.target.value))} required>
                  {members.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.full_name} · {member.role}
                    </option>
                  ))}
                </select>
                <span className="material-symbols-outlined" aria-hidden="true">
                  expand_more
                </span>
              </span>
            </label>
            <label>
              Your fallback role
              <span className="select-shell">
                <select value={fallbackRoleId || ""} onChange={(event) => setFallbackRoleId(Number(event.target.value))}>
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
            </label>
            <label>
              Confirm your password
              <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
            </label>
            {transferMessage ? <p className="status-note">{transferMessage}</p> : null}
            <button type="submit" className="btn-primary" disabled={transferLoading || !workspace}>
              {transferLoading ? "Transferring..." : "Transfer ownership"}
            </button>
          </form>
        </article>
      </section>
    </section>
  );
}
