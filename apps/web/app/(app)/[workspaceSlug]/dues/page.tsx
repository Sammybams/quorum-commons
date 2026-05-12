import { apiGet } from "@/lib/api";
import DuesClient from "./dues-client";

type Workspace = { id: number; slug: string; name: string };
type DuesCycle = { id: number; workspace_id: number; name: string; amount: number; deadline?: string | null };
type DuesPayment = {
  id: number;
  member_id?: number | null;
  member_name?: string | null;
  amount: number;
  method: string;
  gateway_ref?: string | null;
  status: string;
  created_at: string;
};
type Member = { id: number; full_name: string; email?: string | null };

export default async function DuesPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
  const [cycles, payments, members] = await Promise.all([
    apiGet<DuesCycle[]>(`/workspaces/${workspace.id}/dues-cycles`),
    apiGet<DuesPayment[]>(`/workspaces/${workspace.id}/dues-payments`),
    apiGet<Member[]>(`/workspaces/${workspace.id}/members`),
  ]);

  return <DuesClient workspace={workspace} initialCycles={cycles} initialPayments={payments} members={members} />;
}
