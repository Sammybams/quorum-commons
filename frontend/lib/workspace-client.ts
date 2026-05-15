import { apiGet } from "./api";
import { cacheWorkspace, readCachedWorkspace, readSession } from "./session";

export type ClientWorkspace = {
  id: number;
  slug: string;
  name: string;
  description?: string;
  workspace_type?: string;
  community_profile?: Record<string, string>;
};

export async function resolveWorkspace(slug: string): Promise<ClientWorkspace> {
  const session = readSession();
  const sessionWorkspace = session?.workspaces?.find((item) => item.workspace_slug === slug && item.workspace_id);
  const fromSession =
    session?.workspace_slug === slug && session.workspace_id
      ? { id: session.workspace_id, slug, name: session.workspace_name }
      : sessionWorkspace
        ? { id: sessionWorkspace.workspace_id, slug, name: sessionWorkspace.workspace_name }
        : null;
  if (fromSession) {
    cacheWorkspace(fromSession);
    return fromSession;
  }

  const cached = readCachedWorkspace(slug);
  if (cached) {
    return { id: cached.id, slug: cached.slug, name: cached.name };
  }

  const workspace = await apiGet<ClientWorkspace>(`/workspaces/slug/${slug}`, { clientTtlMs: 30_000 });
  cacheWorkspace(workspace);
  return workspace;
}
