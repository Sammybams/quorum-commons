"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import BrandWordmark from "@/components/brand-wordmark";
import { apiPost } from "@/lib/api";
import { saveSession, type QuorumSession } from "@/lib/session";

function slugify(input: string) {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}

export default function RegisterPage() {
  const [step, setStep] = useState(1);
  const [organizationName, setOrganizationName] = useState("");
  const [university, setUniversity] = useState("");
  const [bodyType, setBodyType] = useState("department_body");
  const [faculty, setFaculty] = useState("");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [officeTitle, setOfficeTitle] = useState("president_lead");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [workspaceSlug, setWorkspaceSlug] = useState("workspace");
  const [slugEdited, setSlugEdited] = useState(false);
  const [createdSession, setCreatedSession] = useState<QuorumSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const suggestedSlug = useMemo(
    () => slugify(organizationName || university || "workspace") || "workspace",
    [organizationName, university],
  );

  useEffect(() => {
    if (!slugEdited) {
      setWorkspaceSlug(suggestedSlug);
    }
  }, [slugEdited, suggestedSlug]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (step === 1) {
      setStep(2);
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    const normalizedWorkspaceSlug = slugify(workspaceSlug);

    if (!normalizedWorkspaceSlug) {
      setError("Choose a workspace slug with at least one letter or number.");
      return;
    }

    setLoading(true);

    try {
      const result = await apiPost<
        QuorumSession,
        {
          organization_name: string;
          workspace_slug: string;
          university?: string;
          body_type?: string;
          faculty?: string;
          admin_name: string;
          admin_email: string;
          phone_number?: string;
          admin_role?: string;
          password: string;
        }
      >("/auth/register", {
        organization_name: organizationName.trim(),
        workspace_slug: normalizedWorkspaceSlug,
        university: university.trim() || undefined,
        body_type: bodyType,
        faculty: faculty.trim() || undefined,
        admin_name: adminName.trim(),
        admin_email: adminEmail.trim().toLowerCase(),
        phone_number: phoneNumber.trim() || undefined,
        admin_role: officeTitle,
        password,
      });

      saveSession(result);
      setCreatedSession(result);
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create workspace.");
    } finally {
      setLoading(false);
    }
  }

  if (createdSession) {
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
            <div className="stepper" aria-label="Signup progress">
              {["Organization", "Admin", "Ready"].map((label) => (
                <span key={label} className="active">
                  <b>{label === "Organization" ? 1 : label === "Admin" ? 2 : 3}</b>
                  {label}
                </span>
              ))}
            </div>
            <p className="eyebrow">Workspace ready</p>
            <h1>Your workspace is ready.</h1>
            <p>Verify your email when verification is enabled, then start inviting real members.</p>
          </aside>

          <section className="signup-card success-card">
            <span className="material-symbols-outlined success-icon" aria-hidden="true">
              check_circle
            </span>
            <h2>{createdSession.workspace_name}</h2>
            <p>Your workspace lives at:</p>
            <div className="portal-preview">quorum.ng/{createdSession.workspace_slug}</div>
            <div className="form-actions">
              <Link href="/login" className="btn-ghost">
                Back to login
              </Link>
              <Link href={`/${createdSession.workspace_slug}/dashboard`} className="btn-primary">
                Open workspace
              </Link>
            </div>
          </section>
        </section>
      </main>
    );
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
          <div className="stepper" aria-label="Signup progress">
            {["Organization", "Admin", "Ready"].map((label, index) => (
              <span key={label} className={step >= index + 1 ? "active" : ""}>
                <b>{index + 1}</b>
                {label}
              </span>
            ))}
          </div>
          <p className="eyebrow">Workspace setup</p>
          <h1>Set the stage for your student body.</h1>
          <p>Start with the organization, then create the full-access admin account for the workspace.</p>
        </aside>

        <section className="signup-card">
          <h2>{step === 1 ? "Organization details" : "Admin details"}</h2>

          <form onSubmit={onSubmit} className="form-stack">
            {step === 1 ? (
              <>
                <label>
                  Organization name
                  <span className="input-shell">
                    <span className="material-symbols-outlined" aria-hidden="true">
                      groups
                    </span>
                    <input
                      type="text"
                      placeholder="Undergraduate Student Union"
                      value={organizationName}
                      onChange={(event) => setOrganizationName(event.target.value)}
                      required
                    />
                  </span>
                </label>

                <label>
                  University / Institution
                  <span className="input-shell">
                    <span className="material-symbols-outlined" aria-hidden="true">
                      school
                    </span>
                    <input
                      type="text"
                      placeholder="Search for your institution"
                      value={university}
                      onChange={(event) => setUniversity(event.target.value)}
                      required
                    />
                  </span>
                </label>

                <div className="form-two">
                  <label>
                    Body type
                    <select value={bodyType} onChange={(event) => setBodyType(event.target.value)}>
                      <option value="department_body">Department body</option>
                      <option value="faculty_body">Faculty body</option>
                      <option value="student_union">Student Union</option>
                      <option value="club_association">Club or Association</option>
                    </select>
                  </label>

                  <label>
                    Faculty / Department
                    <input
                      type="text"
                      placeholder="Faculty of Arts"
                      value={faculty}
                      onChange={(event) => setFaculty(event.target.value)}
                    />
                  </label>
                </div>
              </>
            ) : null}

            {step === 2 ? (
              <>
                <label>
                  Your name
                  <span className="input-shell">
                    <span className="material-symbols-outlined" aria-hidden="true">
                      badge
                    </span>
                    <input
                      type="text"
                      placeholder="Oluwaseun Adeyemi"
                      value={adminName}
                      onChange={(event) => setAdminName(event.target.value)}
                      required
                    />
                  </span>
                </label>

                <label>
                  Email
                  <span className="input-shell">
                    <span className="material-symbols-outlined" aria-hidden="true">
                      alternate_email
                    </span>
                    <input
                      type="email"
                      placeholder="you@example.com"
                      value={adminEmail}
                      onChange={(event) => setAdminEmail(event.target.value)}
                      required
                    />
                  </span>
                </label>

                <div className="form-two">
                  <label>
                    Phone number
                    <input
                      type="tel"
                      placeholder="+234 801 234 5678"
                      value={phoneNumber}
                      onChange={(event) => setPhoneNumber(event.target.value)}
                      required
                    />
                  </label>
                  <label>
                    Office title
                    <span className="select-shell">
                      <select value={officeTitle} onChange={(event) => setOfficeTitle(event.target.value)}>
                        <option value="president_lead">President / Lead</option>
                        <option value="secretary">Secretary</option>
                      </select>
                      <span className="material-symbols-outlined" aria-hidden="true">
                        expand_more
                      </span>
                    </span>
                  </label>
                </div>

                <p className="muted-copy">This title is for documentation. The creator still gets full workspace access and can adjust roles later.</p>

                <div className="form-two">
                  <label>
                    Password
                    <input
                      type="password"
                      placeholder="Create password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      required
                    />
                  </label>
                  <label>
                    Confirm password
                    <input
                      type="password"
                      placeholder="Repeat password"
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      required
                    />
                  </label>
                </div>

                <label>
                  Workspace slug
                  <span className="slug-field">
                    <span>quorum.ng/</span>
                    <input
                      type="text"
                      value={workspaceSlug}
                      onChange={(event) => {
                        setSlugEdited(true);
                        setWorkspaceSlug(event.target.value);
                      }}
                      required
                    />
                  </span>
                </label>
              </>
            ) : null}

            {error ? <p className="form-error">{error}</p> : null}

            <div className="form-actions">
              {step === 1 ? (
                <Link href="/" className="btn-ghost">
                  Cancel setup
                </Link>
              ) : (
                <button type="button" className="btn-ghost" onClick={() => setStep(1)}>
                  Back
                </button>
              )}
              <button type="submit" className="btn-primary" disabled={loading}>
                {loading ? "Creating..." : step === 1 ? "Continue" : "Create workspace"}
              </button>
            </div>
          </form>
        </section>
      </section>
    </main>
  );
}
