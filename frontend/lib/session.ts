export type QuorumSession = {
  workspace_id?: number | null;
  workspace_slug: string;
  workspace_name: string;
  member_id: number;
  member_name: string;
  member_role: string;
  user_id?: number;
  role_key?: string;
  access_token?: string;
  refresh_token?: string;
  token_type?: string;
  workspaces?: QuorumWorkspace[];
};

export type QuorumWorkspace = {
  workspace_id: number;
  workspace_slug: string;
  workspace_name: string;
  member_id: number;
  role: string;
  role_key: string;
  permissions: string[];
};

const SESSION_KEY = "quorum_session";
const LAST_WORKSPACE_KEY = "quorum_last_workspace";
const WORKSPACE_CACHE_KEY = "quorum_workspace_cache";

type WorkspaceCacheEntry = {
  id: number;
  slug: string;
  name: string;
  cached_at: number;
};

export function saveSession(session: QuorumSession) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  if (session.workspace_slug) {
    window.localStorage.setItem(LAST_WORKSPACE_KEY, session.workspace_slug);
  }
  const cache = readWorkspaceCacheMap();
  if (session.workspace_id && session.workspace_slug) {
    cache[session.workspace_slug] = {
      id: session.workspace_id,
      slug: session.workspace_slug,
      name: session.workspace_name,
      cached_at: Date.now(),
    };
  }
  for (const workspace of session.workspaces || []) {
    cache[workspace.workspace_slug] = {
      id: workspace.workspace_id,
      slug: workspace.workspace_slug,
      name: workspace.workspace_name,
      cached_at: Date.now(),
    };
  }
  window.localStorage.setItem(WORKSPACE_CACHE_KEY, JSON.stringify(cache));
}

export function readSession(): QuorumSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const value = window.localStorage.getItem(SESSION_KEY);
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value) as QuorumSession;
  } catch {
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function clearSession() {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(SESSION_KEY);
}

export function readAccessToken(): string | null {
  return readSession()?.access_token || null;
}

export function readLastWorkspaceSlug(): string {
  if (typeof window === "undefined") {
    return "";
  }

  return window.localStorage.getItem(LAST_WORKSPACE_KEY) || "";
}

function readWorkspaceCacheMap(): Record<string, WorkspaceCacheEntry> {
  if (typeof window === "undefined") {
    return {};
  }

  const value = window.localStorage.getItem(WORKSPACE_CACHE_KEY);
  if (!value) {
    return {};
  }

  try {
    return JSON.parse(value) as Record<string, WorkspaceCacheEntry>;
  } catch {
    window.localStorage.removeItem(WORKSPACE_CACHE_KEY);
    return {};
  }
}

export function readCachedWorkspace(slug: string): WorkspaceCacheEntry | null {
  const cache = readWorkspaceCacheMap();
  return cache[slug] || null;
}

export function cacheWorkspace(workspace: { id: number; slug: string; name: string }) {
  if (typeof window === "undefined") {
    return;
  }
  const cache = readWorkspaceCacheMap();
  cache[workspace.slug] = {
    id: workspace.id,
    slug: workspace.slug,
    name: workspace.name,
    cached_at: Date.now(),
  };
  window.localStorage.setItem(WORKSPACE_CACHE_KEY, JSON.stringify(cache));
}
