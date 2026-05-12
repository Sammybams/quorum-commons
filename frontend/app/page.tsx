import Link from "next/link";

import BrandWordmark from "@/components/brand-wordmark";
import ThemeToggle from "@/components/theme-toggle";

const valueCards = [
  {
    title: "Leadership ops",
    text: "One workspace for member records, meetings, events, finances, and announcements.",
  },
  {
    title: "Member clarity",
    text: "Give members a clean view of dues, notices, RSVP links, and fundraising progress.",
  },
  {
    title: "Finance control",
    text: "Track dues, campaign inflows, budgets, receipts, and reporting without spreadsheet drift.",
  },
  {
    title: "AI assistance",
    text: "Use Claude to turn transcripts into minutes and action items that leaders can actually work from.",
  },
];

const pricingPlans = [
  {
    name: "Starter",
    accent: "neutral",
    price: "Free",
    cadence: "forever",
    seats: "Up to 3 admin seats",
    ai: "20 AI receipt verifications/month",
    features: [
      "Member registry",
      "Dues tracker with receipt upload",
      "Event creator with shareable links",
      "Announcements board",
      "1 active fundraising campaign",
    ],
  },
  {
    name: "Growth",
    accent: "blue",
    price: "₦8,000",
    cadence: "/month · ₦86,400/year",
    seats: "Up to 10 admin seats",
    ai: "100 AI verifications/month + minutes assistant",
    features: [
      "Everything in Starter",
      "Meetings module (agenda, quorum, minutes)",
      "Budget planner",
      "Events analytics dashboard",
      "Short link click analytics",
    ],
  },
  {
    name: "Pro",
    accent: "violet",
    price: "₦20,000",
    cadence: "/month · ₦216,000/year",
    seats: "Up to 25 admin seats",
    ai: "500 AI verifications/month + analytics reports",
    features: [
      "Everything in Growth",
      "Custom domain for portal page",
      "White-label branding",
      "AI-generated analytics reports",
      "Custom role builder",
    ],
  },
];

const workflowCards = [
  {
    title: "Fundraising cockpit",
    eyebrow: "Campaigns",
    stats: [
      { label: "Raised", value: "₦742k" },
      { label: "Goal", value: "₦1.2m" },
      { label: "Sponsors", value: "48" },
    ],
    items: ["Track streams and donation links", "Review contribution ledger", "Monitor campaign pace in real time"],
  },
  {
    title: "Meetings to minutes",
    eyebrow: "Meetings",
    stats: [
      { label: "Agenda items", value: "8" },
      { label: "Attendees", value: "14" },
      { label: "Actions", value: "6" },
    ],
    items: ["Create agenda and quorum flow", "Sync transcript from integrations", "Publish Claude-generated minutes"],
  },
  {
    title: "Member operations",
    eyebrow: "Members",
    stats: [
      { label: "Active", value: "326" },
      { label: "Pending", value: "24" },
      { label: "Paid dues", value: "71%" },
    ],
    items: ["Invite officers from Gmail", "Track status and role ownership", "See dues and attendance health"],
  },
];

const resourceCards = [
  {
    title: "Demo workspace setup",
    text: "Create the organisation, connect Google, invite officers, and start from a clean admin workspace.",
  },
  {
    title: "Meetings to minutes",
    text: "Run a meeting, sync or paste a transcript, and publish Claude-generated minutes with action items.",
  },
  {
    title: "Treasury workflows",
    text: "Show dues, campaigns, budget lines, contribution records, and exports in one flow.",
  },
  {
    title: "AI audit report",
    text: "Generate an end-of-period report with weighted scoring, executive summary, category verdicts, and handover recommendations.",
  },
];

