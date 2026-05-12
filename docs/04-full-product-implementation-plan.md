# Quorum Full Product Implementation Plan

This plan is derived from `Quorum_Product_Specification.docx` and maps the full product vision into buildable backend, frontend, data, and integration work. The current codebase already has a starter FastAPI + Next.js app with workspaces, members, dues cycles, events, campaigns, links, public pages, login/register screens, and a CRM-style workspace shell. The spec requires turning that scaffold into a production multi-tenant SaaS with real identity, RBAC, payments, AI meeting intelligence, and complete workspace operations.

## 1. Product Shape

Quorum is a multi-tenant SaaS for student bodies and small admin teams. Each student body is a workspace with isolated data, a public slug, internal admin dashboard, member-facing flows, and public pages for events, donations, links, and the portal.

The platform should support two broad user classes:

1. Admin members: exco officers or team leads with dashboard access, role-specific permissions, and paid-seat implications.
2. General members: regular students with personal/member access for announcements, dues, events, donations, and tasks assigned to them.

The implementation must treat workspace isolation, RBAC, and auditability as core architecture, not later decorations.

## 2. Current State Versus Target

Already started:

1. Workspace creation and slug-based routing.
2. Basic auth-like login/register responses, but no secure password storage or JWT/session cookies yet.
3. Workspace dashboard shell and pages for members, events, campaigns, dues, links.
4. Basic models for Workspace, Member, DuesCycle, Event, Campaign, ShortLink.
5. Public route placeholders for portal, events, donations, and short links.
6. Members invite modal can add members directly, but not true email invites or token acceptance.

Major gaps:

1. Real User identity model separate from WorkspaceMember.
2. Password hashing, JWT/session cookies, refresh flow, email verification, password reset.
3. RBAC roles/permissions, owner transfer, role transfer.
4. Payment gateway integrations and webhooks.
5. Dues payment ledger, manual receipt queue, defaulter exports.
6. Campaign contributions, funding streams, public checkout flow.
7. Meetings, minutes, Claude processing, action items, tasks.
8. Announcements, notification feed, email dispatch.
9. Settings, integrations, billing, portal customization.
10. Production MongoDB backup, index, and migration workflows.

## 3. Foundation Architecture

### Backend

Move the API toward these domains:

1. `/api/v1/auth`: register, login, refresh, logout, me, verify email, password reset.
2. `/api/v1/workspaces`: workspace CRUD, overview, settings, invite links.
3. `/api/v1/roles`: role CRUD and permission matrix.
4. `/api/v1/members`: workspace members, invitations, role changes, removals, transfers.
5. `/api/v1/dues`: cycles, payment initiation, manual receipt review, defaulters, exports.
6. `/api/v1/events`: event CRUD, RSVP, attendance, analytics.
7. `/api/v1/campaigns`: campaigns, funding streams, contributions, sponsorships.
8. `/api/v1/budgets`: budgets, budget lines, expenditure logs, PDF export.
9. `/api/v1/meetings`: meeting invites, agendas, attendance, minutes, transcript processing.
10. `/api/v1/tasks`: tasks, statuses, linked records, assignee views.
11. `/api/v1/announcements`: feed, targeting, scheduling, archive.
12. `/api/v1/links`: short links, redirects, analytics.
13. `/api/v1/integrations`: Paystack, Flutterwave, Google, Fireflies, Zoom.
14. `/api/v1/webhooks`: payment and transcript webhooks.
15. `/api/v1/notifications`: in-app notification feed and read state.
16. `/api/v1/ai`: Claude transcript processing and narrative drafting.

### Data Model

Replace the current simplified member model with these core tables:

