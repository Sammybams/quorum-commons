"use client";

import { useEffect, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";
import { resolveWorkspace } from "@/lib/workspace-client";

type Workspace = { id: number; slug: string; name: string };
type HealthCategory = {
  category_key: string;
  title: string;
  score: number;
  status: string;
  summary: string;
};
type HealthMetric = {
  key: string;
  label: string;
  value: string;
  trend: string;
};
type HealthEvidence = {
  evidence_type: string;
  title: string;
  detail: string;
  linked_record_label?: string | null;
  verification_state?: string | null;
  created_at: string;
};
type HealthHistoryPoint = {
  label: string;
  overall_score: number;
  overall_grade: string;
  created_at: string;
};
type PartnerProfile = {
  headline: string;
  confidence_label: string;
  summary: string;
  strengths: string[];
  watchouts: string[];
  recommended_next_step: string;
};
type HealthSnapshot = {
  id?: number | null;
  workspace_id: number;
  overall_score: number;
  overall_grade: string;
  summary: string;
  strengths: string[];
  watchouts: string[];
  categories: HealthCategory[];
  key_metrics: HealthMetric[];
  evidence_trail: HealthEvidence[];
  history: HealthHistoryPoint[];
  partner_profile?: PartnerProfile | null;
  created_at: string;
};

export default function FinancialHealthPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [snapshot, setSnapshot] = useState<HealthSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadSnapshot(slug: string) {
    const foundWorkspace = await resolveWorkspace(slug);
    const foundSnapshot = await apiGet<HealthSnapshot>(`/workspaces/${foundWorkspace.id}/financial-health`);
    setWorkspace(foundWorkspace);
    setSnapshot(foundSnapshot);
  }

  useEffect(() => {
    async function load() {
      try {
        await loadSnapshot(params.workspaceSlug);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load financial health.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [params.workspaceSlug]);

  async function refreshSnapshot() {
    if (!workspace) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const next = await apiPost<HealthSnapshot, Record<string, never>>(`/workspaces/${workspace.id}/financial-health/refresh`, {});
      setSnapshot(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh financial health.");
    } finally {
      setRefreshing(false);
    }
  }

  function humanizeVerificationState(value?: string | null) {
    if (!value) return "tracked";
    return value.replaceAll("_", " ");
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Financial Health</p>
          <h1>Community profile</h1>
          <p>{workspace?.name || params.workspaceSlug}</p>
        </div>
        <button type="button" className="btn-secondary" disabled={refreshing || !workspace} onClick={refreshSnapshot}>
          {refreshing ? "Refreshing..." : "Refresh score"}
        </button>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      {loading || !snapshot ? (
        <article className="panel-card">
          <p className="empty-block">Loading financial health...</p>
        </article>
      ) : (
        <>
          <section className="metrics-grid">
            <article className="metric-card primary">
              <small>Overall score</small>
              <strong>{snapshot.overall_score.toFixed(1)}/10</strong>
              <p>{snapshot.overall_grade}</p>
            </article>
            {snapshot.key_metrics.map((metric) => (
              <article key={metric.key} className="metric-card">
                <small>{metric.label}</small>
                <strong>{metric.value}</strong>
                <p>{metric.trend}</p>
              </article>
            ))}
          </section>

          <section className="content-grid">
            <article className="panel-card large">
              <div className="card-head">
                <div>
                  <p className="eyebrow">Summary</p>
                  <h2>Current financial position</h2>
                </div>
              </div>
              <p>{snapshot.summary}</p>
              <div className="activity-list">
                {snapshot.categories.map((category) => (
                  <div key={category.category_key} className="activity-item">
                    <div>
                      <h3>{category.title}</h3>
                      <p>{category.summary}</p>
                    </div>
                    <span>{category.score.toFixed(1)} · {category.status}</span>
                  </div>
                ))}
              </div>
            </article>

            <div className="side-stack">
              {snapshot.partner_profile ? (
                <article className="panel-card">
                  <div className="card-head compact">
                    <h2>Partner-ready view</h2>
                  </div>
                  <p><strong>{snapshot.partner_profile.headline}</strong></p>
                  <p className="muted-copy">{snapshot.partner_profile.confidence_label}</p>
                  <p>{snapshot.partner_profile.summary}</p>
                  <p className="muted-copy">{snapshot.partner_profile.recommended_next_step}</p>
                </article>
              ) : null}

              <article className="panel-card">
                <div className="card-head compact">
                  <h2>Trend line</h2>
                </div>
                <div className="activity-list">
                  {snapshot.history.map((point) => (
                    <div key={`${point.label}-${point.created_at}`} className="activity-item">
                      <div>
                        <h3>{point.label}</h3>
                        <p>{point.overall_grade}</p>
                      </div>
                      <span>{point.overall_score.toFixed(1)}/10</span>
                    </div>
                  ))}
                </div>
              </article>

              <article className="panel-card">
                <div className="card-head compact">
                  <h2>Evidence trail</h2>
                </div>
                {snapshot.evidence_trail.length ? (
                  <div className="activity-list">
                    {snapshot.evidence_trail.map((item) => (
                      <div key={`${item.evidence_type}-${item.created_at}-${item.title}`} className="activity-item">
                        <div>
                          <h3>{item.title}</h3>
                          <p>{item.detail}</p>
                          {item.linked_record_label ? <p className="muted-copy">Linked to {item.linked_record_label}</p> : null}
                        </div>
                        <span>{humanizeVerificationState(item.verification_state)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted-copy">Evidence items will appear here as Quorum verifies receipts, dues, and contributions.</p>
                )}
              </article>

              <article className="panel-card">
                <div className="card-head compact">
                  <h2>Strengths</h2>
                </div>
                <ul className="bullet-list">
                  {snapshot.strengths.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>

              <article className="panel-card">
                <div className="card-head compact">
                  <h2>Watchouts</h2>
                </div>
                <ul className="bullet-list">
                  {snapshot.watchouts.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
            </div>
          </section>
        </>
      )}
    </section>
  );
}
