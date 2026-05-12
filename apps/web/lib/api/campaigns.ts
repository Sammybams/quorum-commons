const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export type CampaignPublic = {
  name: string;
  slug: string;
  target_amount: number;
  raised_amount: number;
  status: string;
  progress_pct: number;
  workspace_name: string;
  workspace_slug: string;
  workspace: { name: string; slug: string };
  funding_streams: Array<{
    id: number;
    name: string;
    stream_type: string;
    target_amount: number | null;
    raised_amount: number;
  }>;
  contributor_count: number;
};

export async function getCampaignBySlug(slug: string): Promise<CampaignPublic | null> {
  try {
    const res = await fetch(`${API_URL}/public/donate/${slug}`, { next: { revalidate: 60 } });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Failed to fetch campaign: ${res.status}`);
    return res.json();
  } catch {
    return null;
  }
}

export function formatNaira(amount: number): string {
  return `NGN ${amount.toLocaleString("en-NG")}`;
}
