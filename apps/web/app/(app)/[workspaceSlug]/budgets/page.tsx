"use client";

import { FormEvent, useEffect, useState } from "react";

import { API_BASE_URL, apiGet, apiPost } from "@/lib/api";

type Workspace = { id: number; slug: string; name: string };
type Budget = {
  id: number;
  name: string;
  status: string;
  planned_total: number;
  actual_total: number;
  period_label?: string | null;
};
type BudgetDetail = Budget & {
  description?: string | null;
  lines: Array<{ id: number; name: string; planned_amount: number; actual_amount: number; notes?: string | null }>;
};

export default function BudgetsPage({ params }: { params: { workspaceSlug: string } }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [selectedBudget, setSelectedBudget] = useState<BudgetDetail | null>(null);
  const [budgetName, setBudgetName] = useState("");
  const [periodLabel, setPeriodLabel] = useState("");
  const [lineName, setLineName] = useState("");
  const [plannedAmount, setPlannedAmount] = useState("");
  const [lineNotes, setLineNotes] = useState("");
  const [expenseAmounts, setExpenseAmounts] = useState<Record<number, string>>({});
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const found = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
        setWorkspace(found);
        const loadedBudgets = await apiGet<Budget[]>(`/workspaces/${found.id}/budgets`);
        setBudgets(loadedBudgets);
        if (loadedBudgets[0]) {
          setSelectedBudget(await apiGet<BudgetDetail>(`/workspaces/${found.id}/budgets/${loadedBudgets[0].id}`));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load budgets.");
      }
    }
    load();
  }, [params.workspaceSlug]);

  async function selectBudget(budgetId: number) {
    if (!workspace) {
      return;
    }
    setSelectedBudget(await apiGet<BudgetDetail>(`/workspaces/${workspace.id}/budgets/${budgetId}`));
  }

  async function createBudget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      const budget = await apiPost<Budget, { name: string; period_label?: string }>(`/workspaces/${workspace.id}/budgets`, {
        name: budgetName.trim(),
        period_label: periodLabel.trim() || undefined,
      });
      const nextBudgets = [budget, ...budgets];
      setBudgets(nextBudgets);
      setBudgetName("");
      setPeriodLabel("");
      await selectBudget(budget.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create budget.");
    } finally {
      setWorking(false);
    }
  }

  async function addLine(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !selectedBudget) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      await apiPost(
        `/workspaces/${workspace.id}/budgets/${selectedBudget.id}/lines`,
        {
          name: lineName.trim(),
          planned_amount: Number(plannedAmount),
          notes: lineNotes.trim() || undefined,
        },
      );
      setLineName("");
      setPlannedAmount("");
      setLineNotes("");
      await selectBudget(selectedBudget.id);
      setBudgets((current) => current.map((budget) => (budget.id === selectedBudget.id ? { ...budget, planned_total: selectedBudget.planned_total + Number(plannedAmount) } : budget)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add budget line.");
    } finally {
      setWorking(false);
    }
  }

  async function logExpense(lineId: number) {
    if (!workspace || !selectedBudget) {
      return;
    }
    const amount = Number(expenseAmounts[lineId] || 0);
    if (!amount) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      await apiPost(`/workspaces/${workspace.id}/budgets/${selectedBudget.id}/lines/${lineId}/expenditures`, {
        amount,
      });
      setExpenseAmounts((current) => ({ ...current, [lineId]: "" }));
      await selectBudget(selectedBudget.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to log expenditure.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="page-stack">
      <header className="page-head">
        <p className="eyebrow">Budgets</p>
        <h1>Budget planner</h1>
        <p>{workspace?.name || params.workspaceSlug}</p>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      <section className="content-grid">
        <article className="panel-card">
          <div className="card-head compact">
            <h2>New budget</h2>
          </div>
          <form className="form-stack" onSubmit={createBudget}>
            <label>
              Budget name
              <input value={budgetName} onChange={(event) => setBudgetName(event.target.value)} required />
            </label>
            <label>
              Period label
              <input value={periodLabel} onChange={(event) => setPeriodLabel(event.target.value)} placeholder="2026 Session / Q2" />
            </label>
            <button type="submit" className="btn-primary" disabled={working || !workspace}>
              {working ? "Saving..." : "Create budget"}
            </button>
          </form>
        </article>

        <article className="panel-card">
          <div className="card-head compact">
            <h2>Budgets</h2>
          </div>
          {budgets.length === 0 ? (
            <div className="empty-state">
              <span className="material-symbols-outlined" aria-hidden="true">
                account_balance
              </span>
              <h2>No budgets yet</h2>
              <p>Create your first budget to start tracking planned and actual spend.</p>
            </div>
          ) : (
            <div className="activity-list">
              {budgets.map((budget) => (
                <button key={budget.id} type="button" className={`activity-item selectable ${selectedBudget?.id === budget.id ? "active" : ""}`} onClick={() => selectBudget(budget.id)}>
                  <div>
                    <h3>{budget.name}</h3>
                    <p>{budget.period_label || budget.status}</p>
                  </div>
                  <div className="activity-meta">
                    <span>NGN {budget.actual_total.toLocaleString()}</span>
                    <strong>NGN {budget.planned_total.toLocaleString()}</strong>
                  </div>
                </button>
              ))}
            </div>
          )}
        </article>
      </section>

      {selectedBudget ? (
        <section className="content-grid">
          <article className="panel-card">
            <div className="card-head row">
              <div>
                <p className="eyebrow">Selected budget</p>
                <h2>{selectedBudget.name}</h2>
                <p>{selectedBudget.description || selectedBudget.period_label || "Budget detail"}</p>
              </div>
              <a
                href={`${API_BASE_URL}/workspaces/${workspace?.id}/budgets/${selectedBudget.id}/export`}
                className="btn-secondary"
                target="_blank"
                rel="noreferrer"
              >
                Export CSV
              </a>
            </div>
            <div className="mini-list">
              <div>
                <span>Planned</span>
                <strong>NGN {selectedBudget.planned_total.toLocaleString()}</strong>
              </div>
              <div>
                <span>Actual</span>
                <strong>NGN {selectedBudget.actual_total.toLocaleString()}</strong>
              </div>
              <div>
                <span>Status</span>
                <strong>{selectedBudget.status}</strong>
              </div>
            </div>
          </article>

          <article className="panel-card">
            <div className="card-head compact">
              <h2>Add budget line</h2>
            </div>
            <form className="form-stack" onSubmit={addLine}>
              <label>
                Line item
                <input value={lineName} onChange={(event) => setLineName(event.target.value)} required />
              </label>
              <label>
                Planned amount
                <input value={plannedAmount} onChange={(event) => setPlannedAmount(event.target.value)} inputMode="decimal" required />
              </label>
              <label>
                Notes
                <textarea rows={3} value={lineNotes} onChange={(event) => setLineNotes(event.target.value)} />
              </label>
              <button type="submit" className="btn-primary" disabled={working}>
                {working ? "Saving..." : "Add line"}
              </button>
            </form>
          </article>
        </section>
      ) : null}

      {selectedBudget ? (
        <article className="panel-card">
          <h2>Budget lines</h2>
          {selectedBudget.lines.length === 0 ? (
            <div className="empty-block">
              <span className="material-symbols-outlined" aria-hidden="true">
                receipt_long
              </span>
              <h3>No lines yet</h3>
              <p>Add income or expense lines to make this budget useful.</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Planned</th>
                    <th>Actual</th>
                    <th>Log spend</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedBudget.lines.map((line) => (
                    <tr key={line.id}>
                      <td>
                        <strong>{line.name}</strong>
                        {line.notes ? <div className="muted-copy">{line.notes}</div> : null}
                      </td>
                      <td>NGN {line.planned_amount.toLocaleString()}</td>
                      <td>NGN {line.actual_amount.toLocaleString()}</td>
                      <td>
                        <div className="inline-input-row">
                          <input
                            value={expenseAmounts[line.id] || ""}
                            onChange={(event) => setExpenseAmounts((current) => ({ ...current, [line.id]: event.target.value }))}
                            inputMode="decimal"
                            placeholder="Amount"
                          />
                          <button type="button" className="btn-secondary" onClick={() => logExpense(line.id)} disabled={working}>
                            Add
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      ) : null}
    </section>
  );
}
