"use client";

import { FormEvent, useState } from "react";

import { apiPost } from "@/lib/api";

type FundingStream = {
  id: number;
  name: string;
  stream_type: string;
  target_amount: number | null;
  raised_amount: number;
};

type ContributionResponse = {
  payment_reference: string;
  checkout_url: string | null;
  contribution: {
    id: number;
    amount: number;
    status: string;
  };
};

export function DonationForm({
  campaignSlug,
  fundingStreams,
}: {
  campaignSlug: string;
  fundingStreams: FundingStream[];
}) {
  const [streamId, setStreamId] = useState<string>(fundingStreams[0]?.id ? String(fundingStreams[0].id) : "");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [amount, setAmount] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ContributionResponse | null>(null);

  async function submitContribution(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await apiPost<
        ContributionResponse,
        {
          stream_id?: number;
          contributor_name?: string;
          contributor_email?: string;
          amount: number;
          is_anonymous: boolean;
        }
      >(`/public/donate/${campaignSlug}/submissions`, {
        stream_id: streamId ? Number(streamId) : undefined,
        contributor_name: anonymous ? undefined : name.trim() || undefined,
        contributor_email: email.trim() || undefined,
        amount: Number(amount),
        is_anonymous: anonymous,
      });
      setResult(response);
      setAmount("");
      if (response.checkout_url) {
        window.location.assign(response.checkout_url);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to record contribution.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="donation-card form-stack" onSubmit={submitContribution}>
      <div>
        <p className="eyebrow">Contribute</p>
        <h2>Support this campaign</h2>
        <p>Submit your contribution details. The treasurer can confirm it from the campaign ledger.</p>
      </div>

      {fundingStreams.length ? (
        <label>
          Funding stream
          <select value={streamId} onChange={(event) => setStreamId(event.target.value)}>
            {fundingStreams.map((stream) => (
              <option key={stream.id} value={stream.id}>
                {stream.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <label>
        Amount
        <input
          min="1"
          step="100"
          type="number"
          placeholder="5000"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          required
        />
      </label>

      <label>
        Name
        <input
          disabled={anonymous}
          placeholder="Your name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      <label>
        Email
        <input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>

      <label className="checkbox-row">
        <input checked={anonymous} type="checkbox" onChange={(event) => setAnonymous(event.target.checked)} />
        Give anonymously
      </label>

      {error ? <p className="form-error">{error}</p> : null}

      {result ? (
        <div className="donation-success">
          <span className="material-symbols-outlined" aria-hidden="true">
            check_circle
          </span>
          <div>
            <strong>{result.checkout_url ? "Redirecting to Paystack" : "Contribution recorded"}</strong>
            <p>Reference: {result.payment_reference}</p>
          </div>
        </div>
      ) : null}

      <button className="btn-primary wide" disabled={loading} type="submit">
        {loading ? "Preparing..." : "Continue to payment"}
      </button>
    </form>
  );
}
