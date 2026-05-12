export type QuorumSession = {
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
  workspace_slug: string;
  workspace_name: string;
  member_id: number;
  role: string;
  role_key: string;
  permissions: string[];
};

const SESSION_KEY = "quorum_session";
const LAST_WORKSPACE_KEY = "quorum_last_workspace";

export function saveSession(session: QuorumSession) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  if (session.workspace_slug) {
    window.localStorage.setItem(LAST_WORKSPACE_KEY, session.workspace_slug);
  }
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
