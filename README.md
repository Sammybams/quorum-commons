# Quorum

Quorum is a multi-tenant community operating system built for organized groups. It gives cooperatives, student unions, faculty bodies, trade associations, clubs, and community teams one structured workspace for members, meetings, collections, events, budgets, campaigns, links, and announcements.

The product is designed to feel less like a generic admin panel and more like a real operations system for executive councils.

## Live Environments

- Frontend: https://quorum-taupe.vercel.app/
- Backend API docs: https://quorum-9djb.onrender.com/docs

## What Quorum Does

Quorum brings together the core workflows community operators usually scatter across spreadsheets, WhatsApp, Google Forms, payment screenshots, and ad hoc notes:

- workspace creation for community groups
- multi-workspace sign-in for a single user
- role-based admin access
- member registry and invitations
- Gmail-powered invites through Google connection
- dues cycles and payment tracking
- fundraising campaigns and public donation pages
- meetings with transcript ingestion and Claude-generated minutes
- tasks and action items
- events, RSVP, check-in, and attendance analytics
- budgets, budget lines, expenditures, and export
- announcements with targeting and scheduling
- short links and public portal surfaces
- community inbox highlights from synced WhatsApp and Telegram groups
- AI extraction for opportunities, tasks, receipts, announcements, and disbursement signals
- member opportunity matching and recommendation workflows
- financial health scoring with evidence trail and trend history
- in-app notifications for assignments, recommendations, and high-value community signals

## Product Modules

### Auth and Identity
- registration
- login
- refresh token flow
- logout invalidation
- forgot/reset password
- email verification
- multi-workspace membership handling

### Member Operations
- member listing
- invitation flow
- role transfer
- ownership transfer
- seeded demo workspace access

### Finance
- dues cycles
- dues payments
- Squad virtual account collection support
- campaign fundraising
- contribution ledger
- funding streams
- budget planner
- expenditure tracking
- Squad webhook confirmation for dues and contributions
- community receipt capture and receipt-to-record matching
- Squad receipt reference cross-verification inside community inbox flows

### Engagement
- event creation
- RSVP
- attendee check-in
- event analytics
- announcements
- tasks
- meetings and minutes

### Integrations and AI
- Google OAuth
- Gmail invite sending
- Google Meet/Drive integration scaffolding
- Fireflies transcript ingestion path
- Anthropic minutes generation
- WhatsApp group syncing through a local gateway
- Telegram group syncing
- community inbox review queue
- AI opportunity extraction and matching
- task extraction and assignment from community chats
- financial health aggregation from platform and community evidence

## Community Intelligence

Quorum now includes a structured community intelligence layer on top of synced chat channels.

Core capabilities:

- workspace-scoped WhatsApp and Telegram channel connections
- selected-group sync instead of syncing every group by default
- cached `Community Inbox` highlights feed for actionable signals
- review queue for uncertain AI extractions
- bulk approve and reject actions
- audit trail for approvals and task creation
- task extraction, assignee suggestion, and task creation from community messages
- opportunity extraction with:
  - structured summary
  - organization and venue hints
  - deadline and event-date hints
  - trade tags and key points
- receipt and contribution-signal extraction with:
  - OCR/text-aware attachment handling
  - dues/campaign/contribution linking
  - Squad transaction-reference cross-verification when a reference is available

Current receipt verification states shown in the inbox:

- `Matched`
- `Needs review`
- `Unlinked`

Current task workflow:

- high-confidence task signals can create real workspace tasks
- Quorum suggests an assignee from workspace members using:
  - mentioned role
  - mentioned name
  - member role metadata
- assigned members can receive in-app notifications and email notifications when mail is configured

## Opportunity Workflow

Quorum now separates admin and member opportunity experiences.

Admins can:

- review extracted opportunities
- refresh matches
- move recommended members through:
  - `Recommended`
  - `Interested`
  - `Contacted`
  - `Assigned`
- move opportunity records through:
  - `Open`
  - `In progress`
  - `Filled`
  - `Closed`

Members can:

- see a `Recommended for you` section
- browse the wider opportunity board
- respond with interest without seeing the full admin workflow framing

## Financial Health

Financial health is no longer just a static score output.

It now combines:

- confirmed dues payments
- confirmed campaign contributions
- governance and reporting activity
- community receipt signals
- verified inflow evidence from community channels

The financial health view now includes:

- category scores
- trend history
- evidence trail
- partner-facing summary/profile

## Live Demo Flow

