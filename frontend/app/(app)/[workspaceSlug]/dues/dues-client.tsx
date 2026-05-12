"use client";

import { FormEvent, useMemo, useState } from "react";

import { apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type DuesCycle = { id: number; workspace_id: number; name: string; amount: number; deadline?: string | null };
type DuesPayment = {
  id: number;
  member_id?: number | null;
  member_name?: string | null;
  amount: number;
  method: string;
  provider?: string | null;
  gateway_ref?: string | null;
  provider_transaction_ref?: string | null;
  virtual_account_number?: string | null;
  account_name?: string | null;
  bank_name?: string | null;
  expires_at?: string | null;
  verification_status?: string | null;
  status: string;
  created_at: string;
};
type Member = { id: number; full_name: string; email?: string | null };
type CheckoutResponse = {
  payment: DuesPayment;
  payment_reference: string;
  checkout_url: string | null;
  access_code: string | null;
  provider: string;
  virtual_account_number?: string | null;
  account_name?: string | null;
  bank_name?: string | null;
  expires_at?: string | null;
};

export default function DuesClient({
  workspace,
  initialCycles,
  initialPayments,
  members,
}: {
  workspace: Workspace;
  initialCycles: DuesCycle[];
  initialPayments: DuesPayment[];
  members: Member[];
}) {
  const [cycles, setCycles] = useState(initialCycles);
  const [payments, setPayments] = useState(initialPayments);
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [deadline, setDeadline] = useState("");
  const [selectedCycleId, setSelectedCycleId] = useState<number | null>(initialCycles[0]?.id || null);
  const [memberId, setMemberId] = useState<string>("");
  const [email, setEmail] = useState("");
  const [checkout, setCheckout] = useState<CheckoutResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalPaid = useMemo(
    () => payments.filter((payment) => payment.status === "paid").reduce((sum, payment) => sum + payment.amount, 0),
    [payments],
  );

  async function createCycle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const cycle = await apiPost<DuesCycle, { name: string; amount: number; deadline?: string }>(
        `/workspaces/${workspace.id}/dues-cycles`,
        {
          name: name.trim(),
          amount: Number(amount),
          deadline: deadline.trim() || undefined,
        },
      );
      setCycles((current) => [cycle, ...current]);
      setSelectedCycleId(cycle.id);
      setModalOpen(false);
      setName("");
      setAmount("");
      setDeadline("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create dues cycle.");
    } finally {
      setLoading(false);
    }
  }

  async function initializeCheckout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCycleId) {
      setError("Select a dues cycle first.");
      return;
    }

    setLoading(true);
    setError(null);
    setCheckout(null);

    try {
      const response = await apiPost<
        CheckoutResponse,
        { member_id?: number; email?: string }
      >(`/workspaces/${workspace.id}/dues-cycles/${selectedCycleId}/payments/checkout`, {
        member_id: memberId ? Number(memberId) : undefined,
        email: email.trim() || undefined,
      });
      setCheckout(response);
      setPayments((current) => [response.payment, ...current]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to initialize payment.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmPayment(paymentId: number) {
    setLoading(true);
    setError(null);

    try {
      const payment = await apiPost<DuesPayment, Record<string, never>>(
        `/workspaces/${workspace.id}/dues-payments/${paymentId}/confirm`,
        {},
      );
      setPayments((current) => current.map((item) => (item.id === payment.id ? payment : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to confirm payment.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Dues</p>
          <h1>Dues cycles</h1>
          <p>{workspace.name}</p>
        </div>
        <button type="button" className="btn-primary" onClick={() => setModalOpen(true)}>
          <span className="material-symbols-outlined" aria-hidden="true">
            add
          </span>
          New Cycle
        </button>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="metrics-grid">
        <article className="metric-card primary">
          <span className="material-symbols-outlined" aria-hidden="true">
            payments
          </span>
          <small>Total collected</small>
          <strong>NGN {totalPaid.toLocaleString()}</strong>
        </article>
        <article className="metric-card">
          <span className="material-symbols-outlined" aria-hidden="true">
            receipt_long
          </span>
          <small>Cycles</small>
          <strong>{cycles.length}</strong>
          <p>Published dues cycles</p>
        </article>
        <article className="metric-card">
          <span className="material-symbols-outlined" aria-hidden="true">
            pending_actions
          </span>
          <small>Pending review</small>
          <strong>{payments.filter((payment) => payment.status === "pending" || payment.status === "initiated").length}</strong>
          <p>Awaiting webhook or admin confirmation</p>
        </article>
        <article className="metric-card">
          <span className="material-symbols-outlined" aria-hidden="true">
            check_circle
          </span>
          <small>Confirmed</small>
          <strong>{payments.filter((payment) => payment.status === "paid").length}</strong>
          <p>Payments confirmed</p>
        </article>
      </section>

      <section className="content-grid">
        <article className="panel-card cycles-card">
          <h2>Active cycles</h2>
          {cycles.length === 0 ? (
            <div className="empty-state cycles-empty">
              <span className="material-symbols-outlined" aria-hidden="true">
                receipt_long
              </span>
              <h2>No dues cycle yet</h2>
              <p>Create a cycle before collecting or tracking member dues.</p>
              <button type="button" className="btn-primary" onClick={() => setModalOpen(true)}>
                Create cycle
              </button>
            </div>
          ) : (
            <div className="mini-list roomy">
              {cycles.map((cycle) => (
                <div key={cycle.id}>
                  <span>{cycle.name}</span>
                  <strong>
                    NGN {cycle.amount.toLocaleString()} {cycle.deadline ? `· ${cycle.deadline}` : ""}
                  </strong>
                  <button type="button" className="btn-secondary" onClick={() => setSelectedCycleId(cycle.id)}>
                    Collect
                  </button>
                </div>
              ))}
            </div>
          )}
        </article>

        <aside className="side-stack">
          <article className="panel-card">
            <h2>Generate Squad collection details</h2>
            <form className="form-stack" onSubmit={initializeCheckout}>
              <label>
                Cycle
                <select value={selectedCycleId || ""} onChange={(event) => setSelectedCycleId(Number(event.target.value))}>
                  {cycles.map((cycle) => (
                    <option key={cycle.id} value={cycle.id}>
                      {cycle.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Member
                <select value={memberId} onChange={(event) => setMemberId(event.target.value)}>
                  <option value="">No member selected</option>
                  {members.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Email override
                <input
                  type="email"
                  placeholder="payer@example.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
              <button type="submit" className="btn-secondary" disabled={loading || cycles.length === 0}>
                Generate payment details
              </button>
            </form>

            {checkout ? (
              <div className="payment-link-box">
                <span>{checkout.payment_reference}</span>
                <strong>Squad virtual account ready</strong>
                <p>
                  {checkout.account_name || "Account"} · {checkout.bank_name || "Bank"}
                </p>
                <p>{checkout.virtual_account_number || "Account number pending"}</p>
                {checkout.expires_at ? <p>Expires: {checkout.expires_at}</p> : null}
                {checkout.checkout_url ? (
                  <a className="btn-primary" href={checkout.checkout_url} target="_blank" rel="noreferrer">
                    Open hosted payment page
                  </a>
                ) : (
                  <p>Share this account number with the payer. Once Squad confirms the transfer, Quorum will update the ledger automatically.</p>
                )}
              </div>
            ) : null}
          </article>
        </aside>
      </section>

      <article className="panel-card">
        <div className="card-head">
          <h2>Payment ledger</h2>
          <span className="status-pill">{payments.length} records</span>
        </div>
        {payments.length === 0 ? (
          <div className="empty-block">
            <span className="material-symbols-outlined" aria-hidden="true">
              account_balance_wallet
            </span>
            <h3>No payments yet</h3>
            <p>Squad confirmations and manual receipts will appear here.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Amount</th>
                  <th>Provider</th>
                  <th>Reference</th>
                  <th>Collection</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>{payment.member_name || "Unassigned payment"}</td>
                    <td>NGN {payment.amount.toLocaleString()}</td>
                    <td>{payment.provider || payment.method}</td>
                    <td>{payment.gateway_ref || payment.provider_transaction_ref || "-"}</td>
                    <td>
                      {payment.virtual_account_number ? (
                        <>
                          <div>{payment.virtual_account_number}</div>
                          <small>{payment.bank_name || payment.account_name || "Squad virtual account"}</small>
                        </>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>
                      <span className={`status-pill ${payment.status === "paid" ? "ok" : "pending"}`}>
                        {payment.status}
                      </span>
                    </td>
                    <td>
                      {payment.status === "paid" ? (
                        "-"
                      ) : (
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={loading}
                          onClick={() => confirmPayment(payment.id)}
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
        )}
      </article>

      {modalOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setModalOpen(false)}>
          <section className="modal-card" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="card-head compact">
              <div>
                <p className="eyebrow">Dues</p>
                <h2>New dues cycle</h2>
              </div>
              <button type="button" className="icon-button" aria-label="Close dues modal" onClick={() => setModalOpen(false)}>
                <span className="material-symbols-outlined" aria-hidden="true">
                  close
                </span>
              </button>
            </div>
            <form className="form-stack" onSubmit={createCycle}>
              <label>
                Cycle name
                <input placeholder="2026 departmental dues" value={name} onChange={(event) => setName(event.target.value)} required />
              </label>
              <label>
                Amount
                <input min="1" type="number" value={amount} onChange={(event) => setAmount(event.target.value)} required />
              </label>
              <label>
                Deadline
                <input placeholder="May 30, 2026" value={deadline} onChange={(event) => setDeadline(event.target.value)} />
              </label>
              <div className="form-actions">
                <button type="button" className="btn-ghost" onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={loading}>
                  {loading ? "Creating..." : "Create cycle"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </section>
  );
}
