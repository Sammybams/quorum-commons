"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };

type ReportSummary = {
  id: number;
  workspace_id: number;
  title: string;
  period_start: string;
  period_end: string;
  period_label?: string | null;
  status: string;
  overall_score?: number | null;
  overall_grade?: string | null;
  generated_at?: string | null;
  created_at: string;
};

type ReportMetric = {
  metric_key: string;
  label: string;
  actual_value: string;
  target_value?: string | null;
  met_target?: boolean | null;
  score?: number | null;
  status: string;
};

type ReportCategory = {
  category_key: string;
  title: string;
  weight: number;
  category_score: number;
  metrics: ReportMetric[];
};

type ReportNarrativeCategory = {
  category_key: string;
  title: string;
  headline_verdict: string;
  went_well: string[];
  underperformed: string[];
  watch_out_flag?: string | null;
};

type ReportNarrative = {
  executive_summary: string[];
  period_highlights: string[];
  categories: ReportNarrativeCategory[];
  recommendations: Array<{
    data_finding: string;
    action: string;
    expected_outcome: string;
    priority: string;
    responsible_role: string;
  }>;
  handover_note: string[];
};

type ReportDetail = ReportSummary & {
  enabled_categories: string[];
  context_notes?: string | null;
  generation_error?: string | null;
  data_snapshot: ReportCategory[];
  ai_narrative?: ReportNarrative | null;
};

const categoryOptions = [
  ["membership", "Membership & engagement"],
  ["dues", "Dues collection"],
  ["events", "Events & programs"],
  ["meetings", "Meetings & governance"],
  ["fundraising", "Fundraising & finance"],
  ["communication", "Communication"],
  ["ai_usage", "AI & platform usage"],
] as const;

function isoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function semesterPreset() {
  const now = new Date();
  const month = now.getMonth() + 1;
  const startMonth = month <= 6 ? 1 : 7;
  const endMonth = month <= 6 ? 6 : 12;
  return {
    start: `${now.getFullYear()}-${String(startMonth).padStart(2, "0")}-01`,
    end: `${now.getFullYear()}-${String(endMonth).padStart(2, "0")}-${endMonth === 6 ? "30" : "31"}`,
    label: month <= 6 ? `${now.getFullYear()} First Semester` : `${now.getFullYear()} Second Semester`,
  };
}

