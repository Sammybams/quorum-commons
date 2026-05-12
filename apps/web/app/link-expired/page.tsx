import Link from "next/link";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

export default function LinkExpiredPage({ searchParams }: { searchParams: { slug?: string } }) {
  const slug = searchParams.slug;

  return (
    <main className="public-page expired-page">
      <div className="expired-card">
        <span className="material-symbols-outlined expired-icon" aria-hidden="true">
          link_off
        </span>
        <h1>This link has expired</h1>
        {slug ? (
          <p className="muted">
            <strong>quorum.ng/{slug}</strong> is no longer active.
          </p>
        ) : null}
        <p>The organisation that shared this link may have updated or removed it.</p>
        <Link href={APP_URL} className="btn-primary">
          Go to Quorum
        </Link>
      </div>
    </main>
  );
}
