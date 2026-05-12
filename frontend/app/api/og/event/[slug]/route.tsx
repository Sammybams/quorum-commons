import { ImageResponse } from "next/og";
import { getEventBySlug, formatEventDateShort } from "@/lib/api/events";

export const runtime = "edge";

export async function GET(_request: Request, { params }: { params: { slug: string } }) {
  const event = await getEventBySlug(params.slug);
  if (!event) {
    return new Response("Event not found", { status: 404 });
  }

  const titleSize = event.title.length > 44 ? 52 : 64;
  const badge = event.event_type.charAt(0).toUpperCase() + event.event_type.slice(1);

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
          <span style={{ color: "#94A3B8", fontSize: 18 }}>{event.workspace_name} · quorum.ng</span>
        </div>
        <div style={{ display: "flex", marginBottom: 20 }}>
          <span style={{ background: "#1B5EF726", border: "1px solid #1B5EF750", borderRadius: 20, padding: "6px 18px", color: "#60A5FA", fontSize: 16 }}>
            {badge}
          </span>
        </div>
        <div style={{ color: "#FFFFFF", fontSize: titleSize, fontWeight: 700, lineHeight: 1.1, marginBottom: 28, maxWidth: 920 }}>
          {event.title}
        </div>
        <div style={{ display: "flex", gap: 18, color: "#94A3B8", fontSize: 22, flexWrap: "wrap" }}>
          <span>{formatEventDateShort(event.starts_at)}</span>
          {event.venue ? <span>· {event.venue}</span> : null}
          {event.rsvp_enabled && event.rsvp_count > 0 ? <span style={{ color: "#4ADE80" }}>{event.rsvp_count} RSVPs</span> : null}
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
