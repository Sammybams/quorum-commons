"use client";

import { FormEvent, useEffect, useState } from "react";

import { apiGet, apiPatch, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Role = {
  id: number;
  workspace_id: number;
  key: string;
  name: string;
  description?: string;
  is_system_role: boolean;
  permissions: string[];
};

const permissionGroups: Array<[string, string[]]> = [
  ["Members", ["members.view", "members.invite", "members.edit", "members.remove"]],
  ["Dues", ["dues.view", "dues.manage", "dues.confirm_payment"]],
  ["Events", ["events.view", "events.manage", "events.attendance"]],
  ["Meetings", ["meetings.view", "meetings.manage", "meetings.publish_minutes"]],
  ["Campaigns", ["campaigns.view", "campaigns.manage", "campaigns.confirm_contribution"]],
  ["Reports", ["reports.view", "reports.generate"]],
  ["Platform", ["dashboard.view", "settings.view", "settings.edit", "roles.manage", "integrations.manage", "billing.manage"]],
];

export default function RolesPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [permissions, setPermissions] = useState<string[]>(["dashboard.view"]);
  const [editingRole, setEditingRole] = useState<Role | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const foundWorkspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        const foundRoles = await apiGet<Role[]>(`/workspaces/${foundWorkspace.id}/roles`);
        setWorkspace(foundWorkspace);
        setRoles(foundRoles);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load roles.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.workspaceSlug]);

  async function createRole(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace) {
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const role = await apiPost<Role, { name: string; description?: string; permissions: string[] }>(
        `/workspaces/${workspace.id}/roles`,
        {
          name,
          description: description || undefined,
          permissions,
        },
      );
      setRoles((current) => [...current, role]);
      setName("");
      setDescription("");
      setPermissions(["dashboard.view"]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create role.");
    } finally {
      setSaving(false);
    }
  }

  async function saveRole(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !editingRole) {
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const role = await apiPatch<Role, { name: string; description?: string; permissions: string[] }>(
        `/workspaces/${workspace.id}/roles/${editingRole.id}`,
        {
          name,
          description: description || undefined,
          permissions,
        },
      );
      setRoles((current) => current.map((item) => (item.id === role.id ? role : item)));
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update role.");
    } finally {
      setSaving(false);
    }
  }

  function startEditing(role: Role) {
    setEditingRole(role);
    setName(role.name);
    setDescription(role.description || "");
    setPermissions(role.permissions);
  }

  function resetForm() {
    setEditingRole(null);
    setName("");
    setDescription("");
    setPermissions(["dashboard.view"]);
  }

  function togglePermission(permission: string) {
    setPermissions((current) =>
      current.includes(permission) ? current.filter((item) => item !== permission) : [...current, permission],
    );
  }

  return (
    <section className="page-stack">
      <header className="page-head">
        <p className="eyebrow">Settings</p>
        <h1>Roles & permissions</h1>
        <p>Define what each exco or member role can see and do across this workspace.</p>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="settings-grid">
        <article className="panel-card settings-roles-card">
          <div className="card-head">
            <h2>Workspace roles</h2>
          </div>
          {loading ? (
            <p className="empty-block">Loading roles...</p>
          ) : (
            <div className="role-list">
              {roles.map((role) => (
                <button
                  key={role.id}
                  type="button"
                  className={`role-card ${editingRole?.id === role.id ? "active" : ""}`}
                  onClick={() => startEditing(role)}
                >
                  <div className="role-card-main">
                    <div>
                      <h3>{role.name}</h3>
                      <p>{role.description || (role.is_system_role ? "System role" : "Custom role")}</p>
                    </div>
                    <span className={`status-pill ${role.is_system_role ? "ok" : "pending"}`}>
                      {role.is_system_role ? "System" : "Custom"}
                    </span>
                  </div>
                  <div className="permission-chips">
                    {role.permissions.slice(0, 10).map((permission) => (
                      <span key={permission}>{permission}</span>
                    ))}
                    {role.permissions.length > 10 ? <span>+{role.permissions.length - 10} more</span> : null}
                  </div>
                </button>
              ))}
            </div>
          )}
        </article>

        <article className="panel-card settings-editor-card">
          <div className="card-head compact">
            <h2>{editingRole ? "Edit role" : "Create role"}</h2>
            {editingRole ? (
              <button type="button" className="btn-ghost" onClick={resetForm}>
                New role
              </button>
            ) : null}
          </div>
          <form className="form-stack" onSubmit={editingRole ? saveRole : createRole}>
            <label>
              Role name
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Events Lead" required />
            </label>
            <label>
              Description
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What this role is responsible for"
                rows={3}
              />
            </label>
            <div className="permission-picker">
              {permissionGroups.map(([group, groupPermissions]) => (
                <div key={group}>
                  <strong>{group}</strong>
                  {(groupPermissions as string[]).map((permission) => (
                    <label key={permission} className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={permissions.includes(permission)}
                        onChange={() => togglePermission(permission)}
                      />
                      <span>{permission}</span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? "Saving..." : editingRole ? "Save role" : "Create role"}
            </button>
          </form>
        </article>
      </section>
    </section>
  );
}
