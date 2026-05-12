"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { apiGet, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };

function toMeetingTimestamp(value: string) {
  return value.replace("T", " ");
}

export default function NewMeetingPage({ params }: { params: { workspaceSlug: string } }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [scheduledFor, setScheduledFor] = useState("");
  const [agenda, setAgenda] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
      const meeting = await apiPost<{ id: number }, { title: string; scheduled_for: string; agenda: string[]; meeting_type: string }>(
        `/workspaces/${workspace.id}/meetings`,
        {
          title: title.trim(),
          scheduled_for: toMeetingTimestamp(scheduledFor),
          agenda: agenda
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean),
          meeting_type: "general",
        },
      );
      router.push(`/${params.workspaceSlug}/meetings/${meeting.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create meeting.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-head">
        <p className="eyebrow">Meetings</p>
        <h1>Schedule meeting</h1>
      </header>
      <article className="panel-card">
        <form className="form-stack" onSubmit={submit}>
          <label>
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} required />
          </label>
          <label>
            Scheduled for
            <input
              type="datetime-local"
              value={scheduledFor}
              onChange={(event) => setScheduledFor(event.target.value)}
              required
            />
          </label>
          <label>
            Agenda
            <textarea rows={6} value={agenda} onChange={(event) => setAgenda(event.target.value)} placeholder="One agenda item per line" />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="btn-primary" disabled={loading} type="submit">
            {loading ? "Creating..." : "Create meeting"}
          </button>
        </form>
      </article>
    </section>
  );
}
