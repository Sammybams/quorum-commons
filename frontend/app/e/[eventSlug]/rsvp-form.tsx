"use client";

import { FormEvent, useState } from "react";

import { apiPost } from "@/lib/api";

export default function PublicEventRsvpForm({ eventSlug }: { eventSlug: string }) {
  const [fullName, setFullName] = useState("");
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
      await apiPost(`/public/e/${eventSlug}/rsvp`, {
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
      });
      setMessage("RSVP confirmed.");
      setFullName("");
      setEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to RSVP.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="form-stack" onSubmit={submit}>
      <label>
        Full name
        <input value={fullName} onChange={(event) => setFullName(event.target.value)} required />
      </label>
      <label>
        Email
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
      </label>
      {message ? <p className="form-success">{message}</p> : null}
      {error ? <p className="form-error">{error}</p> : null}
      <button className="btn-primary" disabled={loading} type="submit">
        {loading ? "Submitting..." : "RSVP"}
      </button>
    </form>
  );
}
