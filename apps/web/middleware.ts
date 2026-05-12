import { NextRequest, NextResponse } from "next/server";

const RESERVED_PATHS = new Set([
  "api",
  "e",
  "donate",
  "portal",
  "r",
  "link-expired",
  "dashboard",
  "login",
  "register",
  "signup",
  "settings",
  "members",
  "events",
  "dues",
  "fundraising",
  "campaigns",
  "announcements",
  "links",
  "_next",
  "favicon.ico",
]);

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hostname = request.headers.get("host") ?? "";
  const isQuorumSubdomain =
    hostname.endsWith(".quorum.ng") && hostname !== "quorum.ng" && hostname !== "www.quorum.ng";

  if (isQuorumSubdomain) {
    const workspace = hostname.replace(".quorum.ng", "");
    const url = request.nextUrl.clone();
    url.pathname = `/portal/${workspace}${pathname === "/" ? "" : pathname}`;
    return NextResponse.rewrite(url);
  }

  const segments = pathname.split("/").filter(Boolean);
  if (segments.length !== 1) {
    return NextResponse.next();
  }

  const [segment] = segments;
  if (RESERVED_PATHS.has(segment) || segment.includes(".")) {
    return NextResponse.next();
  }

  try {
    const resolveRes = await fetch(`${API_URL}/public/resolve/${segment}`, { next: { revalidate: 60 } });

    if (resolveRes.status === 410) {
      const expiredUrl = request.nextUrl.clone();
      expiredUrl.pathname = "/link-expired";
      expiredUrl.searchParams.set("slug", segment);
      return NextResponse.rewrite(expiredUrl);
    }

    if (!resolveRes.ok) {
      return NextResponse.next();
    }

    const resolveData = (await resolveRes.json()) as { destination: string; link_id: number };

    fetch(`${API_URL}/public/click`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        link_id: resolveData.link_id,
        referer: request.headers.get("referer") ?? "direct",
        user_agent: request.headers.get("user-agent") ?? "",
      }),
    }).catch(() => {});

    return NextResponse.redirect(resolveData.destination, { status: 307 });
  } catch {
    return NextResponse.next();
  }
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
