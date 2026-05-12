"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import QRCodeDownload from "@/components/QRCodeDownload";
import { apiDelete, apiPost } from "@/lib/api";
import type { ShortLink } from "@/lib/api/links";

type Props = {
  links: ShortLink[];
  workspaceId: number;
};

export default function LinksClient({ links, workspaceId }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [showModal, setShowModal] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [copiedSlug, setCopiedSlug] = useState<string | null>(null);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setCreating(true);

    const form = new FormData(event.currentTarget);
    const payload = {
      slug: String(form.get("slug") || "").trim(),
      destination_url: String(form.get("destination_url") || "").trim(),
      title: String(form.get("title") || "").trim() || null,
      expires_at: String(form.get("expires_at") || "") || null,
    };

    try {
      await apiPost<ShortLink, typeof payload>(`/workspaces/${workspaceId}/links`, payload);
      setShowModal(false);
      startTransition(() => router.refresh());
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Unable to create link");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(linkId: number) {
    try {
      await apiDelete(`/workspaces/${workspaceId}/links/${linkId}`);
      setDeletingId(null);
      startTransition(() => router.refresh());
    } catch {
      setDeletingId(null);
    }
  }

  function handleCopy(shortUrl: string, slug: string) {
    navigator.clipboard.writeText(shortUrl).then(() => {
      setCopiedSlug(slug);
      window.setTimeout(() => setCopiedSlug(null), 1800);
    });
  }

  return (
    <>
      <div className="links-actions">
        <button type="button" className="btn-primary" onClick={() => setShowModal(true)}>
          <span className="material-symbols-outlined" aria-hidden="true">
            add_link
          </span>
          New Link
        </button>
      </div>

      <section className="panel-card links-panel">
        {links.length === 0 ? (
          <div className="empty-state compact">
            <span className="material-symbols-outlined" aria-hidden="true">
              link_off
            </span>
            <h2>No links yet</h2>
            <p>Create public short links for events, campaigns, forms, and announcements.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table links-table">
              <thead>
                <tr>
                  <th>Short URL</th>
                  <th>Label</th>
                  <th>Destination</th>
                  <th>Clicks</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {links.map((link) => (
                  <tr key={link.id}>
                    <td>
                      <span className="link-slug-cell">
                        <code>{link.short_url}</code>
                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => handleCopy(link.short_url, link.slug)}
                          title="Copy short URL"
                        >
                          <span className="material-symbols-outlined" aria-hidden="true">
                            {copiedSlug === link.slug ? "check" : "content_copy"}
                          </span>
                        </button>
                      </span>
                    </td>
                    <td>{link.title || <span className="muted">Untitled</span>}</td>
                    <td>
                      <a href={link.destination_url} className="link-dest" target="_blank" rel="noopener noreferrer" title={link.destination_url}>
                        {link.destination_url}
                      </a>
                    </td>
                    <td>
                      <strong>{link.click_count.toLocaleString()}</strong>
                    </td>
                    <td>
                      <span className={`status-pill ${link.is_active ? "ok" : "pending"}`}>{link.is_active ? "Active" : "Disabled"}</span>
                      {link.expires_at ? <span className="muted expires-label"> expires {new Date(link.expires_at).toLocaleDateString()}</span> : null}
                    </td>
                    <td>
                      <div className="action-row">
                        <QRCodeDownload url={link.short_url} filename={link.slug} label="" className="icon-btn" />
                        {deletingId === link.id ? (
                          <span className="confirm-row">
                            <button type="button" className="btn-danger-sm" onClick={() => handleDelete(link.id)}>
                              Confirm
                            </button>
                            <button type="button" className="btn-ghost-sm" onClick={() => setDeletingId(null)}>
                              Cancel
                            </button>
                          </span>
                        ) : (
                          <button type="button" className="icon-btn danger" onClick={() => setDeletingId(link.id)} title="Delete link">
                            <span className="material-symbols-outlined" aria-hidden="true">
                              delete
                            </span>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showModal ? (
        <div className="modal-backdrop" onClick={() => setShowModal(false)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="link-modal-title">
            <div className="modal-head">
              <h2 id="link-modal-title">New short link</h2>
              <button type="button" className="icon-btn" onClick={() => setShowModal(false)} aria-label="Close">
                <span className="material-symbols-outlined" aria-hidden="true">
                  close
                </span>
              </button>
            </div>
            <form onSubmit={handleCreate} className="form-stack">
              <div className="field">
                <label htmlFor="slug">Slug</label>
                <div className="input-prefix-wrap">
                  <span className="input-prefix">quorum.ng/</span>
                  <input id="slug" name="slug" type="text" required pattern="[a-zA-Z0-9- ]+" placeholder="annual-dinner" className="input-with-prefix" autoComplete="off" />
                </div>
                <p className="field-hint">Letters, numbers, spaces, and hyphens are accepted.</p>
              </div>
              <div className="field">
                <label htmlFor="destination_url">Destination URL</label>
                <input id="destination_url" name="destination_url" type="url" required placeholder="https://forms.example.com/rsvp" className="input" />
              </div>
              <div className="field">
                <label htmlFor="title">Label</label>
                <input id="title" name="title" type="text" placeholder="Annual dinner RSVP" className="input" maxLength={200} />
              </div>
              <div className="field">
                <label htmlFor="expires_at">Expiry date</label>
                <input id="expires_at" name="expires_at" type="datetime-local" className="input" />
              </div>
              {formError ? <p className="form-error">{formError}</p> : null}
              <div className="modal-actions">
                <button type="button" className="btn-ghost" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={creating || isPending}>
                  {creating ? "Creating..." : "Create link"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