1. `users`: full_name, email, phone, password_hash, email_verified, timestamps.
2. `workspaces`: name, slug, logo_url, brand_color, body_type, university, department, owner_id, plan.
3. `workspace_members`: workspace_id, user_id, role_id, is_general_member, joined_at, status.
4. `roles`: workspace_id, name, description, is_system_role, permissions JSON.
5. `invitations`: workspace_id, email, role_id, invited_by, token_hash, expires_at, accepted_at, revoked_at.
6. `dues_cycles`, `dues_payments`, `manual_receipts`.
7. `events`, `event_attendees`.
8. `campaigns`, `funding_streams`, `contributions`.
9. `budgets`, `budget_lines`, `expenditures`.
10. `meetings`, `meeting_minutes`, `action_items`.
11. `tasks`.
12. `announcements`.
13. `short_links`, `short_link_clicks`.
14. `integrations`.
15. `notifications`.
16. `audit_logs`.

Use Alembic migrations before adding more production data. Keep foreign keys workspace-scoped where possible.

### Authorization

Every private endpoint must resolve:

1. Current authenticated user.
2. Current workspace.
3. Current workspace membership.
4. Membership role and permission set.

Permissions should be action-oriented, for example:

1. `dashboard.view`
2. `members.view`, `members.invite`, `members.edit`, `members.remove`
3. `dues.view`, `dues.manage`, `dues.confirm_payment`
4. `events.view`, `events.manage`, `events.attendance`
5. `meetings.view`, `meetings.manage`, `meetings.publish_minutes`
6. `tasks.view`, `tasks.assign`, `tasks.manage_all`
7. `campaigns.view`, `campaigns.manage`, `campaigns.confirm_contribution`
8. `budgets.view`, `budgets.manage`
9. `announcements.view`, `announcements.publish`
10. `settings.view`, `settings.edit`
11. `roles.manage`
12. `billing.manage`
13. `integrations.manage`
14. `ownership.transfer`

## 4. End-to-End User Flow Implementation

### 4.1 Workspace Creation

Target user flow:

1. User visits landing page and clicks create workspace.
2. Step 1 collects organization name, university, body type, faculty/department, editable workspace slug.
3. Step 2 collects owner name, school email, phone, role title, password, confirm password.
4. Backend creates user, workspace, system roles, owner membership, default secretary role, and setup checklist.
5. Verification email is sent.
6. User verifies email and lands on dashboard.

Implementation:

1. Add `User`, `Role`, `WorkspaceMember`, `EmailVerificationToken`.
2. Hash passwords with `passlib[bcrypt]`.
3. Return secure session via httpOnly cookie or JWT access/refresh pair.
4. Add email provider abstraction for verification.
5. Add dashboard setup checklist table keyed by workspace and user.

Frontend routes:

1. `/register`
2. `/verify-email`
3. `/login`
4. `/forgot-password`
5. `/reset-password`

### 4.2 Login And Session

Target user flow:

1. User enters workspace slug, email or matric number, password.
2. Backend validates credentials and membership in that workspace.
3. User lands on the workspace dashboard matching their permissions.
4. Forgot password sends reset email and allows password reset with token.

Implementation:

1. Enforce workspace slug in login.
2. Use httpOnly cookies for browser session if possible.
3. Build `GET /auth/me` returning user and workspace memberships.
4. Add middleware/client guard for private routes.

### 4.3 Member Invitation

Invite by email:

1. Admin opens Members -> Invite.
2. Enters email, selects role, optional note.
3. Backend creates invitation token expiring in 72 hours.
4. Email sends unique invite URL.
5. Invitee accepts; if new, creates account; if existing, joins workspace.
6. Member status changes from pending to active.

Invite by link:

1. Admin generates bulk invite link with default role and optional expiry.
2. Anyone with link can join as that default role.
3. Admin can revoke link.

Implementation:

1. `POST /workspaces/{id}/invitations`
2. `GET /invite/{token}`
3. `POST /invite/{token}/accept`
4. `POST /workspaces/{id}/invite-links`
5. `POST /join/{invite_link_token}`
6. Members page tabs: Invite by email, Invite by link.

### 4.4 Roles, Permissions, And Transfers

Target user flow:

1. Owner opens Settings -> Roles & Permissions.
2. Can create/edit/delete custom roles.
3. Cannot delete Owner or Secretary, only rename display labels.
4. Permission changes apply to all users with that role.
5. Owner can transfer ownership with password re-entry and receiver acceptance.
6. Non-owner role transfer can reassign tasks/responsibilities.

