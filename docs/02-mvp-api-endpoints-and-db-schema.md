# Quorum MVP API Endpoints and DB Schema

## 1. API Design Principles

1. All private endpoints are tenant-scoped by `workspace_id`.
2. Role-based authorization enforced server-side for each action.
3. AI verification is advisory; only exco confirmation moves funds/dues states.
4. Public endpoints are read-only or controlled submission endpoints with anti-abuse checks.

Base path: `/api/v1`

## 2. Auth and Identity

## `POST /auth/register`

Create user account and optionally join a workspace via invite token.

## `POST /auth/login`

Authenticate and return access/refresh tokens.

## `POST /auth/refresh`

Rotate access token.

## `GET /auth/me`

Return current user profile and workspace memberships.

## 3. Workspace and Membership

## `POST /workspaces`

Create workspace (student body).

## `GET /workspaces/{workspace_id}`

Get workspace profile.

## `PATCH /workspaces/{workspace_id}`

Update workspace branding and settings.

## `GET /workspaces/{workspace_id}/members`

List members with filters (`role`, `level`, `dues_status`).

## `POST /workspaces/{workspace_id}/members/invite`

Create invite link for member onboarding.

## `PATCH /workspaces/{workspace_id}/members/{user_id}`

Update role/profile fields.

## 4. Dues Module

## `POST /workspaces/{workspace_id}/dues-cycles`

Create dues cycle.

## `GET /workspaces/{workspace_id}/dues-cycles`

List dues cycles.

## `GET /workspaces/{workspace_id}/dues-cycles/{cycle_id}`

Get cycle details and totals.

## `POST /workspaces/{workspace_id}/dues-cycles/{cycle_id}/submissions`

Member submits proof of payment.

## `GET /workspaces/{workspace_id}/dues-submissions/pending`

Exco verification queue.

## `POST /workspaces/{workspace_id}/dues-submissions/{submission_id}/confirm`

Confirm payment (exco action).

## `POST /workspaces/{workspace_id}/dues-submissions/{submission_id}/reject`

Reject payment with reason.

## `GET /workspaces/{workspace_id}/dues/reports/defaulters`

Defaulter report.

## `GET /workspaces/{workspace_id}/dues/reports/export.csv`

CSV export.

## 5. Events Module

## `POST /workspaces/{workspace_id}/events`

Create event.

## `GET /workspaces/{workspace_id}/events`

List events by status/date/type.

## `GET /workspaces/{workspace_id}/events/{event_id}`

Private event detail.

## `PATCH /workspaces/{workspace_id}/events/{event_id}`

Update event.

## `POST /workspaces/{workspace_id}/events/{event_id}/rsvp`

Member RSVP.

## `POST /workspaces/{workspace_id}/events/{event_id}/check-ins`

Batch check-ins.

## `GET /workspaces/{workspace_id}/events/analytics/overview`

Events analytics.

Public:

1. `GET /public/e/{event_slug}`
2. `GET /public/e/{event_slug}/og`

## 6. Meetings Module

## `POST /workspaces/{workspace_id}/meetings`

Create meeting invite.

## `GET /workspaces/{workspace_id}/meetings`

List meetings.

## `GET /workspaces/{workspace_id}/meetings/{meeting_id}`

Get meeting detail.

## `POST /workspaces/{workspace_id}/meetings/{meeting_id}/attendance`

Record attendance.

## `PUT /workspaces/{workspace_id}/meetings/{meeting_id}/minutes`

Save live minutes.

## `POST /workspaces/{workspace_id}/meetings/{meeting_id}/minutes/assist`

AI-assisted minutes formatting and action-item extraction.

Public:

1. `GET /public/m/{meeting_slug}`
2. `GET /public/m/{meeting_slug}/og`

## 7. Campaigns and Budget Module

## `POST /workspaces/{workspace_id}/budgets`

Create budget.

## `GET /workspaces/{workspace_id}/budgets/{budget_id}`

Get budget view.

## `POST /workspaces/{workspace_id}/budgets/{budget_id}/line-items`

Add line item.

## `PATCH /workspaces/{workspace_id}/budgets/{budget_id}/line-items/{line_item_id}`

Update planned/actual amounts.

## `POST /workspaces/{workspace_id}/campaigns`

Create campaign.

## `GET /workspaces/{workspace_id}/campaigns/{campaign_id}`

Campaign dashboard detail.

## `POST /workspaces/{workspace_id}/campaigns/{campaign_id}/streams`

Add funding stream.

## `POST /workspaces/{workspace_id}/campaigns/{campaign_id}/contributions/manual`

Exco manual contribution logging.

## `GET /workspaces/{workspace_id}/campaigns/{campaign_id}/contributions/pending`

Pending donor verification queue.

## `POST /workspaces/{workspace_id}/campaigns/contributions/{contribution_id}/confirm`

Confirm contribution.

## `POST /workspaces/{workspace_id}/campaigns/contributions/{contribution_id}/reject`

Reject contribution.

Public:

1. `GET /public/donate/{campaign_slug}`
2. `POST /public/donate/{campaign_slug}/submissions`

## 8. Links, Portal, Announcements

## `POST /workspaces/{workspace_id}/links`

Create short link.

## `GET /workspaces/{workspace_id}/links`

List links and analytics.

## `PATCH /workspaces/{workspace_id}/links/{link_id}`

Update destination, expiry, status.

## `GET /r/{slug}`

Short-link redirect endpoint and click logging.

## `GET /public/portal/{workspace_slug}`

Public portal content.

## `POST /workspaces/{workspace_id}/announcements`

Create announcement.

## `GET /workspaces/{workspace_id}/announcements`

List announcements.

## `PATCH /workspaces/{workspace_id}/announcements/{announcement_id}`

Pin, archive, schedule, or edit.

## 9. AI Receipt Verification Contract

Internal processing endpoint (service-to-service):

## `POST /internal/ai/receipt-extract`

Input:

1. `image_url`
2. `declared_amount`
3. `context_type` (`dues` or `campaign`)

Output:

1. `extracted_amount`
2. `extracted_sender_name`
3. `extracted_provider`
4. `extracted_reference`
5. `extracted_datetime`
6. `status` (`verified_pending`, `mismatch_manual_review`, `unreadable_manual_review`)
7. `confidence`

## 10. Database Schema (MVP)

Current implemented schema source is `app/models.py` (SQLAlchemy models with SQLite default).

Core entities:

1. `workspaces`
2. `users`
3. `workspace_memberships`
4. `dues_cycles`
5. `dues_submissions`
6. `events`, `event_rsvps`, `event_checkins`
7. `meetings`, `meeting_attendance`, `meeting_minutes`, `meeting_action_items`
8. `budgets`, `budget_line_items`
9. `campaigns`, `funding_streams`, `contributions`
10. `short_links`, `short_link_clicks`
11. `announcements`
12. `audit_log_events`

## 11. Critical State Machines

## Dues submission state

`pending` -> `ai_verified_pending` -> (`confirmed` or `rejected`)

`pending` -> `mismatch_manual_review` -> (`confirmed` or `rejected`)

`pending` -> `unreadable_manual_review` -> (`confirmed` or `rejected`)

## Contribution state

`pending` -> `ai_verified_pending` -> (`confirmed` or `rejected`)

`pending` -> `mismatch_manual_review` -> (`confirmed` or `rejected`)

## 12. Security and Multi-Tenant Guardrails

1. All private table queries include `workspace_id` filters.
2. Composite indexes prioritize `(workspace_id, created_at)` and workflow statuses.
3. Public routes never expose non-public member financial records.
4. All confirmation/rejection actions write immutable audit log rows.