export default function HomePage() {
  return (
    <main className="stitch-landing">
      <nav className="stitch-nav">
        <div className="stitch-nav-inner">
          <Link href="/" className="stitch-logo" aria-label="Quorum home">
            <BrandWordmark />
          </Link>
          <div className="stitch-links">
            <a href="#features">Features</a>
            <a href="#solutions">Solutions</a>
            <a href="#pricing">Pricing</a>
            <a href="#resources">Resources</a>
          </div>
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

      <header className="stitch-hero stitch-section" id="features">
        <div>
          <p className="stitch-badge">Student body operating system</p>
          <h1>
            Where student bodies <span>get things done.</span>
          </h1>
          <p>
            Run members, meetings, dues, budgets, campaigns, links, and announcements from one structured workspace
            designed for campus leadership teams.
          </p>
          <div className="stitch-hero-ctas">
            <Link href="/register" className="stitch-hero-primary">
              Start a workspace
            </Link>
            <a href="#pricing" className="stitch-hero-secondary">
              View pricing
            </a>
          </div>
        </div>
        <div className="stitch-hero-art">
          <article className="stitch-app-window">
            <header className="stitch-app-window-top">
              <div>
                <strong>Quorum workspace</strong>
                <span>Microsoft Learn Student Ambassadors Unilag</span>
              </div>
              <div className="stitch-window-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            </header>
            <div className="stitch-app-window-body">
              <aside className="stitch-app-nav">
                <span className="active">Dashboard</span>
                <span>Members</span>
                <span>Meetings</span>
                <span>Campaigns</span>
                <span>Budgets</span>
              </aside>
              <div className="stitch-app-main">
                <div className="stitch-app-stats">
                  <article>
                    <small>Members</small>
                    <strong>326</strong>
                  </article>
                  <article>
                    <small>Paid dues</small>
                    <strong>71%</strong>
                  </article>
                  <article>
                    <small>Open actions</small>
                    <strong>12</strong>
                  </article>
                </div>
                <div className="stitch-app-panels">
                  <article className="stitch-app-panel">
                    <div className="stitch-app-panel-head">
                      <strong>Campaign progress</strong>
                      <span>₦742k / ₦1.2m</span>
                    </div>
                    <div className="stitch-progress-track">
                      <span style={{ width: "62%" }} />
                    </div>
                    <ul>
                      <li>Donations link active</li>
                      <li>3 funding streams attached</li>
                      <li>48 confirmed contributors</li>
                    </ul>
                  </article>
                  <article className="stitch-app-panel">
                    <div className="stitch-app-panel-head">
                      <strong>Minutes assistant</strong>
                      <span>Claude ready</span>
                    </div>
                    <div className="stitch-mini-chart">
                      <span style={{ height: "36%" }} />
                      <span style={{ height: "56%" }} />
                      <span style={{ height: "74%" }} />
                      <span style={{ height: "100%" }} />
                      <span style={{ height: "68%" }} />
                    </div>
                    <ul>
                      <li>Transcript synced</li>
                      <li>6 action items extracted</li>
                      <li>Minutes published to officers</li>
                    </ul>
                  </article>
                </div>
              </div>
            </div>
          </article>
        </div>
      </header>

      <section className="stitch-values stitch-section" id="solutions">
        <div className="stitch-intro">
          <h2>Designed for impact, not admin clutter.</h2>
          <p>
            Quorum brings CRM-like structure to student leadership: cleaner workflows, clearer permissions, and
            better visibility across the whole body.
          </p>
        </div>

        <div className="stitch-value-grid">
          {valueCards.map((item) => (
            <article key={item.title} className="stitch-value-card">
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="stitch-showcase stitch-section">
        <div className="stitch-intro">
          <p className="eyebrow">Inside the product</p>
          <h2>Actual operational views, not generic marketing blocks.</h2>
          <p>
            Show judges exactly how the workspace feels: fundraising visibility, meeting intelligence, and member
            administration in one system.
          </p>
        </div>
        <div className="stitch-showcase-grid">
          {workflowCards.map((card) => (
            <article key={card.title} className="stitch-preview-card">
              <div className="stitch-preview-top">
                <p className="eyebrow">{card.eyebrow}</p>
                <h3>{card.title}</h3>
              </div>
              <div className="stitch-preview-stats">
                {card.stats.map((stat) => (
                  <div key={stat.label}>
                    <small>{stat.label}</small>
                    <strong>{stat.value}</strong>
                  </div>
                ))}
              </div>
              <ul className="stitch-preview-list">
                {card.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section className="stitch-pricing stitch-section" id="pricing">
        <div className="stitch-intro">
          <p className="eyebrow">Business model</p>
          <h2>Role-based tiered pricing. Designed for student budgets.</h2>
          <p>
            Every workspace has a Super Admin, Subteam Leads, and Core Members. Pricing scales with team size, not
            with the wider membership.
          </p>
        </div>
        <div className="stitch-pricing-grid">
          {pricingPlans.map((plan) => (
            <article key={plan.name} className={`stitch-pricing-card ${plan.accent}`}>
              <div className="stitch-pricing-band" aria-hidden="true" />
              <p className="stitch-plan-name">{plan.name}</p>
              <h3>{plan.price}</h3>
              <p className="stitch-plan-cadence">{plan.cadence}</p>
              <div className="stitch-plan-summary">
                <strong>{plan.seats}</strong>
                <p>{plan.ai}</p>
              </div>
              <ul className="stitch-plan-features">
                {plan.features.map((feature) => (
                  <li key={feature}>{feature}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
        <p className="stitch-pricing-note">
          Additional AI credits available: ₦1,500 / 50 credits · ₦4,500 / 200 credits · ₦9,000 / 500 credits
        </p>
      </section>

      <section className="stitch-proof stitch-section" id="resources">
        <p>Trusted by visionary student leaders across</p>
        <div>
          <span>UNILAG</span>
          <span>OAU</span>
          <span>UI</span>
          <span>ABU</span>
          <span>COVENANT</span>
        </div>
      </section>

      <section className="stitch-resources stitch-section">
        <div className="stitch-intro">
          <h2>Resources for a strong technical demo.</h2>
          <p>Walk judges through the exact flows that matter: setup, governance, finance, and AI-enabled meetings.</p>
        </div>
        <div className="stitch-resource-grid">
          {resourceCards.map((item) => (
            <article key={item.title} className="stitch-value-card">
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className="stitch-footer">
        <div>
          <BrandWordmark className="footer-logo" />
          <p>© 2026 Quorum Student Systems. Empowering student leadership.</p>
        </div>
        <div>
          <a href="#">Terms</a>
          <Link href="/privacy">Privacy</Link>
          <a href="#">Accessibility</a>
          <a href="mailto:support@quorum.ng">Support</a>
        </div>
      </footer>
    </main>
  );
}
