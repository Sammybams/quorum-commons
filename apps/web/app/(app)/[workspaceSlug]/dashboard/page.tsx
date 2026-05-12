import Link from "next/link";

import { apiGet } from "@/lib/api";
import DashboardGreeting from "./dashboard-greeting";

type Overview = {
  workspace: { id: number; name: string; slug: string; description?: string };
  counts: {
    members: number;
    dues_cycles: number;
    events: number;
    campaigns: number;
    links: number;
    reports: number;
    paid_members: number;
    pending_members: number;
    tasks: number;
    pending_tasks: number;
    meetings: number;
  };
  recent_events: Array<{ id: number; title: string; starts_at: string; venue?: string; rsvp_count: number }>;
  active_campaigns: Array<{
    id: number;
    name: string;
    target_amount: number;
    raised_amount: number;
    status: string;
  }>;
  dues_cycles: Array<{ id: number; name: string; amount: number; deadline?: string }>;
  links: Array<{ id: number; slug: string; click_count: number; is_active: boolean }>;
  announcements: Array<{
    id: number;
    title: string;
    body: string;
    status: string;
    is_pinned: boolean;
    published_at?: string | null;
  }>;
  recent_activity: Array<{
    type: string;
    title: string;
    description: string;
    created_at: string;
  }>;
  latest_report?: {
    id: number;
    title: string;
    period_label?: string | null;
    status: string;
    overall_score?: number | null;
    overall_grade?: string | null;
    generated_at?: string | null;
  } | null;
};

