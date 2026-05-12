import { ImageResponse } from "next/og";
import { getCampaignBySlug, formatNaira } from "@/lib/api/campaigns";

export const runtime = "edge";

export async function GET(_request: Request, { params }: { params: { slug: string } }) {
  const campaign = await getCampaignBySlug(params.slug);
  if (!campaign) {
    return new Response("Campaign not found", { status: 404 });
  }

  const pct = Math.min(campaign.progress_pct, 100);
  const titleSize = campaign.name.length > 44 ? 52 : 64;

  return new ImageResponse(
    (
      <div
        style={{
          width: "1200px",
          height: "630px",
          display: "flex",
          flexDirection: "column",
          background: "#0A0A0A",
          padding: "60px",
          fontFamily: "Arial, sans-serif",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 8, background: "#1B5EF7" }} />
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: "auto" }}>
          <div style={{ background: "#1B5EF7", borderRadius: 10, padding: "8px 16px", color: "white", fontSize: 18, fontWeight: 700 }}>
            Q
          </div>
          <span style={{ color: "#94A3B8", fontSize: 18 }}>{campaign.workspace_name} · quorum.ng</span>
        </div>
        <div style={{ display: "flex", marginBottom: 20 }}>
          <span style={{ background: "#16a34a26", border: "1px solid #16a34a50", borderRadius: 20, padding: "6px 18px", color: "#4ADE80", fontSize: 16 }}>
            Fundraising Campaign
          </span>
        </div>
        <div style={{ color: "#FFFFFF", fontSize: titleSize, fontWeight: 700, lineHeight: 1.1, marginBottom: 32, maxWidth: 920 }}>
          {campaign.name}
        </div>
        <div style={{ width: 1080, height: 12, background: "#1F2937", borderRadius: 6, marginBottom: 20, overflow: "hidden", display: "flex" }}>
          <div style={{ width: `${Math.round((pct / 100) * 1080)}px`, height: 12, background: "#1B5EF7", borderRadius: 6 }} />
        </div>
        <div style={{ display: "flex", gap: 24, alignItems: "baseline" }}>
          <span style={{ color: "#FFFFFF", fontSize: 28, fontWeight: 700 }}>{formatNaira(campaign.raised_amount)} raised</span>
          <span style={{ color: "#94A3B8", fontSize: 20 }}>of {formatNaira(campaign.target_amount)}</span>
          <span style={{ background: "#1B5EF726", border: "1px solid #1B5EF750", borderRadius: 16, padding: "4px 14px", color: "#60A5FA", fontSize: 18 }}>
            {pct}% funded
          </span>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
      headers: { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400" },
    },
  );
}
