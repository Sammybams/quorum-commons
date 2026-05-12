import { apiGet } from "@/lib/api";

import MembersClient from "./members-client";

type Workspace = { id: number; slug: string; name: string };
type Member = {
  id: number;
  full_name: string;
  level?: string;
  email?: string;
  role: string;
  dues_status?: string;
};

export default async function MembersPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
  const members = await apiGet<Member[]>(`/workspaces/${workspace.id}/members`);

  return <MembersClient workspace={workspace} initialMembers={members} />;
}
