# Quorum Frontend Route Map and Page-by-Page Build Checklist

## 1. Frontend Stack Baseline

1. Next.js (App Router) + TypeScript
2. Tailwind CSS (or custom CSS modules) in `frontend`
3. Data fetching via `frontend/lib/api.ts`
4. Authenticated route groups for exco/member experiences
5. Public server-rendered pages for OG previews

## 2. Route Map

## App shell and auth

1. `/` - landing page
2. `/login` - user login
3. `/register` - user registration
4. `/onboarding/workspace` - create or join workspace

## Authenticated app (private)

Use route group: `/(app)/[workspaceSlug]/...`

1. `/(app)/[workspaceSlug]/dashboard`
2. `/(app)/[workspaceSlug]/members`
3. `/(app)/[workspaceSlug]/dues`
4. `/(app)/[workspaceSlug]/events`
5. `/(app)/[workspaceSlug]/events/new`
6. `/(app)/[workspaceSlug]/meetings`
7. `/(app)/[workspaceSlug]/meetings/new`
8. `/(app)/[workspaceSlug]/campaigns`
9. `/(app)/[workspaceSlug]/campaigns/[campaignSlug]`
10. `/(app)/[workspaceSlug]/budgets`
11. `/(app)/[workspaceSlug]/links`
12. `/(app)/[workspaceSlug]/announcements`
13. `/(app)/[workspaceSlug]/settings/branding`

## Public routes

1. `/e/[eventSlug]` - public event page with OG metadata
2. `/m/[meetingSlug]` - public meeting invite page with OG metadata
3. `/donate/[campaignSlug]` - public donation page
4. `/portal/[workspaceSlug]` - public branded portal page
5. `/r/[slug]` - short-link redirect entry route

## 3. Layout and UX Shell Plan

1. Global layout: typography, color tokens, spacing, and mobile-first breakpoints.
2. App layout: sidebar + top header + content region.
3. Public layout: lightweight, campaign/event focused pages with clear CTA.
4. Reusable pieces: metric cards, status badges, tables, progress bars, verification cards, OG preview blocks.

## 4. Page-by-Page Build Checklist

## Page 1: Dashboard (`/(app)/[workspaceSlug]/dashboard`)

Build:

1. Metric cards (`total members`, `dues paid %`, `events`, `campaign progress`).
2. Dues alert banner.
3. Upcoming events widget.
4. Active campaign widget.
5. Pinned announcements list.

Connect endpoints:

1. `GET /workspaces/{workspace_id}`
2. `GET /workspaces/{workspace_id}/events`
3. `GET /workspaces/{workspace_id}/campaigns/{campaign_id}`
4. `GET /workspaces/{workspace_id}/announcements`

Done criteria:

1. All widget states covered (`loading`, `empty`, `error`, `success`).
2. Mobile layout remains usable at small widths.

## Page 2: Events Analytics (`/(app)/[workspaceSlug]/events`)

Build:

1. Event stat summary cards.
2. Attendance/event charts.
3. Event table with filters.

Connect endpoints:

1. `GET /workspaces/{workspace_id}/events`
2. `GET /workspaces/{workspace_id}/events/analytics/overview`

Done criteria:

1. Filter controls update data set correctly.
2. Table and charts share same query context.

## Page 3: Create Event (`/(app)/[workspaceSlug]/events/new`)

Build:

1. Event form.
2. Thumbnail uploader.
3. RSVP configuration.
4. Live share-preview component.

Connect endpoints:

1. `POST /workspaces/{workspace_id}/events`

Done criteria:

1. Slug generated and copyable.
2. Validation errors shown inline.

## Page 4: Dues Tracker (`/(app)/[workspaceSlug]/dues`)

Build:

1. Collection summary cards.
2. Pending verification queue.
3. Member dues status table.
4. CSV export trigger.

Connect endpoints:

1. `GET /workspaces/{workspace_id}/dues-cycles`
2. `GET /workspaces/{workspace_id}/dues-submissions/pending`
3. `POST /workspaces/{workspace_id}/dues-submissions/{submission_id}/confirm`
4. `POST /workspaces/{workspace_id}/dues-submissions/{submission_id}/reject`
5. `GET /workspaces/{workspace_id}/dues/reports/export.csv`

