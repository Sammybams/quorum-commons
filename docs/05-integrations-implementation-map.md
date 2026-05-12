# Quorum Integrations Implementation Map

This document maps `Quorum_Integrations_Spec.docx` to the current Quorum codebase. It is intended to answer three practical questions:

1. What the integration spec proposes.
2. What is already implemented in the repo right now.
3. What still needs to be added before the integration layer fully matches the spec.

It also doubles as the checklist for end-to-end testing.

## 1. Integration Systems In Scope

The integration spec describes three connected systems:

1. Google OAuth for workspace-level connection and Google Meet / Drive access.
2. Fireflies transcript ingestion.
3. Gmail-powered invitation emails sent from the connected admin account.

These are all intended to attach to the workspace, not to a transient browser session for a single user.

## 2. Current Architecture In The Repo

The current implementation stores integration state in the Mongo `integrations` collection, keyed by:

1. `workspace_id`
2. `provider`

This is created and indexed in [app/database.py](/Users/sam/Documents/quorum/app/database.py:54).

Right now the live providers exposed by the app are:

1. `google_workspace`
2. `fireflies`

The backend entry points are:

1. [app/routers/integrations.py](/Users/sam/Documents/quorum/app/routers/integrations.py:24)
2. [app/services/google.py](/Users/sam/Documents/quorum/app/services/google.py:17)
3. [app/services/fireflies.py](/Users/sam/Documents/quorum/app/services/fireflies.py:1)
4. [app/routers/meetings.py](/Users/sam/Documents/quorum/app/routers/meetings.py:279)

The frontend admin surfaces are:

1. [frontend/app/(app)/[workspaceSlug]/settings/integrations/page.tsx](/Users/sam/Documents/quorum/frontend/app/(app)/[workspaceSlug]/settings/integrations/page.tsx:21)
2. [frontend/app/(app)/[workspaceSlug]/meetings/[meetingId]/page.tsx](/Users/sam/Documents/quorum/frontend/app/(app)/[workspaceSlug]/meetings/[meetingId]/page.tsx:31)

## 3. Google OAuth Mapping

### Spec Intent

The spec proposes:

1. One Google OAuth connection per workspace.
2. The OAuth `state` parameter carrying the workspace identity through the flow.
3. Tokens stored against the workspace integration record.
4. Shared scopes powering both transcripts and Gmail invitations.
5. Forced `prompt=consent` to reliably obtain a refresh token.

### Current Implementation

This is already mostly true in the repo:

1. OAuth is initiated from `/workspaces/{workspace_id}/integrations/google/oauth/start`.
2. The signed `state` token carries:
   - `workspace_id`
   - `workspace_slug`
   - `user_id`
3. Callback handling is in `/api/v1/integrations/google/callback`.
4. The integration is stored against the workspace in [app/routers/integrations.py](/Users/sam/Documents/quorum/app/routers/integrations.py:120).
5. The frontend settings page displays the connected account and scopes in [settings/integrations/page.tsx](/Users/sam/Documents/quorum/frontend/app/(app)/[workspaceSlug]/settings/integrations/page.tsx:96).

### Current OAuth Scopes

The app currently requests:

1. `openid`
2. `email`
3. `profile`
4. `https://www.googleapis.com/auth/drive.readonly`
5. `https://www.googleapis.com/auth/documents.readonly`
6. `https://www.googleapis.com/auth/meetings.space.created`
7. `https://www.googleapis.com/auth/meetings.space.readonly`

These are defined in [app/services/google.py](/Users/sam/Documents/quorum/app/services/google.py:17).

### Important Difference From The Spec

The spec assumes Gmail sending is part of the same OAuth connection. The current code does **not** yet request `gmail.send`, and it does **not** yet send invitations through Gmail. Invitation email is still SMTP-based through [app/email.py](/Users/sam/Documents/quorum/app/email.py:15).

That means:

1. Google connection currently powers Meet / transcript-related features.
2. It does not yet power member invitation sending.

## 4. How Workspace Association Works

The integration spec asks how Quorum knows the Google connection belongs to a given student body.

That mapping is now:

1. The admin starts the connection from a workspace-specific settings screen.
2. The backend creates a signed `state` token containing the workspace ID and slug.
3. Google redirects to the callback URL with that `state`.
4. The callback decodes `state` and upserts the integration record for that workspace.

This lives in [app/routers/integrations.py](/Users/sam/Documents/quorum/app/routers/integrations.py:72).

So the ownership model is workspace-scoped, which matches the spec’s core idea.

## 5. Google Meet / Transcript Mapping

### Spec Intent

The spec proposes a Drive-watch system:

1. User connects Google.
2. User selects a Drive folder.
3. Quorum registers a Drive push notification channel.
4. Google calls a webhook when a transcript file appears.
5. Quorum downloads the transcript and sends it into Claude processing.

### Current Implementation

The app currently uses a simpler and more direct Meet-centric approach:

