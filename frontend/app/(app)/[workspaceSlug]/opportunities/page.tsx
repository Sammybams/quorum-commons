"use client";

import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";
import { readSession } from "@/lib/session";
import { resolveWorkspace } from "@/lib/workspace-client";

type Workspace = { id: number; slug: string; name: string };
type OpportunityMatch = {
  id: number;
  member_id: number;
  member_name: string;
  member_role: string;
  trade_category?: string | null;
  location?: string | null;
  availability?: string | null;
  match_score: number;
  fit_label: string;
  status: string;
  matched_tags: string[];
  reasons: string[];
  note?: string | null;
};

type Opportunity = {
  id: number;
  title: string;
  description: string;
  location?: string | null;
  trade_tags: string[];
  deadline?: string | null;
  contact?: string | null;
  status: string;
  match_count: number;
  matches: OpportunityMatch[];
  my_match?: OpportunityMatch | null;
  created_at: string;
};

type SessionWorkspace = {
  workspace_slug: string;
  permissions: string[];
};

type Session = {
  member_id: number;
  workspaces?: SessionWorkspace[];
};

export default function OpportunitiesPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshingId, setRefreshingId] = useState<number | null>(null);
  const [respondingKey, setRespondingKey] = useState<string | null>(null);
  const [updatingMatchKey, setUpdatingMatchKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);

  async function loadPage(slug: string) {
    const foundWorkspace = await resolveWorkspace(slug);
    const foundOpportunities = await apiGet<Opportunity[]>(`/workspaces/${foundWorkspace.id}/opportunities`);
    setWorkspace(foundWorkspace);
    setOpportunities(foundOpportunities);
  }

  useEffect(() => {
    setSession(readSession() as Session | null);
  }, []);

  useEffect(() => {
    async function load() {
      try {
        await loadPage(params.workspaceSlug);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load opportunities.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [params.workspaceSlug]);

  const currentWorkspaceSession = useMemo(
    () => session?.workspaces?.find((item) => item.workspace_slug === params.workspaceSlug) || null,
    [params.workspaceSlug, session],
  );
  const canManage = Boolean(currentWorkspaceSession?.permissions?.includes("opportunities.manage"));

  async function refreshMatches(opportunityId: number) {
    if (!workspace) {
      return;
    }
    setRefreshingId(opportunityId);
    setError(null);
    try {
      const result = await apiPost<{ opportunity: Opportunity }, Record<string, never>>(
        `/workspaces/${workspace.id}/opportunities/${opportunityId}/refresh-matches`,
        {},
      );
      setOpportunities((current) => current.map((item) => (item.id === opportunityId ? result.opportunity : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh opportunity matches.");
    } finally {
      setRefreshingId(null);
    }
  }

  async function respondToOpportunity(opportunityId: number, status: "interested" | "passed") {
    if (!workspace) {
      return;
    }
    const actionKey = `${opportunityId}:${status}`;
    setRespondingKey(actionKey);
    setError(null);
    try {
      const updated = await apiPost<Opportunity, { status: "interested" | "passed" }>(
        `/workspaces/${workspace.id}/opportunities/${opportunityId}/respond`,
        { status },
      );
      setOpportunities((current) => current.map((item) => (item.id === opportunityId ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update your opportunity response.");
    } finally {
      setRespondingKey(null);
    }
  }

  async function updateAdminMatchStatus(opportunityId: number, matchId: number, status: "contacted" | "assigned") {
    if (!workspace) {
      return;
    }
    const actionKey = `${opportunityId}:${matchId}:${status}`;
    setUpdatingMatchKey(actionKey);
    setError(null);
    try {
      const updated = await apiPost<OpportunityMatch, { status: "contacted" | "assigned" }>(
        `/workspaces/${workspace.id}/opportunities/${opportunityId}/matches/${matchId}/status`,
        { status },
      );
      setOpportunities((current) =>
        current.map((item) =>
          item.id !== opportunityId
            ? item
            : {
                ...item,
                matches: item.matches.map((match) => (match.id === matchId ? updated : match)),
              },
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update opportunity workflow status.");
    } finally {
      setUpdatingMatchKey(null);
    }
  }

  const recommendedForMe = useMemo(
    () =>
      opportunities.filter(
        (item) =>
          item.my_match &&
          ["recommended", "interested", "contacted", "assigned"].includes(item.my_match.status),
      ),
    [opportunities],
  );

  const totalMatches = useMemo(
    () => opportunities.reduce((sum, opportunity) => sum + opportunity.match_count, 0),
    [opportunities],
  );

  function humanizeStatus(value: string) {
    const map: Record<string, string> = {
      recommended: "Recommended",
      interested: "Interested",
      contacted: "Contacted",
      assigned: "Assigned",
      passed: "Not for me",
    };
    return map[value] || value.replaceAll("_", " ");
  }

  function statusTone(value: string) {
    if (value === "assigned") return "ok";
    if (value === "interested" || value === "contacted") return "pending";
    if (value === "passed") return "danger";
    return "";
  }

  function renderOpportunityCard(opportunity: Opportunity, mode: "admin" | "member") {
    const myMatch = opportunity.my_match || null;
    return (
      <article key={opportunity.id} className="panel-card">
        <div className="card-head compact">
          <div>
            <h2>{opportunity.title}</h2>
            <p>{opportunity.location || "Location not specified"}</p>
          </div>
          {mode === "admin" ? (
            <span className="status-pill ok">{opportunity.match_count} matches</span>
          ) : myMatch ? (
            <span className={`status-pill ${statusTone(myMatch.status)}`}>{humanizeStatus(myMatch.status)}</span>
          ) : null}
        </div>
        <p>{opportunity.description}</p>
        <div className="permission-chips">
          {(opportunity.trade_tags || []).slice(0, 6).map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
          {opportunity.deadline ? <span>Deadline: {opportunity.deadline}</span> : null}
          {opportunity.contact ? <span>Contact: {opportunity.contact}</span> : null}
        </div>

        {mode === "admin" ? (
          <>
            <div className="card-actions">
              <button
                type="button"
                className="btn-secondary"
                disabled={refreshingId === opportunity.id}
                onClick={() => refreshMatches(opportunity.id)}
              >
                {refreshingId === opportunity.id ? "Refreshing..." : "Refresh matches"}
              </button>
            </div>
            <div className="activity-list">
              {opportunity.matches.length ? (
                opportunity.matches.map((match) => (
                  <div key={match.id} className="activity-item">
                    <div>
                      <h3>{match.member_name}</h3>
                      <p>
                        {match.member_role}
                        {match.trade_category ? ` · ${match.trade_category}` : ""}
                      </p>
                      <p>{match.reasons[0]}</p>
                    </div>
                    <div className="opportunity-admin-actions">
                      <span className={`status-pill ${statusTone(match.status)}`}>{humanizeStatus(match.status)}</span>
                      {match.status !== "contacted" && match.status !== "assigned" ? (
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={updatingMatchKey === `${opportunity.id}:${match.id}:contacted`}
                          onClick={() => updateAdminMatchStatus(opportunity.id, match.id, "contacted")}
                        >
                          {updatingMatchKey === `${opportunity.id}:${match.id}:contacted` ? "Saving..." : "Mark contacted"}
                        </button>
                      ) : null}
                      {match.status !== "assigned" ? (
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={updatingMatchKey === `${opportunity.id}:${match.id}:assigned`}
                          onClick={() => updateAdminMatchStatus(opportunity.id, match.id, "assigned")}
                        >
                          {updatingMatchKey === `${opportunity.id}:${match.id}:assigned` ? "Saving..." : "Assign"}
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))
              ) : (
                <p className="muted-copy opportunity-empty-note">No member matches yet. Refresh matching after members complete more profile details.</p>
              )}
            </div>
          </>
        ) : (
          <>
            {myMatch ? (
              <p className="muted-copy opportunity-member-note">
                {myMatch.status === "recommended"
                  ? "Quorum thinks this is worth your attention based on your profile and activity."
                  : myMatch.status === "interested"
                    ? "You already marked interest in this opportunity."
                    : myMatch.status === "contacted"
                      ? "A community lead has already followed up with you on this opportunity."
                      : myMatch.status === "assigned"
                        ? "This opportunity has already moved into a confirmed handoff or assignment for you."
                        : myMatch.reasons[0]}
              </p>
            ) : (
              <p className="muted-copy opportunity-member-note">
                This opportunity is visible to the community. Quorum has not specifically recommended it to you yet.
              </p>
            )}
            <div className="card-actions">
              <button
                type="button"
                className="btn-primary"
                disabled={respondingKey === `${opportunity.id}:interested`}
                onClick={() => respondToOpportunity(opportunity.id, "interested")}
              >
                {respondingKey === `${opportunity.id}:interested` ? "Saving..." : "I’m interested"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={respondingKey === `${opportunity.id}:passed`}
                onClick={() => respondToOpportunity(opportunity.id, "passed")}
              >
                {respondingKey === `${opportunity.id}:passed` ? "Saving..." : "Not for me"}
              </button>
            </div>
          </>
        )}
      </article>
    );
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Opportunities</p>
          <h1>{canManage ? "Opportunity workflow" : "Opportunities"}</h1>
          <p>
            {canManage
              ? "See what Quorum extracted from community channels, who it recommended, and how each lead is progressing."
              : "Browse community opportunities in one place, with a priority section for the ones Quorum believes are most relevant to you."}
          </p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="metrics-grid">
        <article className="metric-card primary">
          <small>{canManage ? "Open opportunities" : "Community board"}</small>
          <strong>{opportunities.length}</strong>
          <p>{canManage ? "Extracted from synced community channels" : "Open opportunities you can browse right now"}</p>
        </article>
        <article className="metric-card">
          <small>{canManage ? "Match suggestions" : "Recommended to you"}</small>
          <strong>{canManage ? totalMatches : recommendedForMe.length}</strong>
          <p>{canManage ? "Member candidates already surfaced" : "Priority items Quorum wants you to notice first"}</p>
        </article>
        <article className="metric-card">
          <small>{canManage ? "Assigned" : "You responded"}</small>
          <strong>
            {canManage
              ? opportunities.reduce((sum, item) => sum + item.matches.filter((match) => match.status === "assigned").length, 0)
              : opportunities.filter((item) => item.my_match?.status === "interested").length}
          </strong>
          <p>{canManage ? "Matches already moved into action" : "Items you have already responded to"}</p>
        </article>
      </section>

      {loading ? (
        <article className="panel-card">
          <p className="empty-block">Loading opportunities...</p>
        </article>
      ) : opportunities.length === 0 ? (
        <article className="panel-card">
          <div className="empty-block">
            <span className="material-symbols-outlined" aria-hidden="true">
              work_off
            </span>
            <h2>No opportunities yet</h2>
            <p>Once Quorum extracts jobs, gigs, supply requests, or partnership leads from your synced groups, they will appear here.</p>
          </div>
        </article>
      ) : canManage ? (
        <div className="content-grid">
          <div className="side-stack">
            {opportunities.map((opportunity) => renderOpportunityCard(opportunity, "admin"))}
          </div>

          <article className="panel-card">
            <div className="card-head">
              <div>
                <p className="eyebrow">Status guide</p>
                <h2>What each stage means</h2>
              </div>
            </div>
            <div className="activity-list">
              <div className="activity-item">
                <div>
                  <h3>Recommended</h3>
                  <p>Quorum thinks this member is a useful fit based on profile and context.</p>
                </div>
              </div>
              <div className="activity-item">
                <div>
                  <h3>Interested</h3>
                  <p>The member has signaled they want the opportunity.</p>
                </div>
              </div>
              <div className="activity-item">
                <div>
                  <h3>Contacted</h3>
                  <p>An admin or lead has already reached out.</p>
                </div>
              </div>
              <div className="activity-item">
                <div>
                  <h3>Assigned</h3>
                  <p>The workflow has moved from suggestion into an actual placement or handoff.</p>
                </div>
              </div>
            </div>
          </article>
        </div>
      ) : (
        <div className="page-stack">
          <article className="panel-card">
            <div className="card-head">
              <div>
                <p className="eyebrow">Recommended for you</p>
                <h2>Your priority opportunities</h2>
              </div>
            </div>
            {recommendedForMe.length ? (
              <div className="side-stack">
                {recommendedForMe.map((opportunity) => renderOpportunityCard(opportunity, "member"))}
              </div>
            ) : (
              <p className="muted-copy">Quorum has not highlighted a specific opportunity for you yet, but you can still browse the full community board below.</p>
            )}
          </article>

          <article className="panel-card">
            <div className="card-head">
              <div>
                <p className="eyebrow">All opportunities</p>
                <h2>Community board</h2>
              </div>
            </div>
            <div className="side-stack">
              {opportunities.map((opportunity) => renderOpportunityCard(opportunity, "member"))}
            </div>
          </article>
        </div>
      )}
    </section>
  );
}