Implementation:

1. Add role CRUD screens under `settings/roles`.
2. Add permission editor grouped by module.
3. Add transfer workflow modals.
4. Add audit log entries for role permission changes and transfers.
5. Add email notifications for transfers.

### 4.5 Dashboard

Target dashboard widgets:

1. Metric cards: total members, dues paid percent, events this semester, campaign progress.
2. Dues alert banner.
3. Upcoming events.
4. Active campaign widget.
5. My tasks.
6. Pinned announcements.
7. Recent activity feed.
8. Setup checklist on first login.

Implementation:

1. Expand `/workspaces/slug/{slug}/overview` into a true dashboard aggregation endpoint.
2. Add tasks, announcements, activity, and setup checklist tables.
3. Make every metric card link into its module.

### 4.6 Dues Collection

Exco flow:

1. Dues -> New dues cycle.
2. Enter name, amount, optional breakdown, deadline, applicable levels.
3. Publish; members notified.

Member payment flow:

1. Member sees unpaid status.
2. Clicks Pay now.
3. Paystack or Flutterwave checkout opens.
4. Webhook marks payment paid.
5. Member receives confirmation.

Manual fallback:

1. Member uploads receipt.
2. Treasurer reviews queue.
3. Confirm or reject updates status.

Implementation:

1. Tables: `dues_cycles`, `dues_payments`, `manual_receipts`.
2. Endpoints for cycle CRUD, payment initiation, webhook confirmation, receipt review, defaulter export.
3. Integrations settings for Paystack/Flutterwave credentials.
4. UI: dues overview cards, cycles list, create cycle modal/page, payment ledger, manual review queue, defaulter list.

### 4.7 Events

Admin flow:

1. Events -> Create event.
2. Enter title, type, date/time, venue, description, thumbnail, RSVP toggle, capacity, external link, tags.
3. Publish and get public link plus QR code.

Member/public flow:

1. Open `/e/[eventSlug]`.
2. View event info and RSVP.
3. Admin tracks attendance manually or via QR scan.

Implementation:

1. Expand `Event` model with status, thumbnail_url, external_link, tags, created_by.
2. Add `EventAttendee`.
3. Build events list filters, event detail page, public event page, attendance tracker, analytics.
4. Add OG metadata for WhatsApp previews.

### 4.8 Fundraising

Exco flow:

1. Fundraising -> New campaign.
2. Enter name, target, deadline, cover image, description, optional linked budget.
3. Add funding streams: sponsorship, donation link, dues levy, ticket sales, manual entry.
4. Publish public donation page.

Donor flow:

1. Opens `/donate/[campaignSlug]`.
2. Sees campaign info, progress, contributor count.
3. Enters name/anonymous choice and amount.
4. Pays through gateway.
5. Webhook confirms contribution.

Implementation:

1. Expand `Campaign` with deadline, cover_url, description, linked_budget_id.
2. Add `FundingStream`, `Contribution`.
3. Build campaign list, create campaign, campaign detail dashboard, stream breakdown, pending queue, contributor ledger, sponsorship logger.
4. Build public donation page with Paystack/Flutterwave checkout initiation.

### 4.9 Meetings And Claude Intelligence

Meeting setup:

1. Meetings -> New meeting.
2. Add title, type, date/time, venue or virtual link, agenda builder, quorum threshold, cover image.
3. Publish public invite/share page.

Automatic transcript flows:

1. Google Meet transcript lands in watched Drive folder.
2. Fireflies webhook sends transcript-ready event.
3. Zoom webhook reports transcript completion.
4. Backend fetches transcript and queues Claude processing.

Manual transcript flow:

1. Officer uploads/pastes transcript or audio.
2. Audio is transcribed first if needed.
3. Claude returns minutes, summary, and action items.
4. Secretary reviews draft and publishes.
5. Action items become tasks.

Implementation:

