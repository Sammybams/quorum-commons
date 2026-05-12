import { apiGet } from "@/lib/api";
import CampaignsClient from "./campaigns-client";

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
type CampaignDetail = Campaign & {
  funding_streams: Array<{
    id: number;
    workspace_id: number;
    campaign_id: number;
    name: string;
    stream_type: string;
    target_amount: number | null;
    raised_amount: number;
  }>;
  contributions: Array<{
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
  }>;
  contributor_count: number;
};

export default async function CampaignsPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
  const campaigns = await apiGet<Campaign[]>(`/workspaces/${workspace.id}/campaigns`);
  const selected = campaigns.find((item) => item.status === "active") || campaigns[0] || null;
  const detail = selected
    ? await apiGet<CampaignDetail>(`/workspaces/${workspace.id}/campaigns/${selected.id}`)
    : null;

  return <CampaignsClient workspace={workspace} initialCampaigns={campaigns} initialDetail={detail} />;
}