1. Admin connects Google Workspace.
2. Admin creates a Google Meet link from the meeting detail page.
3. Quorum stores the created Meet space name on the meeting.
4. Admin clicks `Sync Google transcript`.
5. Quorum:
   - finds the latest conference record for that Meet space
   - lists transcripts for that conference record
   - pulls the linked Google Doc transcript
   - stores the transcript on the meeting
   - runs the Claude minutes pipeline

This is implemented in:

1. `attach_google_meet_link()` in [app/routers/meetings.py](/Users/sam/Documents/quorum/app/routers/meetings.py:386)
2. `sync_google_transcript()` in [app/routers/meetings.py](/Users/sam/Documents/quorum/app/routers/meetings.py:412)
3. the Google helpers in [app/services/google.py](/Users/sam/Documents/quorum/app/services/google.py:66)

### Why This Is Different

This implementation intentionally skips the Drive folder watch layer for now. It is simpler for the current product stage because:

1. it avoids Drive push channel management
2. it avoids renewal cron jobs
3. it keeps transcript sync tied to a known Quorum meeting
4. it works well for admin-driven review flows

### Gap Versus Spec

Still missing relative to the spec:

1. Drive folder picker UI
2. Drive watch registration
3. Google Drive webhook receiver
4. automatic transcript pull after meeting end
5. channel renewal job for expiring watches

## 6. Claude Processing Mapping

### Spec Intent

The spec proposes a shared transcript processor:

1. any transcript source flows into a single processor
2. Claude returns structured minutes and action items
3. tasks are created and linked to the meeting
4. review / publish happens afterward

### Current Implementation

This is now implemented in a practical form:

1. Claude call and JSON parsing live in [app/services/anthropic.py](/Users/sam/Documents/quorum/app/services/anthropic.py:47)
2. Transcript-to-minutes generation is in `_generate_minutes_for_meeting()` in [app/routers/meetings.py](/Users/sam/Documents/quorum/app/routers/meetings.py:160)
3. Generated action items also create linked tasks through `_create_action_item_and_task()` in [app/routers/meetings.py](/Users/sam/Documents/quorum/app/routers/meetings.py:103)
4. The meeting detail screen exposes transcript save, regenerate, and publish controls in [frontend/app/(app)/[workspaceSlug]/meetings/[meetingId]/page.tsx](/Users/sam/Documents/quorum/frontend/app/(app)/[workspaceSlug]/meetings/[meetingId]/page.tsx:294)

### Current Behavior

The pipeline supports:

1. manual transcript paste
2. Google transcript sync
3. Fireflies transcript import

All three feed the same Claude generation path.

## 7. Fireflies Mapping

### Spec Intent

The spec proposes:

1. user pastes Fireflies API key into Quorum
2. Quorum validates it
3. Quorum registers a webhook with Fireflies
4. Fireflies pushes transcript-ready events to Quorum automatically
5. Quorum fetches the transcript and processes it

### Current Implementation

The current app has a lighter first version:

1. backend Fireflies transcript fetcher exists in [app/services/fireflies.py](/Users/sam/Documents/quorum/app/services/fireflies.py:31)
2. the integrations screen surfaces Fireflies availability in [settings/integrations/page.tsx](/Users/sam/Documents/quorum/frontend/app/(app)/[workspaceSlug]/settings/integrations/page.tsx:157)
3. the meeting detail page supports importing a transcript by Fireflies transcript ID in [frontend/app/(app)/[workspaceSlug]/meetings/[meetingId]/page.tsx](/Users/sam/Documents/quorum/frontend/app/(app)/[workspaceSlug]/meetings/[meetingId]/page.tsx:311)
4. the meeting router consumes that transcript and sends it into the same Claude pipeline in [app/routers/meetings.py](/Users/sam/Documents/quorum/app/routers/meetings.py:468)

### Gap Versus Spec

Still missing:

1. storing a workspace-specific Fireflies API key in the database
2. validating Fireflies credentials from the UI
3. registering a Fireflies webhook
4. webhook receiver for transcript-ready events
5. automatic transcript import from webhook events

So Fireflies is currently a **manual fallback import**, not a fully connected webhook integration yet.

## 8. Gmail Invitation Mapping

### Spec Intent

The spec wants:

1. invitation emails sent from the admin’s connected Gmail account
2. shared Google OAuth connection used for both transcript features and Gmail sending
3. fallback to a Quorum transactional sender if Google is not connected

### Current Implementation

This is now implemented with fallback behavior:

1. the Google OAuth connection requests `https://www.googleapis.com/auth/gmail.send`
2. invitation creation checks the workspace Google integration first
3. if Gmail sending is available, Quorum sends the invite through the connected Gmail account
4. if Google is not connected, the Gmail scope is missing, or the Gmail send fails, Quorum falls back to SMTP / transactional email

The live pieces are:

