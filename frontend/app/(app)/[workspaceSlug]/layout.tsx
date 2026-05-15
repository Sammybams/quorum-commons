"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import ThemeToggle from "@/components/theme-toggle";
import { apiPost } from "@/lib/api";
import { clearSession, readSession, saveSession, type QuorumSession, type QuorumWorkspace } from "@/lib/session";

const navItems = [
  { label: "Dashboard", icon: "dashboard", href: "dashboard", permission: "dashboard.view" },
  { label: "Members", icon: "group", href: "members", permission: "members.view" },
  { label: "Events", icon: "event", href: "events", permission: "events.view" },
  { label: "Meetings", icon: "groups_3", href: "meetings", permission: "meetings.view" },
  { label: "Fundraising", icon: "payments", href: "campaigns", permission: "campaigns.view" },
  { label: "Dues", icon: "receipt_long", href: "dues", permission: "dues.view" },
  { label: "Budgets", icon: "account_balance", href: "budgets", permission: "budgets.view" },
  { label: "Community Inbox", icon: "forum", href: "community-inbox", permission: "integrations.manage" },
  { label: "Opportunities", icon: "work", href: "opportunities", permission: "opportunities.view" },
  { label: "Financial Health", icon: "monitoring", href: "financial-health", permission: "reports.view" },
  { label: "Reports", icon: "analytics", href: "reports", permission: "reports.view" },
  { label: "Tasks", icon: "checklist", href: "tasks", permission: "tasks.view" },
  { label: "Links", icon: "link", href: "links", permission: "dashboard.view" },
  { label: "Announcements", icon: "campaign", href: "announcements", permission: "announcements.view" },
  { label: "Integrations", icon: "hub", href: "settings/integrations", permission: "integrations.manage" },
  { label: "Settings", icon: "settings", href: "settings/roles", permission: "settings.view" },
];

