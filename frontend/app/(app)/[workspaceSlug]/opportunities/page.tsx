"use client";

import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";

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
  matched_tags: string[];
  reasons: string[];
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
  created_at: string;
};

export default function OpportunitiesPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshingId, setRefreshingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadPage(slug: string) {
    const foundWorkspace = await apiGet<Workspace>(`/workspaces/slug/${slug}`);
    const foundOpportunities = await apiGet<Opportunity[]>(`/workspaces/${foundWorkspace.id}/opportunities`);
    setWorkspace(foundWorkspace);
    setOpportunities(foundOpportunities);
  }

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

  const totalMatches = useMemo(
    () => opportunities.reduce((sum, opportunity) => sum + opportunity.match_count, 0),
    [opportunities],
  );

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Opportunities</p>
          <h1>Member matching</h1>
          <p>
            {workspace?.name || params.workspaceSlug} members can access these opportunities through their existing workspace roles once
            they join by invitation or invite link.
          </p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="metrics-grid">
        <article className="metric-card primary">
          <small>Open opportunities</small>
          <strong>{opportunities.length}</strong>
          <p>Extracted from synced community channels</p>
        </article>
        <article className="metric-card">
          <small>Match suggestions</small>
          <strong>{totalMatches}</strong>
          <p>Member candidates already surfaced</p>
        </article>
        <article className="metric-card">
          <small>Strong fits</small>
          <strong>{opportunities.reduce((sum, item) => sum + item.matches.filter((match) => match.fit_label === "strong fit").length, 0)}</strong>
          <p>High-confidence matches to follow up</p>
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
      ) : (
        <div className="content-grid">
          <div className="side-stack">
            {opportunities.map((opportunity) => (
              <article key={opportunity.id} className="panel-card">
                <div className="card-head compact">
                  <div>
                    <h2>{opportunity.title}</h2>
                    <p>{opportunity.location || "Location not specified"}</p>
                  </div>
                  <span className="status-pill ok">{opportunity.match_count} matches</span>
                </div>
                <p>{opportunity.description}</p>
                <div className="permission-chips">
                  {(opportunity.trade_tags || []).slice(0, 6).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                  {opportunity.deadline ? <span>Deadline: {opportunity.deadline}</span> : null}
                  {opportunity.contact ? <span>Contact: {opportunity.contact}</span> : null}
                </div>
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
                          <p>{match.member_role}{match.trade_category ? ` · ${match.trade_category}` : ""}</p>
                          <p>{match.reasons[0]}</p>
                        </div>
                        <span>{Math.round(match.match_score * 100)}% · {match.fit_label}</span>
                      </div>
                    ))
                  ) : (
                    <p className="muted-copy opportunity-empty-note">No member matches yet. Refresh matching after members complete more profile details.</p>
                  )}
                </div>
              </article>
            ))}
          </div>

          <article className="panel-card">
            <div className="card-head">
              <div>
                <p className="eyebrow">How members access this</p>
                <h2>Access model</h2>
              </div>
            </div>
            <div className="activity-list">
              <div className="activity-item">
                <div>
                  <h3>Join the workspace</h3>
                  <p>Community members keep using the existing invite link or direct invitation flow.</p>
                </div>
              </div>
              <div className="activity-item">
                <div>
                  <h3>Keep the role model</h3>
                  <p>The current role-based access still applies. Core members can view opportunity matches without needing a separate portal.</p>
                </div>
              </div>
              <div className="activity-item">
                <div>
                  <h3>Improve match quality</h3>
                  <p>Trade category, location, languages, availability, and opportunity preferences all improve who Quorum recommends.</p>
                </div>
              </div>
            </div>
          </article>
        </div>
      )}
    </section>
  );
}
