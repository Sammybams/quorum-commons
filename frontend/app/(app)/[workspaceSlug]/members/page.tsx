import { apiGet } from "@/lib/api";
import { getWorkspaceBySlug } from "@/lib/workspace-server";

import MembersClient from "./members-client";
type Member = {
  id: number;
  full_name: string;
  level?: string;
  email?: string;
  role: string;
  trade_category?: string | null;
  location?: string | null;
  languages?: string[];
  availability?: string | null;
  contribution_capacity?: string | null;
  dues_status?: string;
};

export default async function MembersPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await getWorkspaceBySlug(params.workspaceSlug);
  const members = await apiGet<Member[]>(`/workspaces/${workspace.id}/members`);

  return <MembersClient workspace={workspace} initialMembers={members} />;
}
