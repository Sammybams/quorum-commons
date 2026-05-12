import Link from "next/link";

import { apiGet } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Meeting = {
  id: number;
  title: string;
  meeting_type: string;
  scheduled_for: string;
  status: string;
};

export default async function MeetingsPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
  const meetings = await apiGet<Meeting[]>(`/workspaces/${workspace.id}/meetings`);

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Meetings</p>
          <h1>Meetings</h1>
          <p>{workspace.name}</p>
        </div>
        <Link href={`/${workspace.slug}/meetings/new`} className="btn-primary">
          <span className="material-symbols-outlined" aria-hidden="true">
            add
          </span>
          Schedule meeting
        </Link>
      </header>
      <article className="panel-card">
        {meetings.length === 0 ? (
          <div className="empty-state">
            <span className="material-symbols-outlined" aria-hidden="true">
              groups_3
            </span>
            <h2>No meetings yet</h2>
            <p>Create meetings, upload transcripts, and publish minutes here.</p>
          </div>
        ) : (
          <div className="activity-list">
            {meetings.map((meeting) => (
              <Link key={meeting.id} href={`/${workspace.slug}/meetings/${meeting.id}`} className="activity-item">
                <div>
                  <h3>{meeting.title}</h3>
                  <p>{meeting.meeting_type}</p>
                </div>
                <div className="activity-meta">
                  <span>{meeting.scheduled_for}</span>
                  <strong>{meeting.status}</strong>
                </div>
              </Link>
            ))}
          </div>
        )}
      </article>
    </section>
  );
}
