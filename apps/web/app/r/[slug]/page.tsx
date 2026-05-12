import { redirect } from "next/navigation";

type ResolveResponse = {
  destination_url: string;
  click_count: number;
};

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default async function ShortLinkResolverPage({ params }: { params: { slug: string } }) {
  const res = await fetch(`${API_URL}/public/r/${params.slug}`, { cache: "no-store" });
  if (res.status === 410) {
    redirect(`/link-expired?slug=${params.slug}`);
  }
  if (!res.ok) {
    redirect("/");
  }
  const data = (await res.json()) as ResolveResponse;
  redirect(data.destination_url);
}
