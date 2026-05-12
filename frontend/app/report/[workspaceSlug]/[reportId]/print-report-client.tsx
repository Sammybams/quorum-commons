"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import BrandWordmark from "@/components/brand-wordmark";
import ThemeToggle from "@/components/theme-toggle";
import { apiGet } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };

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

type ReportDetail = {
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
  context_notes?: string | null;
  generation_error?: string | null;
  data_snapshot: ReportCategory[];
  ai_narrative?: ReportNarrative | null;
};

export default function PrintReportClient({
  params,
}: {
  params: { workspaceSlug: string; reportId: string };
}) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const foundWorkspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        const foundReport = await apiGet<ReportDetail>(`/workspaces/${foundWorkspace.id}/reports/${params.reportId}`);
        setWorkspace(foundWorkspace);
        setReport(foundReport);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load printable report.");
      }
    }

    load();
  }, [params.reportId, params.workspaceSlug]);

  return (
    <main className="print-report-shell">
      <header className="print-report-toolbar no-print">
        <Link href="/" className="stitch-logo" aria-label="Quorum home">
          <BrandWordmark />
        </Link>
        <div className="print-report-toolbar-actions">
          <ThemeToggle />
          <button type="button" className="btn-primary" onClick={() => window.print()}>
            <span className="material-symbols-outlined" aria-hidden="true">
              picture_as_pdf
            </span>
            Print / Save PDF
          </button>
        </div>
      </header>

      {error ? (
        <section className="legal-page">
          <h1>Report unavailable</h1>
          <p>{error}</p>
        </section>
      ) : !report || !workspace ? (
        <section className="legal-page">
          <h1>Preparing report...</h1>
          <p>Loading the printable report view.</p>
        </section>
      ) : (
        <article className="print-report-page" id="report-ready">
          <section className="print-report-cover print-block">
            <div>
              <p className="stitch-badge">Organisational performance report</p>
              <h1>{report.title}</h1>
              <p>{workspace.name}</p>
              <p>{report.period_label || `${report.period_start} to ${report.period_end}`}</p>
              <p>Generated {report.generated_at ? new Date(report.generated_at).toLocaleString() : "just now"}</p>
            </div>
            <div className="print-report-score">
              <strong>{report.overall_score?.toFixed(1) || "-"}</strong>
              <span>{report.overall_grade || report.status}</span>
            </div>
          </section>

          {report.ai_narrative?.period_highlights?.length ? (
            <section className="print-block">
              <h2>Period highlights</h2>
              <div className="report-highlight-row">
                {report.ai_narrative.period_highlights.map((highlight) => (
                  <span key={highlight}>{highlight}</span>
                ))}
              </div>
            </section>
          ) : null}

          {report.ai_narrative?.executive_summary?.length ? (
            <section className="print-block">
              <h2>Executive summary</h2>
              {report.ai_narrative.executive_summary.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </section>
          ) : null}

          <section className="print-block">
            <h2>Scorecard</h2>
            <div className="print-scorecard-table table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Metric</th>
                    <th>Actual</th>
                    <th>Target</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {report.data_snapshot.flatMap((category) =>
                    category.metrics.map((metric, index) => (
                      <tr key={`${category.category_key}-${metric.metric_key}`}>
                        <td>{index === 0 ? category.title : ""}</td>
                        <td>{metric.label}</td>
                        <td>{metric.actual_value}</td>
                        <td>{metric.target_value || "-"}</td>
                        <td>{metric.status.replace("_", " ")}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {report.data_snapshot.map((category) => {
            const commentary = report.ai_narrative?.categories?.find((item) => item.category_key === category.category_key);
            return (
              <section key={category.category_key} className="print-block page-break-soft">
                <div className="print-section-head">
                  <div>
                    <h2>{category.title}</h2>
                    <p>{commentary?.headline_verdict || `${category.category_score.toFixed(1)} / 10 category score`}</p>
                  </div>
                  <span className="report-score-chip compact">
                    <strong>{category.category_score.toFixed(1)}</strong>
                    <span>{Math.round(category.weight * 100)}% weight</span>
                  </span>
                </div>
                <div className="print-two-column">
                  <article className="report-recommendation-card">
                    <h3>What went well</h3>
                    <ul className="stitch-preview-list">
                      {(commentary?.went_well || []).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </article>
                  <article className="report-recommendation-card">
                    <h3>What underperformed</h3>
                    <ul className="stitch-preview-list">
                      {(commentary?.underperformed || []).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                    {commentary?.watch_out_flag ? <p className="report-flag">Watch out: {commentary.watch_out_flag}</p> : null}
                  </article>
                </div>
              </section>
            );
          })}

          {report.ai_narrative?.recommendations?.length ? (
            <section className="print-block page-break-soft">
              <h2>Recommendations</h2>
              <div className="report-recommendation-list">
                {report.ai_narrative.recommendations.map((item, index) => (
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

          {report.ai_narrative?.handover_note?.length ? (
            <section className="print-block page-break-soft">
              <h2>Handover note</h2>
              {report.ai_narrative.handover_note.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </section>
          ) : null}

          {report.context_notes ? (
            <section className="print-block">
              <h2>Generation context</h2>
              <p>{report.context_notes}</p>
            </section>
          ) : null}

          {report.generation_error ? (
            <section className="print-block">
              <h2>Generation note</h2>
              <p>The report used a local fallback narrative because the AI request returned an error: {report.generation_error}</p>
            </section>
          ) : null}
        </article>
      )}
    </main>
  );
}
