"use client";

import { FormEvent, useMemo, useState } from "react";

import { apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Campaign = {
  id: number;
  workspace_id: number;
  name: string;
  slug: string;
  target_amount: number;
  raised_amount: number;
  status: string;
};
type FundingStream = {
  id: number;
  workspace_id: number;
  campaign_id: number;
  name: string;
  stream_type: string;
  target_amount: number | null;
  raised_amount: number;
};
type Contribution = {
  id: number;
  stream_id: number | null;
  contributor_name: string | null;
  contributor_email: string | null;
  stream_name: string | null;
  amount: number;
  method: string;
  gateway_ref: string | null;
  status: string;
  created_at: string;
};
type CampaignDetail = Campaign & {
  funding_streams: FundingStream[];
  contributions: Contribution[];
  contributor_count: number;
};

export default function CampaignsClient({
  workspace,
  initialCampaigns,
  initialDetail,
}: {
  workspace: Workspace;
  initialCampaigns: Campaign[];
  initialDetail: CampaignDetail | null;
}) {
  const [campaigns, setCampaigns] = useState(initialCampaigns);
  const [campaign, setCampaign] = useState<CampaignDetail | null>(initialDetail);
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [streamName, setStreamName] = useState("");
  const [streamTarget, setStreamTarget] = useState("");
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const progress = campaign
    ? Math.min(100, Math.round((campaign.raised_amount / Math.max(campaign.target_amount, 1)) * 100))
    : 0;
  const publicUrl = useMemo(() => {
    if (!campaign) {
      return "";
    }
    if (typeof window === "undefined") {
      return `/donate/${campaign.slug}`;
    }
    return `${window.location.origin}/donate/${campaign.slug}`;
  }, [campaign]);

  async function copyPublicLink() {
    if (!publicUrl) {
      return;
    }
    await navigator.clipboard.writeText(publicUrl);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const created = await apiPost<Campaign, { name: string; slug: string; target_amount: number }>(
        `/workspaces/${workspace.id}/campaigns`,
        {
          name: name.trim(),
          slug: slugify(name),
          target_amount: Number(targetAmount),
        },
      );
      const detail: CampaignDetail = {
        ...created,
        funding_streams: [],
        contributions: [],
        contributor_count: 0,
      };
      setCampaigns((current) => [created, ...current]);
      setCampaign(detail);
      setModalOpen(false);
      setName("");
      setTargetAmount("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create campaign.");
    } finally {
      setLoading(false);
    }
  }

  async function createStream(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!campaign) {
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const stream = await apiPost<
        FundingStream,
        { name: string; stream_type: string; target_amount?: number }
      >(`/workspaces/${workspace.id}/campaigns/${campaign.id}/streams`, {
        name: streamName.trim(),
        stream_type: "general",
        target_amount: streamTarget ? Number(streamTarget) : undefined,
      });
      setCampaign({
        ...campaign,
        funding_streams: [stream, ...campaign.funding_streams],
      });
      setStreamName("");
      setStreamTarget("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add funding stream.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmContribution(contributionId: number) {
    if (!campaign) {
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const confirmed = await apiPost<Contribution, Record<string, never>>(
        `/workspaces/${workspace.id}/campaigns/${campaign.id}/contributions/${contributionId}/confirm`,
        {},
      );
      setCampaign({
        ...campaign,
        raised_amount: campaign.raised_amount + confirmed.amount,
        contributor_count: campaign.contributor_count + 1,
        funding_streams: campaign.funding_streams.map((stream) =>
          stream.id === confirmed.stream_id
            ? { ...stream, raised_amount: stream.raised_amount + confirmed.amount }
            : stream,
        ),
        contributions: campaign.contributions.map((item) => (item.id === confirmed.id ? confirmed : item)),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to confirm contribution.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Fundraising</p>
          <h1>{campaign ? campaign.name : "Campaigns"}</h1>
          <p>
            {workspace.name} · {campaigns.length} {campaigns.length === 1 ? "campaign" : "campaigns"}
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={() => setModalOpen(true)}>
          <span className="material-symbols-outlined" aria-hidden="true">
            add
          </span>
          New Campaign
        </button>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      {campaign ? (
        <>
          <section className="fund-grid">
            <article className="fund-hero">
              <div>
                <p className="eyebrow">Raised so far</p>
                <strong>NGN {campaign.raised_amount.toLocaleString()}</strong>
              </div>
              <div>
                <p>
                  {progress}% of NGN {campaign.target_amount.toLocaleString()} from {campaign.contributor_count}{" "}
                  contributors
                </p>
                <div className="progress-track">
                  <span style={{ width: `${progress}%` }} />
                </div>
              </div>
            </article>

            <article className="panel-card">
              <div className="card-head compact">
                <h2>Campaign status</h2>
                <span className={`status-pill ${campaign.status === "active" ? "ok" : "pending"}`}>
                  {campaign.status}
                </span>
              </div>
              <div className="mini-list">
                <div>
                  <span>Public donation page</span>
                  <strong>{campaign.slug}</strong>
                </div>
                <div>
                  <span>Public link</span>
                  <button type="button" className="btn-secondary" onClick={copyPublicLink}>
                    {copied ? "Copied" : "Copy link"}
                  </button>
                </div>
              </div>
            </article>
          </section>

          <section className="content-grid">
            <article className="panel-card">
              <div className="card-head">
                <h2>Contribution ledger</h2>
                <span className="status-pill">{campaign.contributions.length} records</span>
              </div>
              {campaign.contributions.length ? (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Contributor</th>
                        <th>Stream</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaign.contributions.map((contribution) => (
                        <tr key={contribution.id}>
                          <td>
                            <strong>{contribution.contributor_name || "Anonymous"}</strong>
                            <br />
                            <span>{contribution.contributor_email || contribution.gateway_ref || "-"}</span>
                          </td>
                          <td>{contribution.stream_name || "General"}</td>
                          <td>NGN {contribution.amount.toLocaleString()}</td>
                          <td>
                            <span className={`status-pill ${contribution.status === "confirmed" ? "ok" : "pending"}`}>
                              {contribution.status}
                            </span>
                          </td>
                          <td>
                            {contribution.status === "confirmed" ? (
                              "-"
                            ) : (
                              <button
                                type="button"
                                className="btn-secondary"
                                disabled={loading}
                                onClick={() => confirmContribution(contribution.id)}
                              >
                                Confirm
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-block">
                  <span className="material-symbols-outlined" aria-hidden="true">
                    receipt_long
                  </span>
                  <h3>No contributions yet</h3>
                  <p>Public submissions and confirmed donations will appear here.</p>
                </div>
              )}
            </article>

            <aside className="side-stack">
              <article className="panel-card">
                <div className="card-head compact">
                  <h2>Funding streams</h2>
                </div>
                {campaign.funding_streams.length ? (
                  <div className="mini-list">
                    {campaign.funding_streams.map((stream) => (
                      <div key={stream.id}>
                        <span>{stream.name}</span>
                        <strong>
                          NGN {stream.raised_amount.toLocaleString()}
                          {stream.target_amount ? ` / ${stream.target_amount.toLocaleString()}` : ""}
                        </strong>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted-copy">Split a campaign into streams such as welfare, venue, logistics, or media.</p>
                )}
              </article>

              <article className="panel-card">
                <h2>Add stream</h2>
                <form className="form-stack" onSubmit={createStream}>
                  <label>
                    Stream name
                    <input value={streamName} onChange={(event) => setStreamName(event.target.value)} required />
                  </label>
                  <label>
                    Target amount
                    <input
                      min="1"
                      type="number"
                      value={streamTarget}
                      onChange={(event) => setStreamTarget(event.target.value)}
                    />
                  </label>
                  <button type="submit" className="btn-secondary" disabled={loading}>
                    Add funding stream
                  </button>
                </form>
              </article>
            </aside>
          </section>
        </>
      ) : (
        <article className="panel-card campaigns-empty-card">
          <div className="empty-state campaigns-empty">
            <span className="material-symbols-outlined" aria-hidden="true">
              payments
            </span>
            <h2>No campaigns yet</h2>
            <p>Create a fundraising campaign when your student body is ready to receive contributions.</p>
            <button type="button" className="btn-primary" onClick={() => setModalOpen(true)}>
              Create first campaign
            </button>
          </div>
        </article>
      )}

      {modalOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setModalOpen(false)}>
          <section className="modal-card" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="card-head compact">
              <div>
                <p className="eyebrow">Fundraising</p>
                <h2>New campaign</h2>
              </div>
              <button type="button" className="icon-button" aria-label="Close campaign modal" onClick={() => setModalOpen(false)}>
                <span className="material-symbols-outlined" aria-hidden="true">
                  close
                </span>
              </button>
            </div>
            <form className="form-stack" onSubmit={createCampaign}>
              <label>
                Campaign name
                <input value={name} onChange={(event) => setName(event.target.value)} required />
              </label>
              <label>
                Target amount
                <input
                  min="1"
                  type="number"
                  value={targetAmount}
                  onChange={(event) => setTargetAmount(event.target.value)}
                  required
                />
              </label>
              {name ? <div className="portal-preview">/donate/{slugify(name)}</div> : null}
              <div className="form-actions">
                <button type="button" className="btn-ghost" onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={loading}>
                  {loading ? "Creating..." : "Create campaign"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function slugify(value: string) {
  return (
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "campaign"
  );
}