export default function WorkspaceLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: { workspaceSlug: string };
}) {
  const base = `/${params.workspaceSlug}`;
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<QuorumSession | null>(null);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const workspaceMenuRef = useRef<HTMLDivElement | null>(null);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);
  const workspaceName = session?.workspace_name || params.workspaceSlug;
  const workspaceLabel = workspaceName.split("-").join(" ");
  const currentWorkspaceSession = session?.workspaces?.find((item) => item.workspace_slug === params.workspaceSlug) || null;
  const currentPermissions = currentWorkspaceSession?.permissions || [];
  const visibleNavItems = navItems.filter((item) => !item.permission || currentPermissions.includes(item.permission));
  const prefetchTargets = [
    `${base}/dashboard`,
    `${base}/members`,
    `${base}/events`,
    `${base}/meetings`,
    `${base}/campaigns`,
    `${base}/dues`,
    `${base}/budgets`,
    ...visibleNavItems.map((item) => `${base}/${item.href}`),
    ...(currentPermissions.includes("settings.view") ? [`${base}/settings/workspace`] : []),
    ...(currentPermissions.includes("events.manage") ? [`${base}/events/new`] : []),
  ];

  useEffect(() => {
    setSession(readSession());
  }, []);

  useEffect(() => {
    prefetchTargets.forEach((href) => {
      router.prefetch(href);
    });
  }, [router, base]);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (workspaceMenuRef.current && !workspaceMenuRef.current.contains(target)) {
        setWorkspaceOpen(false);
      }
      if (profileMenuRef.current && !profileMenuRef.current.contains(target)) {
        setProfileOpen(false);
      }
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setWorkspaceOpen(false);
        setProfileOpen(false);
      }
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  async function signOut() {
    if (session?.refresh_token || session?.access_token) {
      try {
        await apiPost("/auth/logout", {
          refresh_token: session?.refresh_token,
          access_token: session?.access_token,
        });
      } catch {
        // Best effort logout; local signout still proceeds.
      }
    }
    clearSession();
    router.push("/login");
  }

  function switchWorkspace(workspace: QuorumWorkspace) {
    if (!session) {
      return;
    }
    const nextSession: QuorumSession = {
      ...session,
      workspace_id: workspace.workspace_id,
      workspace_slug: workspace.workspace_slug,
      workspace_name: workspace.workspace_name,
      member_id: workspace.member_id,
      member_role: workspace.role,
      role_key: workspace.role_key,
    };
    saveSession(nextSession);
    setSession(nextSession);
    setWorkspaceOpen(false);
    router.push(`/${workspace.workspace_slug}/dashboard`);
  }

  const initials = session?.member_name
    ? session.member_name
        .split(" ")
        .map((part) => part[0])
        .join("")
        .slice(0, 2)
        .toUpperCase()
    : "Q";

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <Link href={`${base}/dashboard`} className="brand-block" prefetch>
          <img className="brand-logo-img" src="/brand/quorum-icon-circle.svg" alt="" />
          <span className="brand-copy">
            <strong>Quorum</strong>
            <small title={workspaceLabel || "Community Admin"}>{workspaceLabel || "Community Admin"}</small>
          </span>
        </Link>

        <nav className="nav-list" aria-label="Workspace">
          {visibleNavItems.map((item) => {
            const href = `${base}/${item.href}`;
            const section = item.href.split("/")[0];
            const isActive = pathname === href || pathname.startsWith(`${base}/${section}/`);

            return (
              <Link
                key={item.href}
                className={`nav-item ${isActive ? "active" : ""}`}
                href={href}
                prefetch
                aria-current={isActive ? "page" : undefined}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="side-nav-actions">
          {currentPermissions.includes("campaigns.manage") ? (
            <Link href={`${base}/campaigns`} className="side-action primary" prefetch>
              <span className="material-symbols-outlined" aria-hidden="true">
                add
              </span>
              <span>New Campaign</span>
            </Link>
          ) : null}
          <button type="button" className="side-action" onClick={signOut}>
            <span className="material-symbols-outlined" aria-hidden="true">
              logout
            </span>
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <div className="workspace-frame">
        <header className="topbar">
          <div className="workspace-switcher" ref={workspaceMenuRef}>
            <button
              type="button"
              className="workspace-pill"
              title={session?.workspace_name || params.workspaceSlug}
              aria-expanded={workspaceOpen}
              onClick={() => {
                setWorkspaceOpen((value) => !value);
                setProfileOpen(false);
              }}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                expand_more
              </span>
              <span className="workspace-pill-text">{workspaceLabel || params.workspaceSlug}</span>
            </button>
            {workspaceOpen ? (
              <div className="workspace-menu">
                {(session?.workspaces || []).length > 0 ? (
                  session?.workspaces?.map((workspace) => (
                    <button
                      key={workspace.workspace_slug}
                      type="button"
                      className={workspace.workspace_slug === params.workspaceSlug ? "active" : ""}
                      onClick={() => switchWorkspace(workspace)}
                    >
                      <span>
                        <strong>{workspace.workspace_name}</strong>
                        <small>{workspace.role}</small>
                      </span>
                      {workspace.workspace_slug === params.workspaceSlug ? (
                        <span className="material-symbols-outlined" aria-hidden="true">
                          check
                        </span>
                      ) : null}
                    </button>
                  ))
                ) : (
                  <p>Sign in again to load your communities.</p>
                )}
              </div>
            ) : null}
          </div>
          <div className="topbar-actions">
            <ThemeToggle compact />
            <button type="button" className="icon-button" aria-label="Notifications">
              <span className="material-symbols-outlined" aria-hidden="true">
                notifications
              </span>
            </button>
            <Link href={`${base}/events/new`} className="btn-secondary" prefetch>
              <span className="material-symbols-outlined" aria-hidden="true">
                add
              </span>
              Create Event
            </Link>
            <div className="profile-menu-wrap" ref={profileMenuRef}>
              <button
                type="button"
                className="avatar-chip"
                aria-label="Open profile menu"
                aria-expanded={profileOpen}
                onClick={() => {
                  setProfileOpen((value) => !value);
                  setWorkspaceOpen(false);
                }}
              >
                {initials}
              </button>
              {profileOpen ? (
                <div className="profile-menu">
                  <div>
                    <strong>{session?.member_name || "Quorum user"}</strong>
                    <span>{session?.member_role || "Workspace member"}</span>
                  </div>
                  <Link href={`${base}/dashboard`} prefetch>
                    <span className="material-symbols-outlined" aria-hidden="true">
                      person
                    </span>
                    Profile
                  </Link>
                  {currentPermissions.includes("settings.view") ? (
                    <Link href={`${base}/settings/workspace`} prefetch>
                      <span className="material-symbols-outlined" aria-hidden="true">
                        settings
                      </span>
                      Settings
                    </Link>
                  ) : null}
                  {currentPermissions.includes("integrations.manage") ? (
                    <Link href={`${base}/settings/integrations`} prefetch>
                      <span className="material-symbols-outlined" aria-hidden="true">
                        hub
                      </span>
                      Connect Google
                    </Link>
                  ) : null}
                  <button type="button" onClick={signOut}>
                    <span className="material-symbols-outlined" aria-hidden="true">
                      logout
                    </span>
                    Sign out
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className="workspace-canvas">{children}</main>
      </div>
    </div>
  );
}
