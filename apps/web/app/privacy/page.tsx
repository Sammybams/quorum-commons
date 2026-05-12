import Link from "next/link";

import BrandWordmark from "@/components/brand-wordmark";
import ThemeToggle from "@/components/theme-toggle";

export const metadata = {
  title: "Privacy Policy | Quorum",
  description: "Privacy policy for Quorum, the student body operating system.",
};

const policySections = [
  {
    title: "Information we collect",
    body: [
      "Quorum collects the account, workspace, and operational information needed to run student-body administration. This can include names, email addresses, phone numbers, workspace slugs, member records, meeting notes, event RSVPs, financial records, and invitation activity.",
      "We also collect technical information needed to secure and operate the service, such as authentication tokens, audit timestamps, browser metadata, and usage logs.",
    ],
  },
  {
    title: "How we use your information",
    body: [
      "We use your information to provide Quorum features, including account access, workspace administration, member invitations, event operations, fundraising workflows, dues tracking, budgeting, and announcements.",
      "When enabled by a workspace administrator, Quorum can use connected integrations such as Google Workspace and Fireflies to create meeting links, retrieve transcripts, and send invitations from the connected account.",
    ],
  },
  {
    title: "Google user data",
    body: [
      "If a workspace administrator connects Google Workspace, Quorum only uses the granted Google data and scopes to support the features the administrator has chosen to enable. These features may include sending invitations through Gmail, creating Google Meet links, and reading transcript documents required for meeting minutes workflows.",
      "Quorum does not sell Google user data, does not use it for advertising, and does not transfer it to third parties except as necessary to provide the requested product functionality or to comply with the law.",
      "Google user data is used only for the active workspace connection and can be disconnected by an authorized workspace administrator from the Integrations settings page.",
    ],
  },
  {
    title: "AI-assisted features",
    body: [
      "Quorum may process meeting transcripts, notes, receipts, and other workspace content through configured AI services to generate summaries, minutes, action items, verification decisions, and analytics. These features are used only to provide workspace functionality requested by the user.",
      "Workspace administrators are responsible for deciding what content is uploaded into Quorum and what integrations are enabled for their workspace.",
    ],
  },
  {
    title: "Data sharing and retention",
    body: [
      "We do not sell personal information. We may share data with subprocessors and infrastructure providers that help us operate Quorum, such as cloud hosting, authentication, payment, email, and AI service providers, strictly for service delivery purposes.",
      "We retain information for as long as needed to provide the service, meet legal obligations, resolve disputes, and enforce agreements. Workspace administrators may request deletion or disconnection of integrations where supported.",
    ],
  },
  {
    title: "Security and contact",
    body: [
      "We use reasonable administrative, technical, and organizational measures to protect data processed through Quorum. No method of transmission or storage is perfectly secure, so we cannot guarantee absolute security.",
      "For privacy questions, support requests, or data-related concerns, contact support@quorum.ng.",
    ],
  },
];

export default function PrivacyPage() {
  return (
    <main className="legal-shell">
      <nav className="stitch-nav">
        <div className="stitch-nav-inner">
          <Link href="/" className="stitch-logo" aria-label="Quorum home">
            <BrandWordmark />
          </Link>
          <div className="stitch-actions">
            <ThemeToggle />
            <Link href="/login" className="stitch-login">
              Login
            </Link>
            <Link href="/register" className="stitch-join">
              Join Quorum
            </Link>
          </div>
        </div>
      </nav>

      <section className="legal-page">
        <div className="legal-page-head">
          <p className="stitch-badge">Privacy policy</p>
          <h1>Privacy Policy</h1>
          <p>
            This page explains how Quorum collects, uses, and protects information across workspace administration,
            member operations, integrations, and AI-assisted workflows.
          </p>
          <p className="legal-meta">Last updated: April 24, 2026</p>
        </div>

        <div className="legal-section-list">
          {policySections.map((section) => (
            <section key={section.title} className="legal-section">
              <h2>{section.title}</h2>
              {section.body.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </section>
          ))}
        </div>

        <div className="legal-actions">
          <Link href="/" className="stitch-hero-secondary">
            Back to home
          </Link>
          <a href="mailto:support@quorum.ng" className="stitch-hero-primary">
            Contact support
          </a>
        </div>
      </section>
    </main>
  );
}