There are two main ways to explore the product:

1. Standard sign-in with a real workspace account
2. One-click demo entry from `/login` using `Explore demo workspace`

The demo workspace is seeded as:

- **Engineering Faculty Council**
- 7 executive members
- live-looking dues, campaigns, budgets, meetings, tasks, announcements, links, and events

That seeded workspace exists specifically for demos, walkthroughs, and product evaluation without needing credentials.

## Where to Connect Google

Once a user is inside a workspace, Google is connected from:

- `/{workspaceSlug}/settings/integrations`

That is where a workspace admin can:

- connect Google Workspace
- reconnect to add new scopes like Gmail send
- disconnect Google

Google connection powers:

- Gmail-sent invitations
- meeting link creation
- transcript and meeting integration flows

## Frontend Structure

The frontend is a Next.js app in `frontend/`.

Important routes:

- `/` - landing page
- `/login` - standard sign-in + demo workspace entry
- `/register` - two-step workspace creation
- `/forgot-password`
- `/verify-email`
- `/{workspaceSlug}/dashboard`
- `/{workspaceSlug}/members`
- `/{workspaceSlug}/events`
- `/{workspaceSlug}/meetings`
- `/{workspaceSlug}/campaigns`
- `/{workspaceSlug}/dues`
- `/{workspaceSlug}/community-inbox`
- `/{workspaceSlug}/opportunities`
- `/{workspaceSlug}/financial-health`
- `/{workspaceSlug}/budgets`
- `/{workspaceSlug}/tasks`
- `/{workspaceSlug}/announcements`
- `/{workspaceSlug}/settings/roles`
- `/{workspaceSlug}/settings/workspace`
- `/{workspaceSlug}/settings/integrations`
- `/portal/{workspaceSlug}`
- `/donate/{campaignSlug}`
- `/e/{eventSlug}`

The app also includes:

- persisted light/dark mode
- workspace shell prefetching for faster navigation
- route loading skeletons
- CRM-style sidebar and topbar structure

## Backend Structure

The backend is a FastAPI app in `app/`.

Main router groups:

- `auth`
- `workspaces`
- `members`
- `roles`
- `invitations`
- `integrations`
- `dues`
- `events`
- `campaigns`
- `community_channels`
- `links`
- `announcements`
- `tasks`
- `meetings`
- `budgets`
- `financial_health`
- `notifications`
- `public`
- `webhooks`

The OpenAPI docs are available locally at:

- `http://localhost:8000/docs`

Health endpoint:

- `http://localhost:8000/api/v1/health`

And in the deployed environment at:

- https://quorum-9djb.onrender.com/docs

## Database Model

Quorum uses MongoDB with segmented databases while keeping integer IDs for compatibility with the frontend.

Logical segmentation:

- `communities`
  - `workspaces`
  - `members`
- `identity`
  - `users`
  - `roles`
  - `workspace_members`
  - `integrations`
  - `auth_sessions`
  - `revoked_tokens`
  - `email_verification_tokens`
  - `password_reset_tokens`
  - `invitations`
  - `invite_links`
- `finance`
  - `dues_cycles`
  - `dues_payments`
  - `campaigns`
  - `funding_streams`
  - `contributions`
  - `virtual_accounts`
  - `budgets`
  - `budget_lines`
  - `expenditures`
  - `community_financial_records`
  - `financial_health_snapshots`
- `engagement`
  - `events`
  - `event_attendees`
  - `meetings`
  - `meeting_minutes`
  - `action_items`
  - `announcements`
  - `short_links`
  - `link_clicks`
  - `tasks`
  - `notifications`
  - `channel_group_links`
  - `channel_messages`
  - `message_artifacts`
  - `opportunities`
- `platform`
  - `counters`

## Local Development

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### WhatsApp Gateway

```bash
cd whatsapp-gateway
npm install
npm start
```

Quorum uses the local Baileys gateway only for WhatsApp session handling. Prepare the WhatsApp channel from `Settings > Integrations`, copy the generated channel ID and gateway secret into `whatsapp-gateway/.env`, then connect the session through the gateway's `/internal/session/connect` endpoint. Full setup notes live in [whatsapp-gateway/README.md](/Users/sam/Documents/quorum-commons/whatsapp-gateway/README.md).

Current WhatsApp behavior:

- live new-message sync
- selected-group syncing only
- session reset/reconnect support
- degraded or reconnect-required state when the gateway session is unhealthy
- group discovery on demand

