import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getEventBySlug, formatEventDate } from "@/lib/api/events";
import PublicEventRsvpForm from "./rsvp-form";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

export async function generateMetadata({ params }: { params: { eventSlug: string } }): Promise<Metadata> {
  const event = await getEventBySlug(params.eventSlug);
  if (!event) return {};

  const title = `${event.title} | ${event.workspace_name}`;
  const description = event.description || `${event.workspace_name} event on Quorum.`;
  const ogImage = event.thumbnail_url || `${APP_URL}/api/og/event/${event.slug}`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
      url: `${APP_URL}/e/${event.slug}`,
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

export default async function PublicEventPage({ params }: { params: { eventSlug: string } }) {
  const event = await getEventBySlug(params.eventSlug);
  if (!event) notFound();

  return (
    <main>
      <div className="hero">
        <h1>{event.title}</h1>
        <p>{formatEventDate(event.starts_at)} {event.venue ? `• ${event.venue}` : ""}</p>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <p>{event.description || "No description provided."}</p>
        <p className="muted">RSVPs: {event.rsvp_count}</p>
        {event.rsvp_enabled ? <PublicEventRsvpForm eventSlug={event.slug} /> : null}
      </div>
    </main>
  );
}
