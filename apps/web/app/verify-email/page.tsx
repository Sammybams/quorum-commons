"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { apiPost } from "@/lib/api";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [state, setState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("Checking your verification link...");

  useEffect(() => {
    async function run() {
      if (!token) {
        setState("error");
        setMessage("Verification token is missing.");
        return;
      }
      setState("loading");
      try {
        const result = await apiPost<{ message: string }, { token: string }>("/auth/verify-email", { token });
        setState("success");
        setMessage(result.message);
      } catch (err) {
        setState("error");
        setMessage(err instanceof Error ? err.message : "Unable to verify email.");
      }
    }
    run();
  }, [token]);

  return (
    <div className="auth-card">
      <div className="auth-card-head">
        <p className="eyebrow">Email verification</p>
        <h2>{state === "success" ? "Email verified" : "Verify email"}</h2>
        <p>{message}</p>
      </div>
      <div className="form-actions">
        <Link href="/login" className="btn-primary">
          Go to login
        </Link>
      </div>
    </div>
  );
}

function VerifyEmailFallback() {
  return (
    <div className="auth-card">
      <div className="auth-card-head">
        <p className="eyebrow">Email verification</p>
        <h2>Verify email</h2>
        <p>Checking your verification link...</p>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <main className="auth-screen">
      <section className="auth-form-area auth-form-area-centered">
        <Suspense fallback={<VerifyEmailFallback />}>
          <VerifyEmailContent />
        </Suspense>
      </section>
    </main>
  );
}
