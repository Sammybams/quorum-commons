# Quorum

Quorum is a multi-tenant student-body operating system built for campus leadership teams. It gives a student union, faculty body, department association, club, or ambassador program one structured workspace for members, meetings, dues, events, budgets, campaigns, links, and announcements.

The product is designed to feel less like a generic admin panel and more like a real operations system for executive councils.

## Live Environments

- Frontend: https://quorum-taupe.vercel.app/
- Backend API docs: https://quorum-9djb.onrender.com/docs

## What Quorum Does

Quorum brings together the core workflows student leaders usually scatter across spreadsheets, WhatsApp, Google Forms, payment screenshots, and ad hoc notes:

- workspace creation for student bodies
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
- Paystack initialization support
- campaign fundraising
- contribution ledger
- funding streams
- budget planner
- expenditure tracking

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
- `links`
- `announcements`
- `tasks`
- `meetings`
- `budgets`
- `public`
- `webhooks`

The OpenAPI docs are available locally at:

- `http://localhost:8000/docs`

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
  - `budgets`
  - `budget_lines`
  - `expenditures`
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

## Environment Variables

Backend examples are in `.env.example`.

The core ones are:

```text
MONGODB_CONNECTION_STRING=
ANTHROPIC_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=
PAYSTACK_SECRET_KEY=
FRONTEND_ORIGIN=
APP_URL=
PUBLIC_APP_URL=
FRONTEND_URL=
```

Frontend examples are in `frontend/.env.example`.

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

- a real operational workspace for student leadership teams
- a strong demoable system that clearly shows structure, governance, finance, communication, and AI assistance in one place

That is why the repo includes both production-style workflows and a dedicated demo workspace path.
