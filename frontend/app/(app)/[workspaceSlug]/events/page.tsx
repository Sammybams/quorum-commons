import Link from "next/link";

import { apiGet } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Event = { id: number; title: string; event_type: string; starts_at: string; venue?: string; rsvp_count: number };

export default async function EventsPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
  const events = await apiGet<Event[]>(`/workspaces/${workspace.id}/events`);

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Events</p>
          <h1>Events calendar</h1>
          <p>{workspace.name}</p>
        </div>
        <Link href={`/${workspace.slug}/events/new`} className="btn-primary">
          <span className="material-symbols-outlined" aria-hidden="true">
            add
          </span>
          Create Event
        </Link>
      </header>

      <article className="panel-card">
        {events.length === 0 ? (
          <div className="empty-state">
            <span className="material-symbols-outlined" aria-hidden="true">
              event_busy
            </span>
            <h2>No events created yet</h2>
            <p>Publish your first event and its RSVP activity will appear here.</p>
          </div>
        ) : (
          <div className="activity-list">
            {events.map((event) => (
              <Link key={event.id} href={`/${workspace.slug}/events/${event.id}`} className="activity-item">
                <div>
                  <h3>{event.title}</h3>
                  <p>{event.event_type} · {event.venue || "Venue TBD"}</p>
                </div>
                <div className="activity-meta">
                  <span>{event.starts_at}</span>
                  <strong>{event.rsvp_count} RSVPs</strong>
                </div>
              </Link>
            ))}
          </div>
        )}
      </article>
    </section>
  );
}
