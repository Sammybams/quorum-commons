export default function WorkspaceRouteLoading() {
  return (
    <section className="page-stack">
      <header className="page-head">
        <p className="eyebrow">Loading</p>
        <h1>Opening workspace</h1>
        <p>Fetching the latest workspace data.</p>
      </header>
      <section className="metrics-grid">
        <article className="metric-card">
          <small>Loading</small>
          <strong>...</strong>
          <p>Please wait</p>
        </article>
        <article className="metric-card">
          <small>Loading</small>
          <strong>...</strong>
          <p>Please wait</p>
        </article>
        <article className="metric-card">
          <small>Loading</small>
          <strong>...</strong>
          <p>Please wait</p>
        </article>
      </section>
      <article className="panel-card">
        <p className="empty-block">Loading workspace section...</p>
      </article>
    </section>
  );
}