export default function ReportsPage({ params }: { params: { workspaceSlug: string } }) {
  const preset = useMemo(() => semesterPreset(), []);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [selected, setSelected] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("Semester Audit Report");
  const [periodStart, setPeriodStart] = useState(preset.start);
  const [periodEnd, setPeriodEnd] = useState(preset.end);
  const [periodLabel, setPeriodLabel] = useState(preset.label);
  const [contextNotes, setContextNotes] = useState("");
  const [enabledCategories, setEnabledCategories] = useState<string[]>(categoryOptions.map(([key]) => key));

  useEffect(() => {
    async function load() {
      try {
        const foundWorkspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        const foundReports = await apiGet<ReportSummary[]>(`/workspaces/${foundWorkspace.id}/reports`);
        setWorkspace(foundWorkspace);
        setReports(foundReports);
        if (foundReports[0]) {
          const detail = await apiGet<ReportDetail>(`/workspaces/${foundWorkspace.id}/reports/${foundReports[0].id}`);
          setSelected(detail);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load reports.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.workspaceSlug]);

  async function openReport(reportId: number) {
    if (!workspace) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      const detail = await apiGet<ReportDetail>(`/workspaces/${workspace.id}/reports/${reportId}`);
      setSelected(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load report.");
    } finally {
      setWorking(false);
    }
  }

  async function generateReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      const report = await apiPost<
        ReportDetail,
        {
          title: string;
          period_start: string;
          period_end: string;
          period_label?: string;
          enabled_categories: string[];
          context_notes?: string;
        }
      >(`/workspaces/${workspace.id}/reports/generate`, {
        title: title.trim(),
        period_start: periodStart,
        period_end: periodEnd,
        period_label: periodLabel.trim() || undefined,
        enabled_categories: enabledCategories,
        context_notes: contextNotes.trim() || undefined,
      });
      setReports((current) => [report, ...current.filter((item) => item.id !== report.id)]);
      setSelected(report);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to generate report.");
    } finally {
      setWorking(false);
    }
  }

  function applyPreset(type: "semester" | "quarter" | "year") {
    const now = new Date();
    if (type === "semester") {
      const next = semesterPreset();
      setPeriodStart(next.start);
      setPeriodEnd(next.end);
      setPeriodLabel(next.label);
      return;
    }
    if (type === "quarter") {
      const start = new Date(now);
      start.setDate(now.getDate() - 90);
      setPeriodStart(isoDate(start));
      setPeriodEnd(isoDate(now));
      setPeriodLabel("Last 90 Days");
      return;
    }
    setPeriodStart(`${now.getFullYear()}-01-01`);
    setPeriodEnd(isoDate(now));
    setPeriodLabel(`${now.getFullYear()} Session to Date`);
  }

  function toggleCategory(categoryKey: string) {
    setEnabledCategories((current) =>
      current.includes(categoryKey) ? current.filter((item) => item !== categoryKey) : [...current, categoryKey],
    );
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Reports</p>
          <h1>AI analytics reports</h1>
          <p>{workspace?.name || params.workspaceSlug}</p>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="report-layout">
        <article className="panel-card report-builder-card">
          <div className="card-head compact">
            <div>
              <h2>Generate report</h2>
              <p>Compile the period, score each category, then let Claude write the audit narrative.</p>
            </div>
          </div>

          <form className="form-stack" onSubmit={generateReport}>
            <label>
              Report title
              <input value={title} onChange={(event) => setTitle(event.target.value)} required />
            </label>

            <div className="report-preset-row">
              <button type="button" className="btn-ghost" onClick={() => applyPreset("semester")}>
                Semester
              </button>
              <button type="button" className="btn-ghost" onClick={() => applyPreset("quarter")}>
                Last 90 days
              </button>
              <button type="button" className="btn-ghost" onClick={() => applyPreset("year")}>
                Session to date
              </button>
            </div>

            <div className="form-two">
              <label>
                Period start
                <input type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} required />
              </label>
              <label>
                Period end
                <input type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} required />
              </label>
            </div>

            <label>
              Period label
              <input value={periodLabel} onChange={(event) => setPeriodLabel(event.target.value)} />
            </label>

            <div className="report-category-picker">
              {categoryOptions.map(([key, label]) => (
                <label key={key} className="checkbox-row">
                  <input type="checkbox" checked={enabledCategories.includes(key)} onChange={() => toggleCategory(key)} />
                  <span>{label}</span>
                </label>
              ))}
            </div>

            <label>
              Context notes for Claude
              <textarea
                rows={5}
                value={contextNotes}
                onChange={(event) => setContextNotes(event.target.value)}
                placeholder="Examples: We prioritized sponsor mobilisation this semester. Leadership turnover affected treasury follow-up. Welfare activities happened offline and should be interpreted carefully."
              />
            </label>

            <button type="submit" className="btn-primary" disabled={working || enabledCategories.length === 0}>
              {working ? "Generating..." : "Generate audit report"}
            </button>
          </form>
        </article>

        <div className="report-content-stack">
          <article className="panel-card">
            <div className="card-head compact">
              <h2>Generated reports</h2>
              <span className="status-pill">{reports.length}</span>
            </div>
            {loading ? (
              <p className="empty-block">Loading reports...</p>
            ) : reports.length === 0 ? (
              <div className="empty-state">
                <span className="material-symbols-outlined" aria-hidden="true">
                  analytics
                </span>
                <h2>No reports yet</h2>
                <p>Generate your first audit report to review the semester with real numbers and AI commentary.</p>
              </div>
            ) : (
              <div className="report-list">
                {reports.map((report) => (
                  <button
                    key={report.id}
                    type="button"
                    className={`report-list-card ${selected?.id === report.id ? "active" : ""}`}
                    onClick={() => openReport(report.id)}
                  >
                    <div>
                      <strong>{report.title}</strong>
                      <span>{report.period_label || `${report.period_start} to ${report.period_end}`}</span>
                    </div>
                    <div className="report-list-meta">
                      <span className={`status-pill ${report.status === "complete" ? "ok" : "pending"}`}>{report.status}</span>
                      <strong>{report.overall_score ? `${report.overall_score.toFixed(1)} / 10` : "-"}</strong>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </article>

          <article className="panel-card report-preview-card">
            {!selected ? (
              <div className="empty-state">
                <span className="material-symbols-outlined" aria-hidden="true">
                  auto_stories
                </span>
                <h2>Select a report</h2>
                <p>Generated reports will show their narrative, scorecard, and recommendations here.</p>
              </div>
            ) : (
              <div className="report-preview">
                <div className="report-preview-hero">
                  <div>
                    <p className="eyebrow">Audit report</p>
                    <h2>{selected.title}</h2>
                    <p>{selected.period_label || `${selected.period_start} to ${selected.period_end}`}</p>
                  </div>
                  <div className="report-hero-actions">
                    <div className="report-score-chip">
                      <strong>{selected.overall_score?.toFixed(1) || "-"}</strong>
                      <span>{selected.overall_grade || selected.status}</span>
                    </div>
                    <Link
                      href={`/report/${params.workspaceSlug}/${selected.id}`}
                      className="btn-secondary"
                      target="_blank"
                      rel="noreferrer"
                    >
                      <span className="material-symbols-outlined" aria-hidden="true">
                        print
                      </span>
                      Print / Save PDF
                    </Link>
                  </div>
                </div>

                {selected.ai_narrative?.period_highlights?.length ? (
                  <div className="report-highlight-row">
                    {selected.ai_narrative.period_highlights.map((highlight) => (
                      <span key={highlight}>{highlight}</span>
                    ))}
                  </div>
                ) : null}

                {selected.ai_narrative?.executive_summary?.length ? (
                  <section className="report-section">
                    <h3>Executive summary</h3>
                    {selected.ai_narrative.executive_summary.map((paragraph) => (
                      <p key={paragraph}>{paragraph}</p>
                    ))}
                  </section>
                ) : null}

                <section className="report-section">
                  <h3>Category scorecard</h3>
                  <div className="report-category-grid">
                    {selected.data_snapshot.map((category) => {
                      const commentary = selected.ai_narrative?.categories?.find((item) => item.category_key === category.category_key);
                      return (
                        <article key={category.category_key} className="report-category-card">
                          <div className="report-category-head">
                            <div>
                              <strong>{category.title}</strong>
                              <span>{category.category_score.toFixed(1)} / 10</span>
                            </div>
                            <span className="status-pill">{Math.round(category.weight * 100)}%</span>
                          </div>
                          {commentary ? <p>{commentary.headline_verdict}</p> : null}
                          <div className="table-wrap">
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>Metric</th>
                                  <th>Actual</th>
                                  <th>Target</th>
                                  <th>Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {category.metrics.map((metric) => (
                                  <tr key={metric.metric_key}>
                                    <td>{metric.label}</td>
                                    <td>{metric.actual_value}</td>
                                    <td>{metric.target_value || "-"}</td>
                                    <td>
                                      <span className={`status-pill ${metric.status === "excellent" || metric.status === "good" ? "ok" : metric.status === "informational" ? "" : "pending"}`}>
                                        {metric.status.replace("_", " ")}
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          {commentary?.watch_out_flag ? <p className="report-flag">Watch out: {commentary.watch_out_flag}</p> : null}
                        </article>
                      );
                    })}
                  </div>
                </section>

                {selected.ai_narrative?.recommendations?.length ? (
                  <section className="report-section">
                    <h3>Recommendations</h3>
                    <div className="report-recommendation-list">
                      {selected.ai_narrative.recommendations.map((item, index) => (
                        <article key={`${item.data_finding}-${index}`} className="report-recommendation-card">
                          <div className="report-recommendation-head">
                            <strong>{item.priority.toUpperCase()}</strong>
                            <span>{item.responsible_role}</span>
                          </div>
                          <p>
                            <strong>{item.data_finding}</strong>
                          </p>
                          <p>{item.action}</p>
                          <p>{item.expected_outcome}</p>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}

                {selected.ai_narrative?.handover_note?.length ? (
                  <section className="report-section">
                    <h3>Handover note</h3>
                    {selected.ai_narrative.handover_note.map((paragraph) => (
                      <p key={paragraph}>{paragraph}</p>
                    ))}
                  </section>
                ) : null}

                {selected.context_notes ? (
                  <section className="report-section">
                    <h3>Generation context</h3>
                    <p>{selected.context_notes}</p>
                  </section>
                ) : null}

                {selected.generation_error ? <p className="status-note">AI fallback used: {selected.generation_error}</p> : null}
              </div>
            )}
          </article>
        </div>
      </section>
    </section>
  );
}
