import { apiGet } from "@/lib/api";
import { getWorkspaceBySlug } from "@/lib/workspace-server";
import DuesClient from "./dues-client";
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

export default async function DuesPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await getWorkspaceBySlug(params.workspaceSlug);
  const [cycles, payments, members] = await Promise.all([
    apiGet<DuesCycle[]>(`/workspaces/${workspace.id}/dues-cycles`),
    apiGet<DuesPayment[]>(`/workspaces/${workspace.id}/dues-payments`),
    apiGet<Member[]>(`/workspaces/${workspace.id}/members`),
  ]);

  return <DuesClient workspace={workspace} initialCycles={cycles} initialPayments={payments} members={members} />;
}
