"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };

function slugify(input: string) {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}

export default function NewEventPage({ params }: { params: { workspaceSlug: string } }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [eventType, setEventType] = useState("social");
  const [venue, setVenue] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
      await apiPost(`/workspaces/${workspace.id}/events`, {
        title,
        slug: `${slugify(title)}-${Date.now().toString(36)}`,
        event_type: eventType,
        starts_at: [date, time].filter(Boolean).join(" "),
        venue: venue || undefined,
        description: description || undefined,
        rsvp_enabled: true,
      });
      router.push(`/${workspace.slug}/events`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create event.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-head">
        <p className="eyebrow">Events</p>
        <h1>Create new event</h1>
        <p>Build and publish an event page in one clean flow.</p>
      </header>

      <div className="fund-grid">
        <article className="panel-card">
          <h2>Event details</h2>
          <form className="form-stack" onSubmit={onSubmit}>
            <label>
              Event title
              <input
                type="text"
                placeholder="Annual Department Dinner"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                required
              />
            </label>

            <div className="form-two">
              <label>
                Event type
                <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
                  <option value="social">Social</option>
                  <option value="academic">Academic</option>
                  <option value="professional">Professional</option>
                  <option value="fundraiser">Fundraiser</option>
                </select>
              </label>
              <label>
                Venue
                <input
                  type="text"
                  placeholder="Main Hall"
                  value={venue}
                  onChange={(event) => setVenue(event.target.value)}
                />
              </label>
            </div>

            <div className="form-two">
              <label>
                Date
                <input type="date" value={date} onChange={(event) => setDate(event.target.value)} required />
              </label>
              <label>
                Time
                <input type="time" value={time} onChange={(event) => setTime(event.target.value)} />
              </label>
            </div>

            <label>
              Description
              <textarea
                rows={5}
                placeholder="Tell members what this event is about"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>

            {error ? <p className="form-error">{error}</p> : null}

            <div className="form-actions">
              <button className="btn-secondary" type="button">
                Save Draft
              </button>
              <button className="btn-primary" type="submit" disabled={loading}>
                {loading ? "Creating..." : "Create Event"}
              </button>
            </div>
          </form>
        </article>

        <article className="panel-card">
          <p className="eyebrow">Live preview</p>
          <div className="event-preview">
            <span className="status-pill ok">{eventType || "Social"} Event</span>
            <h2>{title || "Event title"}</h2>
            <p>{venue || "Venue TBD"} {time ? `· ${time}` : ""}</p>
            <p>{description || "Add a clear title and date first. Most RSVP decisions come from those two fields."}</p>
          </div>
        </article>
      </div>
    </section>
  );
}
