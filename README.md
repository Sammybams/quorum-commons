# quorum-commons

`quorum-commons` is the monorepo home for Quorum, a student-body operating system for campus leadership teams.

This repo currently contains:

- `apps/api`: FastAPI backend imported from the existing Quorum implementation
- `apps/web`: Next.js frontend imported from the existing Quorum implementation
- `docs`: product and implementation planning documents carried over from the source project

## Product Scope

Quorum brings together the workflows student leaders often split across spreadsheets, WhatsApp, Google Forms, payment screenshots, and scattered notes:

- workspace creation and multi-workspace membership
- role-based admin access
- member registry and invitations
- dues, payments, and campaign fundraising
- meetings, transcripts, and AI-assisted minutes
- events, RSVP, attendance, and announcements
- budgets, reports, links, and public portal surfaces

## Repository Layout

```text
quorum-commons/
  apps/
    api/
    web/
  docs/
```

## Local Development

### API

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Web

```bash
cd apps/web
npm install
npm run dev
```
