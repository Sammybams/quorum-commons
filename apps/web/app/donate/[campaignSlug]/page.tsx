import type { Metadata } from "next";
import { notFound } from "next/navigation";
import BrandWordmark from "@/components/brand-wordmark";
import { getCampaignBySlug } from "@/lib/api/campaigns";
import { DonationForm } from "./donation-form";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

export async function generateMetadata({ params }: { params: { campaignSlug: string } }): Promise<Metadata> {
  const campaign = await getCampaignBySlug(params.campaignSlug);
  if (!campaign) return {};

  const title = `${campaign.name} | ${campaign.workspace_name}`;
  const description = `${campaign.workspace_name} is raising NGN ${campaign.target_amount.toLocaleString("en-NG")} on Quorum.`;
  const ogImage = `${APP_URL}/api/og/campaign/${campaign.slug}`;

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
      url: `${APP_URL}/donate/${campaign.slug}`,
      images: [{ url: ogImage, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [ogImage],
    },
  };
}

export default async function DonatePage({ params }: { params: { campaignSlug: string } }) {
  const campaign = await getCampaignBySlug(params.campaignSlug);
  if (!campaign) notFound();
  const percent = campaign.target_amount > 0 ? Math.round((campaign.raised_amount / campaign.target_amount) * 100) : 0;

  return (
    <main className="donation-page">
      <nav className="donation-nav">
        <BrandWordmark />
        <span>{campaign.workspace.name}</span>
      </nav>

      <section className="donation-grid">
        <div className="donation-hero">
          <p className="eyebrow">Fundraising campaign</p>
          <h1>{campaign.name}</h1>
          <p>
            Help {campaign.workspace.name} reach its goal. Every contribution is tracked against the public campaign
            ledger.
          </p>

          <div className="donation-progress-card">
            <div>
              <span>Raised</span>
              <strong>NGN {campaign.raised_amount.toLocaleString()}</strong>
            </div>
            <div>
              <span>Target</span>
              <strong>NGN {campaign.target_amount.toLocaleString()}</strong>
            </div>
            <div>
              <span>Contributors</span>
              <strong>{campaign.contributor_count}</strong>
            </div>
            <div className="progress-track">
              <span style={{ width: `${Math.min(percent, 100)}%` }} />
            </div>
            <p>{Math.min(percent, 100)}% funded</p>
          </div>

          {campaign.funding_streams.length ? (
            <div className="stream-list">
              {campaign.funding_streams.map((stream) => {
                const streamTarget = stream.target_amount || campaign.target_amount;
                const streamPercent = Math.min(100, Math.round((stream.raised_amount / Math.max(streamTarget, 1)) * 100));
                return (
                  <article key={stream.id}>
                    <div>
                      <strong>{stream.name}</strong>
                      <span>{stream.stream_type}</span>
                    </div>
                    <p>NGN {stream.raised_amount.toLocaleString()}</p>
                    <div className="progress-track slim">
                      <span style={{ width: `${streamPercent}%` }} />
                    </div>
                  </article>
                );
              })}
            </div>
          ) : null}
        </div>

        <DonationForm campaignSlug={campaign.slug} fundingStreams={campaign.funding_streams} />
      </section>
    </main>
  );
}