Done criteria:

1. Confirm/reject actions optimistically update queue.
2. Defaulter counts and totals are consistent.

## Page 5: Meeting Invite Creator (`/(app)/[workspaceSlug]/meetings/new`)

Build:

1. Meeting details form.
2. Agenda list builder.
3. Share preview card.
4. QR display/download trigger.

Connect endpoints:

1. `POST /workspaces/{workspace_id}/meetings`

Done criteria:

1. Agenda items reorder and persist correctly.
2. Generated meeting link is copyable.

## Page 6: Campaign Dashboard (`/(app)/[workspaceSlug]/campaigns/[campaignSlug]`)

Build:

1. Campaign hero and progress.
2. Funding stream chart.
3. Donation verification queue.
4. Contribution ledger with export.

Connect endpoints:

1. `GET /workspaces/{workspace_id}/campaigns/{campaign_id}`
2. `GET /workspaces/{workspace_id}/campaigns/{campaign_id}/contributions/pending`
3. `POST /workspaces/{workspace_id}/campaigns/contributions/{contribution_id}/confirm`
4. `POST /workspaces/{workspace_id}/campaigns/contributions/{contribution_id}/reject`

Done criteria:

1. Totals recalculate correctly after actions.
2. Status transitions visible and auditable in UI.

## Page 7: Budget Planner (`/(app)/[workspaceSlug]/budgets`)

Build:

1. Planned vs actual summary cards.
2. Category variance chart.
3. Line-item editable table.

Connect endpoints:

1. `POST /workspaces/{workspace_id}/budgets`
2. `GET /workspaces/{workspace_id}/budgets/{budget_id}`
3. `PATCH /workspaces/{workspace_id}/budgets/{budget_id}/line-items/{line_item_id}`

Done criteria:

1. Over-budget lines visibly flagged.
2. Numeric formatting consistent for Naira.

## Page 8: Public Donation Page (`/donate/[campaignSlug]`)

Build:

1. Public campaign header and progress.
2. Donor form.
3. Receipt upload component.
4. Submission success/failure states.

Connect endpoints:

1. `GET /public/donate/{campaign_slug}`
2. `POST /public/donate/{campaign_slug}/submissions`

Done criteria:

1. No-login flow completes in minimal steps.
2. Anti-abuse and validation messages are clear.

## Page 9: Smart Links (`/(app)/[workspaceSlug]/links`)

Build:

1. Link creation form.
2. Active links list with click counts and expiry badges.
3. Link actions (copy, disable, edit).

Connect endpoints:

1. `POST /workspaces/{workspace_id}/links`
2. `GET /workspaces/{workspace_id}/links`
3. `PATCH /workspaces/{workspace_id}/links/{link_id}`

Done criteria:

1. Slug uniqueness errors handled.
2. Link analytics refresh without full reload.

## Page 10: Public Portal (`/portal/[workspaceSlug]`)

Build:

1. Branded workspace header.
2. Active links section.
3. Upcoming events section.
4. Active campaign CTA.

Connect endpoints:

1. `GET /public/portal/{workspace_slug}`

Done criteria:

1. Fully usable on mobile.
2. Only public-safe data rendered.

## 5. OG Metadata Checklist (Public Pages)

For `/e/[eventSlug]`, `/m/[meetingSlug]`, `/donate/[campaignSlug]`, `/portal/[workspaceSlug]`:

1. Set `title`, `description`, canonical URL.
2. Set Open Graph image (`1200x630` recommended).
3. Set `twitter:card=summary_large_image`.
4. Validate preview behavior with WhatsApp and X-friendly metadata.

## 6. Frontend Sequencing (Implementation Order)

1. Build auth + shell + dashboard first.
2. Add dues and campaign workflows (highest product differentiation).
3. Add events and meetings creation + public OG pages.
4. Add links and portal pages.
5. Final pass on mobile UX, empty states, and copy.

## 7. MVP Completion Definition

MVP frontend is complete when:

1. All 10 planned pages are implemented.
2. Public OG pages render valid metadata server-side.
3. Core actions (create event, submit donation, verify payment, create short link) are executable end-to-end.
4. Mobile and desktop usability pass for all primary flows.
