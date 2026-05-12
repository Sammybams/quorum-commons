"use client";

import { useEffect, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type EventDetail = {
  id: number;
  title: string;
  event_type: string;
  starts_at: string;
  venue?: string | null;
  description?: string | null;
  rsvp_count: number;
  attendees: Array<{
    id: number;
    full_name: string;
    email: string;
    status: string;
    checked_in_at?: string | null;
  }>;
};

export default function EventDetailPage({ params }: { params: { workspaceSlug: string; eventId: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [event, setEvent] = useState<EventDetail | null>(null);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const found = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        setWorkspace(found);
        setEvent(await apiGet<EventDetail>(`/workspaces/${found.id}/events/${params.eventId}`));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load event.");
      }
    }
    load();
  }, [params.eventId, params.workspaceSlug]);

  async function checkIn(attendeeId: number) {
    if (!workspace || !event) {
      return;
    }
    setWorkingId(attendeeId);
    setError(null);
    try {
      const updated = await apiPost<{ id: number; checked_in_at?: string | null; status: string }, Record<string, never>>(
        `/workspaces/${workspace.id}/events/${event.id}/check-in/${attendeeId}`,
        {},
      );
      setEvent((current) =>
        current
          ? {
              ...current,
              attendees: current.attendees.map((attendee) =>
                attendee.id === attendeeId ? { ...attendee, checked_in_at: updated.checked_in_at || attendee.checked_in_at, status: updated.status } : attendee,
              ),
            }
          : current,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to check attendee in.");
    } finally {
      setWorkingId(null);
    }
  }

  if (!workspace || !event) {
    return <section className="page-stack"><article className="panel-card"><p>{error || "Loading event..."}</p></article></section>;
  }

  return (
    <section className="page-stack">
      <header className="page-head">
        <p className="eyebrow">Event detail</p>
        <h1>{event.title}</h1>
        <p>
          {event.event_type} · {event.starts_at}
          {event.venue ? ` · ${event.venue}` : ""}
        </p>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="content-grid">
        <article className="panel-card">
          <h2>Overview</h2>
          <p>{event.description || "No description provided."}</p>
          <div className="mini-list">
            <div>
              <span>RSVPs</span>
              <strong>{event.rsvp_count}</strong>
            </div>
            <div>
              <span>Checked in</span>
              <strong>{event.attendees.filter((item) => item.checked_in_at).length}</strong>
            </div>
          </div>
        </article>

        <article className="panel-card">
          <h2>Attendees</h2>
          {event.attendees.length === 0 ? (
            <div className="empty-block">
              <span className="material-symbols-outlined" aria-hidden="true">
                group_off
              </span>
              <h3>No attendees yet</h3>
              <p>RSVP activity will appear here.</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {event.attendees.map((attendee) => (
                    <tr key={attendee.id}>
                      <td>{attendee.full_name}</td>
                      <td>{attendee.email}</td>
                      <td>{attendee.checked_in_at ? "Checked in" : attendee.status}</td>
                      <td>
                        {attendee.checked_in_at ? (
                          <span className="status-pill ok">Done</span>
                        ) : (
                          <button type="button" className="btn-secondary" onClick={() => checkIn(attendee.id)} disabled={workingId === attendee.id}>
                            {workingId === attendee.id ? "Checking in..." : "Check in"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      </section>
    </section>
  );
}
