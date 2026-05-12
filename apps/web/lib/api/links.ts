const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

export type ShortLink = {
  id: number;
  workspace_id: number;
  slug: string;
  destination_url: string;
  title: string | null;
  click_count: number;
  is_active: boolean;
  expires_at: string | null;
  short_url: string;
  created_at: string;
};

export type LinkAnalytics = {
  link_id: number;
  total: number;
  daily: Array<{ day: string; count: number }>;
};

export type PortalData = {
  workspace: {
    name: string;
    slug: string;
    description: string | null;
  };
  links: Array<{
    id: number;
    slug: string;
    title: string | null;
    destination_url: string;
    click_count: number;
    expires_at: string | null;
  }>;
  events: Array<{
    title: string;
    slug: string;
    starts_at: string;
    venue: string | null;
    thumbnail_url: string | null;
  }>;
  announcements: Array<{ title: string; body: string; is_pinned: boolean; published_at?: string | null }>;
};

export async function getPortalData(workspaceSlug: string): Promise<PortalData | null> {
  try {
    const res = await fetch(`${API_URL}/public/portal/${workspaceSlug}`, { next: { revalidate: 60 } });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Failed to fetch portal: ${res.status}`);
    return res.json();
  } catch {
    return null;
  }
}

export function buildShortUrl(slug: string): string {
  return `${APP_URL.replace(/\/$/, "")}/${slug}`;
}
