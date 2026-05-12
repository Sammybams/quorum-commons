"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { apiPost } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await apiPost<{ message: string }, { email: string }>("/auth/forgot-password", {
        email: email.trim().toLowerCase(),
      });
      setMessage(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to send reset email.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-screen">
      <section className="auth-form-area auth-form-area-centered">
        <div className="auth-card">
          <div className="auth-card-head">
            <p className="eyebrow">Account recovery</p>
            <h2>Forgot password</h2>
            <p>Enter the email attached to your Quorum account and we’ll send a reset link.</p>
          </div>
          <form className="form-stack" onSubmit={submit}>
            <label>
              Email
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            {message ? <p className="form-success">{message}</p> : null}
            {error ? <p className="form-error">{error}</p> : null}
            <button className="btn-primary wide" disabled={loading} type="submit">
              {loading ? "Sending..." : "Send reset link"}
            </button>
          </form>
          <p className="auth-footnote">
            Remembered it? <Link href="/login">Back to login</Link>
          </p>
        </div>
      </section>
    </main>
  );
}