## Environment Variables

Backend examples are in `.env.example`.

The core ones are:

```text
MONGODB_CONNECTION_STRING=
ANTHROPIC_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
SQUAD_SECRET_KEY=
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
WHATSAPP_GATEWAY_TOKEN=
WHATSAPP_GATEWAY_INTERNAL_URL=
```

Frontend examples are in `frontend/.env.example`.

## Manual QA

A current end-to-end manual checklist for admin/member flows lives at:

- [docs/member-workflow-test-pass.md](/Users/sam/Documents/quorum-commons/docs/member-workflow-test-pass.md)

## Recommended Deployment Shape

The current repo is easiest to deploy with:

- `frontend` on Vercel
- `backend` on Azure Web App for Containers or Azure App Service
- `whatsapp-gateway` on a separate Azure Web App for Containers
- `MongoDB` on MongoDB Atlas

Why split the gateway:

- the WhatsApp gateway has its own runtime behavior and local auth/session storage
- it should not be bundled into the main FastAPI backend process
- isolating it makes reconnects and restarts safer

Recommended production topology:

1. Vercel hosts the Next.js frontend.
2. Azure Web App hosts the FastAPI backend.
3. Another Azure Web App hosts the WhatsApp gateway.
4. MongoDB Atlas stores the application data.
5. Public HTTPS routes are configured so:
   - frontend calls the backend API
   - backend calls the internal WhatsApp gateway URL
   - Squad webhooks hit the backend
   - WhatsApp gateway pushes inbound events back to the backend

Deployment notes:

- Persist WhatsApp auth/session storage on the gateway app if possible.
- Set `WHATSAPP_GATEWAY_INTERNAL_URL` on the backend to the gateway base URL.
- Set `PUBLIC_APP_URL` / `NEXT_PUBLIC_API_BASE_URL` correctly for frontend and backend coordination.
- Configure Squad webhook URL to `/api/v1/webhooks/squad`.
- Use the backend health route `/api/v1/health` for uptime checks.

The key one is:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

## Resetting the Database

To clear the current MongoDB data and reseed only the demo workspace:

```bash
python scripts/reset_database.py
```

That will:

- remove existing workspaces and accounts
- clear all current operational data
- recreate the demo workspace entry used by `Explore demo workspace`

This is destructive and intended for fresh-start local/demo resets.

## How Login Works

Login is email-first. After successful authentication:

- Quorum loads the workspaces associated with that user
- if there is only one workspace, it opens directly
- if there are multiple, it presents the chooser
- the last real workspace used is remembered and prioritized

There is no requirement for an explicit workspace field during normal login.

## Why Login Can Feel Slow

Historically, login was slow because it did too much work across the entire dataset before completing.

That path has been tightened so it now:

- authenticates the user
- loads only the memberships relevant to that user
- only performs legacy membership sync for workspaces actually linked to that email when needed

If login is still slow in a deployed environment, the next likely causes are:

- cold backend start on the hosting platform
- slow MongoDB network round-trips
- the backend URL configured in the frontend pointing to a sleeping or remote service

## Google and Invitations

Invitation sending uses the workspace’s Google connection first.

Flow:

1. Workspace admin connects Google in `Settings > Integrations`
2. Quorum requests the Gmail send scope
3. Member invites are sent from the connected Gmail account
4. If Google is unavailable, Quorum falls back to SMTP/transactional mail

## AI Flow

Meetings support a transcript-to-minutes workflow:

1. Create or open a meeting
2. Upload transcript text or sync from an integration path
3. Claude generates:
   - summary
   - structured minutes
   - decisions
   - action items
4. Action items can become linked tasks

## Demo and QA Docs

For a guided walkthrough, see:

- [7-minute demo script](docs/06-seven-minute-demo-script.md)
- [pre-demo QA checklist](docs/07-pre-demo-qa-checklist.md)

## Repo Layout

```text
app/                FastAPI backend
frontend/           Next.js frontend
docs/               product and implementation docs
scripts/            utility scripts like DB reset/migrations
requirements.txt    backend dependencies
.env.example        backend env template
```

## Current Testing Approach

Useful verification commands:

```bash
python -m compileall app
cd frontend && npm run build
```

## Summary

Quorum is meant to be both:

- a real operational workspace for community leadership teams
- a strong demoable system that clearly shows structure, governance, finance, communication, and AI assistance in one place

That is why the repo includes both production-style workflows and a dedicated demo workspace path.
