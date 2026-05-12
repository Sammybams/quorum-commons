"use client";

import { FormEvent, useState } from "react";
import { useEffect } from "react";

import { apiGet, apiPatch, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Role = { id: number; name: string };
type Announcement = {
  id: number;
  workspace_id: number;
  title: string;
  body: string;
  status: string;
  is_pinned: boolean;
  published_at: string | null;
  scheduled_for?: string | null;
  delivered_at?: string | null;
  delivery_count?: number;
  audience?: string;
  channels?: string[];
  target_role_ids?: number[];
  target_levels?: string[];
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export default function AnnouncementsClient({
  workspace,
  initialAnnouncements,
}: {
  workspace: Workspace;
  initialAnnouncements: Announcement[];
}) {
  const [announcements, setAnnouncements] = useState(initialAnnouncements);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [isPinned, setIsPinned] = useState(false);
  const [status, setStatus] = useState("published");
  const [scheduledFor, setScheduledFor] = useState("");
  const [audience, setAudience] = useState("all_members");
  const [channels, setChannels] = useState<string[]>(["in_app"]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);
  const [targetLevels, setTargetLevels] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadRoles() {
      try {
        setRoles(await apiGet<Role[]>(`/workspaces/${workspace.id}/roles`));
      } catch {
        // The announcement list can still function without role targeting metadata.
      }
    }
    loadRoles();
  }, [workspace.id]);

  async function publishAnnouncement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const announcement = await apiPost<
        Announcement,
        {
          title: string;
          body: string;
          status: string;
          is_pinned: boolean;
          scheduled_for?: string;
          audience: string;
          channels: string[];
          target_role_ids: number[];
          target_levels: string[];
        }
      >(`/workspaces/${workspace.id}/announcements`, {
        title: title.trim(),
        body: body.trim(),
        status,
        is_pinned: isPinned,
        scheduled_for: scheduledFor ? new Date(scheduledFor).toISOString() : undefined,
        audience,
        channels,
        target_role_ids: selectedRoleIds,
        target_levels: targetLevels
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      });
      setAnnouncements((current) => [announcement, ...current]);
      setTitle("");
      setBody("");
      setIsPinned(false);
      setStatus("published");
      setScheduledFor("");
      setAudience("all_members");
      setChannels(["in_app"]);
      setSelectedRoleIds([]);
      setTargetLevels("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to publish announcement.");
    } finally {
      setLoading(false);
    }
  }

  async function updateAnnouncement(announcementId: number, payload: Partial<Announcement>) {
    setLoading(true);
    setError(null);

    try {
      const updated = await apiPatch<Announcement, Partial<Announcement>>(
        `/workspaces/${workspace.id}/announcements/${announcementId}`,
        payload,
      );
      setAnnouncements((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update announcement.");
    } finally {
      setLoading(false);
    }
  }

  async function processScheduled() {
    setLoading(true);
    setError(null);
    try {
      await apiPost<{ message: string }, Record<string, never>>(`/workspaces/${workspace.id}/announcements/process-scheduled`, {});
      setAnnouncements(await apiGet<Announcement[]>(`/workspaces/${workspace.id}/announcements`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to process scheduled announcements.");
    } finally {
      setLoading(false);
    }
  }

  function toggleChannel(channel: string, checked: boolean) {
    setChannels((current) => {
      if (checked) {
        return current.includes(channel) ? current : [...current, channel];
      }
      const next = current.filter((item) => item !== channel);
      return next.length ? next : ["in_app"];
    });
  }

  function toggleRole(roleId: number, checked: boolean) {
    setSelectedRoleIds((current) => (checked ? [...current, roleId] : current.filter((item) => item !== roleId)));
  }

  const visibleAnnouncements = announcements.filter((announcement) => announcement.status !== "archived");
  const archivedCount = announcements.length - visibleAnnouncements.length;

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Announcements</p>
          <h1>Member updates</h1>
          <p>
            {workspace.name} · {visibleAnnouncements.length} visible · {archivedCount} archived
          </p>
        </div>
        <button type="button" className="btn-secondary" onClick={processScheduled} disabled={loading}>
          Process scheduled
        </button>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="content-grid">
        <article className="panel-card">
          <div className="card-head compact">
            <h2>Published feed</h2>
            <span className="status-pill">{visibleAnnouncements.length} updates</span>
          </div>
          {visibleAnnouncements.length === 0 ? (
            <div className="empty-state">
              <span className="material-symbols-outlined" aria-hidden="true">
                campaign
              </span>
              <h2>No announcements yet</h2>
              <p>Publish a member update and it will appear on the dashboard and public portal.</p>
            </div>
          ) : (
            <div className="activity-list">
              {visibleAnnouncements.map((announcement) => (
                <div key={announcement.id} className="activity-item">
                  <div>
                    <h3>{announcement.title}</h3>
                    <p>{announcement.body}</p>
                    <p className="muted-copy">
                      Audience: {(announcement.audience || "all_members").replaceAll("_", " ")} · Delivered: {announcement.delivery_count || 0}
                    </p>
                  </div>
                  <div className="activity-meta">
                    <span>{announcement.is_pinned ? "Pinned" : announcement.status}</span>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={loading}
                      onClick={() =>
                        updateAnnouncement(announcement.id, { is_pinned: !announcement.is_pinned })
                      }
                    >
                      {announcement.is_pinned ? "Unpin" : "Pin"}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      disabled={loading}
                      onClick={() => updateAnnouncement(announcement.id, { status: "archived" })}
                    >
                      Archive
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <aside className="panel-card">
          <div className="card-head compact">
            <h2>New announcement</h2>
          </div>
          <form className="form-stack" onSubmit={publishAnnouncement}>
            <label>
              Title
              <input value={title} onChange={(event) => setTitle(event.target.value)} required />
            </label>
            <label>
              Body
              <textarea value={body} onChange={(event) => setBody(event.target.value)} required />
            </label>
            <label>
              Status
              <span className="select-shell">
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="published">Publish now</option>
                  <option value="scheduled">Schedule</option>
                  <option value="draft">Save draft</option>
                </select>
                <span className="material-symbols-outlined" aria-hidden="true">
                  expand_more
                </span>
              </span>
            </label>
            {status === "scheduled" ? (
              <label>
                Scheduled for
                <input type="datetime-local" value={scheduledFor} onChange={(event) => setScheduledFor(event.target.value)} required />
              </label>
            ) : null}
            <label>
              Audience
              <span className="select-shell">
                <select value={audience} onChange={(event) => setAudience(event.target.value)}>
                  <option value="all_members">All members</option>
                  <option value="admins">Admins only</option>
                  <option value="general_members">General members</option>
                  <option value="paid_members">Paid members</option>
                  <option value="dues_defaulters">Dues defaulters</option>
                  <option value="roles">Specific roles</option>
                  <option value="levels">Specific levels</option>
                </select>
                <span className="material-symbols-outlined" aria-hidden="true">
                  expand_more
                </span>
              </span>
            </label>
            {audience === "roles" && roles.length ? (
              <div className="inline-checkbox-grid">
                {roles.map((role) => (
                  <label key={role.id} className="checkbox-row">
                    <input type="checkbox" checked={selectedRoleIds.includes(role.id)} onChange={(event) => toggleRole(role.id, event.target.checked)} />
                    {role.name}
                  </label>
                ))}
              </div>
            ) : null}
            {audience === "levels" ? (
              <label>
                Levels
                <input value={targetLevels} onChange={(event) => setTargetLevels(event.target.value)} placeholder="100, 200, 300 level" />
              </label>
            ) : null}
            <div className="inline-checkbox-grid">
              <label className="checkbox-row">
                <input type="checkbox" checked={channels.includes("in_app")} onChange={(event) => toggleChannel("in_app", event.target.checked)} />
                In-app
              </label>
              <label className="checkbox-row">
                <input type="checkbox" checked={channels.includes("email")} onChange={(event) => toggleChannel("email", event.target.checked)} />
                Email
              </label>
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={isPinned}
                onChange={(event) => setIsPinned(event.target.checked)}
              />
              Pin on dashboard and portal
            </label>
            <button type="submit" className="btn-primary" disabled={loading}>
              {status === "scheduled" ? "Schedule" : status === "draft" ? "Save draft" : "Publish"}
            </button>
          </form>
        </aside>
      </section>
    </section>
  );
}