export default async function DashboardPage({ params }: { params: { workspaceSlug: string } }) {
  let overview: Overview;

  try {
    overview = await apiGet<Overview>(`/workspaces/slug/${params.workspaceSlug}/overview`);
  } catch {
    return (
      <section className="empty-state full">
        <span className="material-symbols-outlined" aria-hidden="true">
          search_off
        </span>
        <h1>Workspace not found</h1>
        <p>Create a workspace first, then return to its dashboard.</p>
        <Link href="/register" className="btn-primary">
          Create workspace
        </Link>
      </section>
    );
  }

  const { workspace, counts } = overview;
  const activeCampaign = overview.active_campaigns.find((campaign) => campaign.status === "active") || null;
  const duesPercent = counts.members > 0 ? Math.round((counts.paid_members / counts.members) * 100) : 0;
  const campaignProgress = activeCampaign
    ? Math.min(100, Math.round((activeCampaign.raised_amount / Math.max(activeCampaign.target_amount, 1)) * 100))
    : 0;

  return (
    <section className="page-stack">
      {counts.pending_members > 0 ? (
        <div className="alert-banner">
          <span className="alert-text">
            {counts.pending_members} {counts.pending_members === 1 ? "member has" : "members have"} not paid dues yet.
          </span>
          <Link href={`/${workspace.slug}/dues`} className="alert-link">
            View report
          </Link>
        </div>
      ) : null}

      <DashboardGreeting workspaceName={workspace.name} workspaceDescription={workspace.description} />

      {counts.members <= 1 && counts.events === 0 && counts.campaigns === 0 ? (
        <section className="onboarding-panel">
          <div>
            <p className="eyebrow">Fresh workspace</p>
            <h2>Start with the essentials</h2>
            <p>Add your first members, schedule events, set dues, and launch campaigns when this community is ready.</p>
          </div>
          <div className="onboarding-actions">
            <Link href={`/${workspace.slug}/members`} className="btn-primary">
              Add members
            </Link>
            <Link href={`/${workspace.slug}/events/new`} className="btn-secondary">
              Create event
            </Link>
          </div>
        </section>
      ) : null}

      <section className="metrics-grid">
        <article className="metric-card primary">
          <span className="material-symbols-outlined" aria-hidden="true">
            group
          </span>
          <small>Total members</small>
          <strong>{counts.members}</strong>
          <p>{counts.members <= 1 ? "Fresh workspace" : "Active registry"}</p>
        </article>
        <article className="metric-card">
          <span className="material-symbols-outlined" aria-hidden="true">
            payments
          </span>
          <small>Dues paid</small>
          <strong>{duesPercent}%</strong>
          <p>{counts.pending_members} pending</p>
        </article>
        <article className="metric-card">
          <span className="material-symbols-outlined" aria-hidden="true">
            event
          </span>
          <small>Events</small>
          <strong>{counts.events}</strong>
          <p>{overview.recent_events.length} recent</p>
        </article>
        <article className="metric-card">
          <span className="material-symbols-outlined" aria-hidden="true">
            checklist
          </span>
          <small>Tasks</small>
          <strong>{counts.pending_tasks}</strong>
          <p>{counts.tasks} tracked</p>
        </article>
        <article className="metric-card">
          <span className="material-symbols-outlined" aria-hidden="true">
            analytics
          </span>
          <small>Reports</small>
          <strong>{counts.reports}</strong>
          <p>{overview.latest_report?.overall_grade || "Generate first audit"}</p>
        </article>
        <article className="metric-card">
          <span className="material-symbols-outlined" aria-hidden="true">
            monitoring
          </span>
          <small>Campaign</small>
          <strong>{campaignProgress}%</strong>
          <p>{activeCampaign?.name || "No active campaign"}</p>
        </article>
      </section>

      <section className="content-grid">
        <article className="panel-card large">
          <div className="card-head">
            <div>
              <p className="eyebrow">Calendar</p>
              <h2>Upcoming events</h2>
            </div>
            <Link href={`/${workspace.slug}/events`} className="subtle-link">
              View all
            </Link>
          </div>
          {overview.recent_events.length === 0 ? (
            <EmptyBlock icon="event_busy" title="No events yet" text="Create your first event and it will appear here." />
          ) : (
            <div className="activity-list">
              {overview.recent_events.map((event) => (
                <div key={event.id} className="activity-item">
                  <div>
                    <h3>{event.title}</h3>
                    <p>{event.venue || "Venue TBD"}</p>
                  </div>
                  <span>{event.starts_at}</span>
                </div>
              ))}
            </div>
          )}
        </article>

        <div className="side-stack">
          <article className="panel-card">
            <div className="card-head compact">
              <h2>Fundraising</h2>
              <Link href={`/${workspace.slug}/campaigns`} className="subtle-link">
                Open
              </Link>
            </div>
            {activeCampaign ? (
              <div className="campaign-widget">
                <strong>{activeCampaign.name}</strong>
                <p>
                  NGN {activeCampaign.raised_amount.toLocaleString()} / NGN{" "}
                  {activeCampaign.target_amount.toLocaleString()}
                </p>
                <div className="progress-track">
                  <span style={{ width: `${campaignProgress}%` }} />
                </div>
              </div>
            ) : (
              <EmptyBlock icon="payments" title="No campaign" text="Create a campaign when fundraising begins." />
            )}
          </article>

          <article className="panel-card">
            <div className="card-head compact">
              <h2>Dues cycles</h2>
              <Link href={`/${workspace.slug}/dues`} className="subtle-link">
                Open
              </Link>
            </div>
            {overview.dues_cycles.length === 0 ? (
              <EmptyBlock icon="receipt_long" title="No dues cycle" text="Set a dues cycle before tracking payments." />
            ) : (
              <div className="mini-list">
                {overview.dues_cycles.map((cycle) => (
                  <div key={cycle.id}>
                    <span>{cycle.name}</span>
                    <strong>NGN {cycle.amount.toLocaleString()}</strong>
                  </div>
                ))}
              </div>
            )}
          </article>

          <article className="panel-card">
            <div className="card-head compact">
              <h2>Audit reports</h2>
              <Link href={`/${workspace.slug}/reports`} className="subtle-link">
                Open
              </Link>
            </div>
            {overview.latest_report ? (
              <div className="mini-list">
                <div>
                  <span>{overview.latest_report.period_label || "Latest report"}</span>
                  <strong>{overview.latest_report.title}</strong>
                </div>
                <div>
                  <span>Overall</span>
                  <strong>
                    {overview.latest_report.overall_score?.toFixed(1) || "-"} / 10 · {overview.latest_report.overall_grade || overview.latest_report.status}
                  </strong>
                </div>
              </div>
            ) : (
              <EmptyBlock icon="analytics" title="No audit report yet" text="Generate an analytics report to review the semester in one document." />
            )}
          </article>

          <article className="panel-card">
            <div className="card-head compact">
              <h2>Announcements</h2>
              <Link href={`/${workspace.slug}/announcements`} className="subtle-link">
                Open
              </Link>
            </div>
            {overview.announcements.length === 0 ? (
              <EmptyBlock icon="campaign" title="No announcements" text="Publish updates for members and portal visitors." />
            ) : (
              <div className="mini-list">
                {overview.announcements.map((announcement) => (
                  <div key={announcement.id}>
                    <span>{announcement.is_pinned ? "Pinned" : "Published"}</span>
                    <strong>{announcement.title}</strong>
                  </div>
                ))}
              </div>
            )}
          </article>

          <article className="panel-card">
            <div className="card-head compact">
              <h2>Recent activity</h2>
            </div>
            {overview.recent_activity.length === 0 ? (
              <EmptyBlock icon="history" title="No activity yet" text="Recent workspace activity will show up here." />
            ) : (
              <div className="mini-list">
                {overview.recent_activity.map((item, index) => (
                  <div key={`${item.type}-${index}`}>
                    <span>{item.type.replace("_", " ")}</span>
                    <strong>{item.title}</strong>
                  </div>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>
    </section>
  );
}

function EmptyBlock({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <div className="empty-block">
      <span className="material-symbols-outlined" aria-hidden="true">
        {icon}
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