1. Tables: `meetings`, `meeting_minutes`, `action_items`, `tasks`.
2. Background job queue for transcript processing.
3. Claude adapter that returns structured JSON and validates it.
4. Fuzzy member matching for assignees.
5. UI: meetings list, create meeting, live meeting view, minutes draft editor, published minutes, transcript upload.

### 4.10 Tasks

Manual task flow:

1. Tasks -> New task.
2. Add title, description, assignee, due date, priority, linked module.
3. Assignee receives notification.

Meeting-generated flow:

1. Claude extracts action item.
2. Backend creates task linked to meeting minutes.
3. Assignee updates status from To do to In Progress to Done.

Implementation:

1. Add task board and task list routes.
2. Add endpoints for CRUD, status changes, filters, assignee view.
3. Add overdue notification job.

### 4.11 Announcements

Admin flow:

1. Announcements -> New announcement.
2. Enter title, rich text body, optional attachment.
3. Choose target audience: all, level, admin, role-specific.
4. Publish now or schedule.
5. Optionally pin.

Member flow:

1. Receives email and in-app notification.
2. Announcement appears in feed.

Implementation:

1. Add `Announcement` model and targeting fields.
2. Add scheduled publish background job.
3. Add feed, detail, archive, pin/unpin, read counts.

### 4.12 Budget Planner

Flow:

1. Create budget with program name and planned line items.
2. Log expenditures against line items with receipt upload.
3. View planned vs actual variance and burn rate.
4. Export PDF report.

Implementation:

1. Tables: `budgets`, `budget_lines`, `expenditures`.
2. UI: budget list, create budget, budget detail, expenditure logger, PDF export.
3. Link campaigns/events to budgets where relevant.

### 4.13 Smart Links And Portal

Smart links:

1. Create custom short slug, destination, optional expiry.
2. Redirect through `/r/[slug]`.
3. Track click count and analytics.

Portal:

1. Public page at `quorum.ng/[slug]` or `/portal/[workspaceSlug]`.
2. Shows logo, name, tagline, active campaign, published links, upcoming events, latest announcements.
3. Settings controls brand color, logo, tagline, and visible sections.

Implementation:

1. Add `short_link_clicks`.
2. Add portal settings fields to workspace.
3. Build link analytics and QR download.

### 4.14 Settings, Integrations, Billing

Settings sections:

1. Workspace settings: name, slug, body type, university, department, logo, brand color, tagline.
2. Roles & permissions.
3. Members & invitations.
4. Integrations.
5. Notifications.
6. Billing & plan.

Integrations:

1. Paystack/Flutterwave: API keys, verify, connect/disconnect.
2. Google: OAuth, Drive folder watch, Calendar matching.
3. Fireflies: API key, verify, webhook registration.
4. Zoom: OAuth and transcript webhook.

Billing:

1. Plans: Free, Growth, Pro.
2. Seat counts for admin members.
3. AI credit balance and top-ups.
4. Subscription invoices.

Implementation:

1. Add settings route group.
2. Add integration model with encrypted secrets.
3. Add notification preferences table.
4. Add billing tables after the core product is stable.

## 5. Recommended Build Phases

### Phase 0: Stabilize The Foundation

Goal: make the existing app reliable enough to extend.

1. Introduce Alembic migrations.
2. Split `Member` into `User` and `WorkspaceMember`.
3. Add password hashing, JWT/httpOnly session, `GET /auth/me`.
4. Add email verification and password reset skeleton.
5. Add RBAC middleware/dependencies.
6. Seed default roles and permissions on workspace creation.
7. Stop relying on localStorage as the source of auth truth.

Exit criteria:

1. A user can register, verify email, log in, and access only their workspace.
2. Owner and Secretary roles exist automatically.
3. Private endpoints reject unauthorized access.

### Phase 1: Members, Roles, And Setup Checklist

Goal: make workspace onboarding complete.

1. Roles & permissions settings page.
2. Members list with search, filters, status.
3. Email invite and invite-link flows.
4. Invite acceptance.
5. Role transfer and owner transfer skeleton.
6. Dashboard setup checklist.

