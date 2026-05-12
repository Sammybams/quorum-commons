"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import BrandWordmark from "@/components/brand-wordmark";
import { apiGet, apiPost } from "@/lib/api";
import { saveSession, type QuorumSession } from "@/lib/session";

type InvitePreview = {
  workspace_name: string;
  workspace_slug: string;
  role_name: string;
  expires_at?: string;
};

export default function JoinLinkPage({ params }: { params: { token: string } }) {
  const router = useRouter();
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        setPreview(await apiGet<InvitePreview>(`/join/${params.token}`));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Invite link not found.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [params.token]);

  async function joinWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const session = await apiPost<
        QuorumSession,
        { full_name: string; email: string; phone_number?: string; password: string }
      >(`/join/${params.token}/accept`, {
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        phone_number: phoneNumber.trim() || undefined,
        password,
      });
      saveSession(session);
      router.push(`/${session.workspace_slug}/dashboard`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to join workspace.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="signup-screen">
      <header className="signup-top">
        <Link className="wordmark" href="/">
          <BrandWordmark />
        </Link>
        <Link href="/login" className="subtle-link">
          Sign in
        </Link>
      </header>

      <section className="signup-grid">
        <aside className="signup-copy">
          <p className="eyebrow">Invite link</p>
          <h1>{loading ? "Checking invite..." : "Join the workspace."}</h1>
          <p>
            {preview
              ? `This link adds you to ${preview.workspace_name} as ${preview.role_name}.`
              : "Use your invite link to create your Quorum account."}
          </p>
        </aside>

        <section className="signup-card">
          <h2>Create your member account</h2>
          <form className="form-stack" onSubmit={joinWorkspace}>
            <label>
              Full name
              <input value={fullName} onChange={(event) => setFullName(event.target.value)} required />
            </label>
            <label>
              Email
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            <label>
              Phone number
              <input value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} />
            </label>
            <div className="form-two">
              <label>
                Password
                <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
              </label>
              <label>
                Confirm password
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  required
                />
              </label>
            </div>
            {error ? <p className="form-error">{error}</p> : null}
            <button className="btn-primary" type="submit" disabled={submitting || loading || !preview}>
              {submitting ? "Joining..." : "Join workspace"}
            </button>
          </form>
        </section>
      </section>
    </main>
  );
}
