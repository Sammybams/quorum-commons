export default function WorkspaceLoading() {
  return (
    <section className="page-stack">
      <header className="page-head">
        <p className="eyebrow">Loading</p>
        <h1>Opening workspace section...</h1>
        <p>Your next view is being prepared.</p>
      </header>

      <section className="metrics-grid">
        {Array.from({ length: 4 }).map((_, index) => (
          <article key={index} className="metric-card skeleton-card">
            <div className="skeleton-line short" />
            <div className="skeleton-line medium" />
            <div className="skeleton-line long" />
          </article>
        ))}
      </section>

      <section className="content-grid">
        <article className="panel-card skeleton-panel">
          <div className="skeleton-line short" />
          <div className="skeleton-line medium" />
          <div className="skeleton-line long" />
          <div className="skeleton-line long" />
        </article>
        <article className="panel-card skeleton-panel">
          <div className="skeleton-line short" />
          <div className="skeleton-line medium" />
          <div className="skeleton-line long" />
        </article>
      </section>
    </section>
  );
}
