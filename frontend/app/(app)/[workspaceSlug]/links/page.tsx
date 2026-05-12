import { apiGet } from "@/lib/api";
import type { ShortLink } from "@/lib/api/links";
import LinksClient from "./LinksClient";

type Workspace = { id: number; slug: string; name: string };

export default async function LinksPage({ params }: { params: { workspaceSlug: string } }) {
  const workspace = await apiGet<Workspace>(`/workspaces/slug/${params.workspaceSlug}`);
  const links = await apiGet<ShortLink[]>(`/workspaces/${workspace.id}/links`);
  const activeCount = links.filter((link) => link.is_active).length;
  const totalClicks = links.reduce((sum, link) => sum + link.click_count, 0);

  return (
    <section className="page-stack">
      <header className="page-head row">
        <div>
          <p className="eyebrow">Smart links</p>
          <h1>Trackable redirects</h1>
          <p>{workspace.name}</p>
        </div>
      </header>

      <div className="metric-row">
        <div className="metric-card">
          <span className="metric-label">Total links</span>
          <span className="metric-value">{links.length}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Active</span>
          <span className="metric-value">{activeCount}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Total clicks</span>
          <span className="metric-value">{totalClicks.toLocaleString()}</span>
        </div>
      </div>

      <LinksClient links={links} workspaceId={workspace.id} />
    </section>
  );
}