Exit criteria:

1. Owner can invite admin and general members.
2. Role permissions control UI visibility and API access.
3. Pending, active, revoked invitations are represented.

### Phase 2: Dues And Payments

Goal: implement the primary value proposition.

1. Dues cycle creation with breakdown and applicable levels.
2. Member dues status.
3. Paystack connection and checkout initiation.
4. Paystack webhook for `charge.success`.
5. Manual receipt upload and treasurer review queue.
6. Defaulter list and CSV export.

Exit criteria:

1. Payment updates dues automatically through webhook.
2. Manual receipt confirmation path works.
3. Dashboard dues metrics update from real payment data.

### Phase 3: Events And Public Sharing

Goal: support viral/shareable public pages.

1. Events CRUD and event detail.
2. Public event page with RSVP.
3. RSVP list and attendance tracking.
4. QR code and copyable event link.
5. OG metadata for WhatsApp previews.
6. Events analytics.

Exit criteria:

1. Admin can publish an event and share it publicly.
2. Members/public users can RSVP.
3. Admin can track attendance.

### Phase 4: Fundraising And Campaigns

Goal: complete the financial picture beyond dues.

1. Campaign creation with target, deadline, cover, description.
2. Funding streams.
3. Public donation page.
4. Payment gateway donation flow.
5. Contribution ledger and sponsorship logger.
6. Campaign dashboard and export.

Exit criteria:

1. Donor can pay without logging in.
2. Webhook updates contribution total.
3. Campaign page shows progress and contributor ledger.

### Phase 5: Meetings, Claude, And Tasks

Goal: deliver the major AI differentiator.

1. Meetings list and create meeting.
2. Agenda builder and public meeting invite.
3. Manual transcript upload/paste.
4. Claude processing into minutes, summary, action items.
5. Draft review and publish flow.
6. Task creation from action items.
7. Task board/list and my tasks.

Exit criteria:

1. Raw transcript becomes editable structured minutes.
2. Action items become assigned tasks.
3. Dashboard shows my tasks.

### Phase 6: Integrations, Announcements, Budget, Portal

Goal: round out the platform.

1. Google Meet, Fireflies, Zoom integrations.
2. Announcements feed and scheduling.
3. Budget planner and expenditure logger.
4. Portal customization.
5. Smart link analytics.
6. Notification preferences.

Exit criteria:

1. Automatic transcript ingestion works for at least one provider.
2. Portal shows live workspace content.
3. Announcements and budgets are production usable.

### Phase 7: Billing, AI Credits, Production Hardening

Goal: production SaaS readiness.

1. Plans, admin seat limits, billing portal.
2. AI credit tracking and top-ups.
3. Audit logs across sensitive actions.
4. Rate limiting and abuse protection.
5. File upload storage policy.
6. Observability and error reporting.
7. E2E tests for critical flows.

## 6. Demo Path

For a 5-minute demo, build toward this story first:

1. Signup: create `CSC Department Student Body`.
2. Dues: create dues cycle and show payment path or simulated webhook.
3. Fundraising: create campaign and show public donation page.
4. Meetings: upload transcript and show Claude-generated minutes/tasks.

For a 15-minute demo, add:

1. Role creation and member invitations.
2. Event creation and public RSVP page.
3. Ownership transfer walkthrough.
4. Dashboard setup checklist and live metrics.

## 7. Immediate Next Implementation Tasks

1. Add Alembic and create a migration for real identity/RBAC tables.
2. Implement secure auth with password hashing and `GET /auth/me`.
3. Add `Role`, `WorkspaceMember`, and permission enforcement.
4. Refactor existing routes to use authenticated workspace membership instead of raw workspace IDs.
5. Build Settings -> Roles & Permissions.
6. Replace current direct member creation with email invite and invite-link acceptance.
7. Expand dashboard overview to include setup checklist, tasks, announcements, and activity.
8. Implement dues payment ledger and manual receipt review.

This order keeps the product coherent: identity and permissions first, then the high-value operational modules.
