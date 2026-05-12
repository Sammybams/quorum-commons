import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getPortalData, buildShortUrl } from "@/lib/api/links";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

export async function generateMetadata({ params }: { params: { workspaceSlug: string } }): Promise<Metadata> {
  const data = await getPortalData(params.workspaceSlug);
  if (!data) return {};

  const title = `${data.workspace.name} | Quorum`;
  const description = data.workspace.description || "Links, events, fundraising, and updates from this workspace.";
  const ogImage = `${APP_URL}/api/og/portal/${data.workspace.slug}`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
      url: `${APP_URL}/portal/${data.workspace.slug}`,
      images: [{ url: ogImage, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [ogImage],
    },
  };
}

export default async function PortalPage({ params }: { params: { workspaceSlug: string } }) {
  const data = await getPortalData(params.workspaceSlug);
  if (!data) notFound();
  const featuredAnnouncement = data.announcements.find((announcement) => announcement.is_pinned) || data.announcements[0];

  return (
    <main className="portal-page">
      <header className="portal-hero">
        <div>
          <p className="eyebrow">Public portal</p>
          <h1>{data.workspace.name}</h1>
          <p>{data.workspace.description || "Links, events, fundraising, and updates from this workspace."}</p>
        </div>
        <span className="portal-badge">{data.workspace.slug}</span>
      </header>

      {featuredAnnouncement ? (
        <section className="portal-feature">
          <span>{featuredAnnouncement.is_pinned ? "Pinned announcement" : "Latest announcement"}</span>
          <h2>{featuredAnnouncement.title}</h2>
          <p>{featuredAnnouncement.body}</p>
        </section>
      ) : null}

      <section className="portal-grid">
        <article className="portal-card">
          <div className="card-head compact">
            <h2>Active links</h2>
            <span>{data.links.length}</span>
          </div>
          {data.links.length ? (
            <div className="portal-list">
              {data.links.map((link) => (
                <a key={link.slug} href={buildShortUrl(link.slug)}>
                  <span>{link.title || `/${link.slug}`}</span>
                  <strong>{link.click_count} clicks</strong>
                </a>
              ))}
            </div>
          ) : (
            <p className="portal-empty">No public links have been published yet.</p>
          )}
        </article>

        <article className="portal-card">
          <div className="card-head compact">
            <h2>Upcoming events</h2>
            <span>{data.events.length}</span>
          </div>
          {data.events.length ? (
            <div className="portal-list">
              {data.events.map((event) => (
                <a key={event.slug} href={`/e/${event.slug}`}>
                  <span>{event.title}</span>
                  <strong>{event.starts_at}</strong>
                </a>
              ))}
            </div>
          ) : (
            <p className="portal-empty">No public events are live yet.</p>
          )}
        </article>

        <article className="portal-card">
          <div className="card-head compact">
            <h2>Announcements</h2>
            <span>{data.announcements.length}</span>
          </div>
          {data.announcements.length ? (
            <div className="portal-announcements">
              {data.announcements.map((announcement) => (
                <div key={`${announcement.title}-${announcement.published_at || ""}`}>
                  <strong>{announcement.title}</strong>
                  <p>{announcement.body}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="portal-empty">No announcements have been posted yet.</p>
          )}
        </article>
      </section>
    </main>
  );
}
