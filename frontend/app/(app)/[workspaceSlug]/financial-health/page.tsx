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
