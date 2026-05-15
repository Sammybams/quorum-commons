import { cache } from "react";

import { API_BASE_URL } from "./api";

export type ServerWorkspace = { id: number; slug: string; name: string };

export const getWorkspaceBySlug = cache(async (slug: string): Promise<ServerWorkspace> => {
  const res = await fetch(`${API_BASE_URL}/workspaces/slug/${slug}`, {
    next: { revalidate: 60 },
  });
  if (!res.ok) {
    throw new Error(`Workspace lookup failed: ${res.status}`);
  }
  return res.json() as Promise<ServerWorkspace>;
});