1. Gmail scope + sender helpers in [app/services/google.py](/Users/sam/Documents/quorum/app/services/google.py:20)
2. invitation MIME builder + SMTP fallback in [app/email.py](/Users/sam/Documents/quorum/app/email.py:33)
3. workspace invitation branching in [app/routers/invitations.py](/Users/sam/Documents/quorum/app/routers/invitations.py:17)
4. integration UI messaging in [frontend/app/(app)/[workspaceSlug]/settings/integrations/page.tsx](/Users/sam/Documents/quorum/frontend/app/(app)/[workspaceSlug]/settings/integrations/page.tsx:86)
5. invitation delivery status labels in [frontend/app/(app)/[workspaceSlug]/members/members-client.tsx](/Users/sam/Documents/quorum/frontend/app/(app)/[workspaceSlug]/members/members-client.tsx:362)

### Gap Versus Spec

Still missing:

1. browser-tested live callback + Gmail send verification against a connected Google account
2. alias / send-as management if a workspace wants a different sender than the connected account
3. encryption-at-rest for the stored Google tokens

## 9. Security Mapping

### Spec Intent

The spec strongly recommends encryption at rest for:

1. Google access token
2. Google refresh token
3. Fireflies API key

It specifically suggests Fernet symmetric encryption.

### Current Implementation

This is **not implemented yet**.

At the moment, the Google integration record stores tokens directly in the `integrations` collection. There is not yet a Fernet encryption layer or equivalent secret-wrapping abstraction around those fields.

### Gap Versus Spec

Still missing:

1. encryption key env var
2. encryption / decryption helpers
3. encrypted write path for Google tokens
4. encrypted write path for Fireflies API key
5. migration of existing stored secrets to encrypted form

This is the most important integration hardening task still outstanding.

## 10. Current Feature Mapping Table

| Feature | In Spec | Current Status | Notes |
|---|---|---|---|
| Workspace-scoped Google OAuth | Yes | Implemented | Uses signed `state`, workspace-scoped integration record |
| Google account connect UI | Yes | Implemented | Settings page is live |
| Google Meet link creation | Yes | Implemented | Created from Quorum meeting detail |
| Manual Google transcript sync | Partial | Implemented | Uses Meet conference records + Docs transcript |
| Automatic Google transcript ingestion | Yes | Not implemented | No Drive watch / webhook / cron renewal yet |
| Claude meeting minutes generation | Yes | Implemented | Live and tested |
| Claude action item extraction to tasks | Yes | Implemented | Generated tasks are linked to meetings |
| Fireflies transcript import | Partial | Implemented | Manual by transcript ID |
| Fireflies webhook automation | Yes | Not implemented | No connect / validate / webhook registration yet |
| Gmail invitation sending | Yes | Implemented | Gmail first, SMTP fallback |
| Token encryption at rest | Yes | Not implemented | Needs hardening pass |

## 11. Recommended Build Order From Here

The cleanest next sequence is:

1. Add encryption-at-rest for integration secrets.
2. Add real Fireflies workspace connection and webhook registration.
3. Add Google automatic transcript ingestion via Drive watch or Workspace Events.
4. Expand Gmail sending with browser-tested alias / sender management if needed.

That order hardens the current implementation before expanding the automation surface.

## 12. End-to-End Test Readiness

What is testable now:

1. Google OAuth initiation
2. Google account connection callback
3. Google Meet link creation from a meeting
4. manual transcript paste -> Claude minutes -> generated action items
5. Fireflies transcript import by transcript ID, if `FIREFLIES_API_KEY` is set
6. budgets, targeted announcements, ownership transfer, event check-in, and the wider admin shell

What is not yet testable as an implemented product path:

1. automatic Drive-watch transcript pulling
2. Fireflies webhook-driven transcript delivery
3. encrypted secret storage verification

## 13. Practical Notes For The E2E Pass

Before the end-to-end test, the environment should include:

1. `ANTHROPIC_API_KEY`
2. `GOOGLE_CLIENT_ID`
3. `GOOGLE_CLIENT_SECRET`
4. `BACKEND_PUBLIC_URL` or `GOOGLE_OAUTH_REDIRECT_URI`
5. optionally `FIREFLIES_API_KEY`

For local development, the current Google callback fallback resolves to:

`http://localhost:8000/api/v1/integrations/google/callback`

That fallback is defined in [app/services/google.py](/Users/sam/Documents/quorum/app/services/google.py:28).

## 14. Bottom Line

The integration spec and the current repo are aligned in direction, but not yet identical in implementation approach.

The repo already has:

1. workspace-scoped Google OAuth
2. Claude-backed meeting processing
3. Google Meet transcript sync
4. Fireflies fallback import

The repo does not yet have:

1. automatic webhook-driven transcript ingestion
2. Gmail-powered invitation sending
3. encrypted integration secret storage

So the right framing is:

Quorum has a working integrations foundation and a working AI meeting pipeline, but the automation and security-hardening layers described in the full integration spec are still the next build phase.
