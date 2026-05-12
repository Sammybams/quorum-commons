const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export type EventPublic = {
  title: string;
  slug: string;
  event_type: string;
  starts_at: string;
  venue: string | null;
  description: string | null;
  rsvp_enabled: boolean;
  rsvp_count: number;
  thumbnail_url: string | null;
  workspace_name: string;
  workspace_slug: string;
};

export async function getEventBySlug(slug: string): Promise<EventPublic | null> {
  try {
    const res = await fetch(`${API_URL}/public/e/${slug}`, { next: { revalidate: 60 } });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Failed to fetch event: ${res.status}`);
    return res.json();
  } catch {
    return null;
  }
}

export function formatEventDate(raw: string): string {
  try {
    return new Date(raw).toLocaleDateString("en-GB", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return raw;
  }
}

export function formatEventDateShort(raw: string): string {
  try {
    return new Date(raw).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return raw;
  }
}
