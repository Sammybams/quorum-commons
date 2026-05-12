import { ImageResponse } from "next/og";
import { getPortalData } from "@/lib/api/links";

export const runtime = "edge";

export async function GET(_request: Request, { params }: { params: { workspace: string } }) {
  const portal = await getPortalData(params.workspace);
  if (!portal) {
    return new Response("Portal not found", { status: 404 });
  }

  const workspace = portal.workspace;
  const nameSize = workspace.name.length > 34 ? 70 : 92;

  return new ImageResponse(
    (
      <div
        style={{
          width: "1200px",
          height: "630px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          background: "#0A0A0A",
          padding: "80px",
          fontFamily: "Arial, sans-serif",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 8, background: "#1B5EF7" }} />
        <div style={{ position: "absolute", top: 40, right: 60, display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ background: "#1B5EF7", borderRadius: 10, padding: "6px 14px", color: "white", fontSize: 16, fontWeight: 700 }}>
            Q
          </div>
          <span style={{ color: "#94A3B8", fontSize: 16 }}>quorum.ng</span>
        </div>
        <div style={{ color: "#FFFFFF", fontSize: nameSize, fontWeight: 700, lineHeight: 1.1, marginBottom: 24 }}>
          {workspace.name}
        </div>
        {workspace.description ? (
          <div style={{ color: "#94A3B8", fontSize: 28, maxWidth: 900, lineHeight: 1.4 }}>{workspace.description}</div>
        ) : null}
        <div style={{ display: "flex", marginTop: 40 }}>
          <span style={{ background: "#1B5EF726", border: "1px solid #1B5EF750", borderRadius: 20, padding: "8px 20px", color: "#60A5FA", fontSize: 20 }}>
            quorum.ng/{workspace.slug}
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
