"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { apiPost } from "@/lib/api";

export default function ResetPasswordPage({ params }: { params: { token: string } }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await apiPost("/auth/reset-password", { token: params.token, password });
      router.push("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reset password.");
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
            <h2>Set a new password</h2>
          </div>
          <form className="form-stack" onSubmit={submit}>
            <label>
              New password
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
            {error ? <p className="form-error">{error}</p> : null}
            <button className="btn-primary wide" disabled={loading} type="submit">
              {loading ? "Updating..." : "Update password"}
            </button>
          </form>
          <p className="auth-footnote">
            <Link href="/login">Back to login</Link>
          </p>
        </div>
      </section>
    </main>
  );
}
