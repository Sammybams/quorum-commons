# Quorum Monorepo Scaffold Plan

> Update (implemented): The live repository currently uses a simplified structure with backend at repo root (`app/`) and frontend in `frontend/` for easier deployment on Render and Vercel.

## 1. Recommendation Summary

Use a **monorepo** with one frontend app, one backend API app, and shared packages for UI, generated API client, and lint/format/tooling config.

This is the best fit for Quorum at MVP stage because:

1. Product modules are tightly coupled (dues, campaigns, budget, links, events).
2. Public OG pages and admin workflows need coordinated full-stack changes.
3. One repository reduces integration friction and speeds demo-to-production iteration.

## 2. Repository Layout

```text
quorum/
  app/                    # FastAPI package (Render)
  requirements.txt        # backend dependencies
  .env.example            # backend env template
  frontend/               # Next.js app (Vercel)
  docs/
    01-monorepo-scaffold-plan.md
    02-mvp-api-endpoints-and-db-schema.md
    03-frontend-route-map-and-build-checklist.md
```

## 3. Application Boundaries

## `frontend` (Next.js)

Responsibilities:

1. Authenticated exco/member dashboard and workflows.
2. Public pages with SSR OG metadata (events, meetings, campaigns/portal pages).
3. Link redirect entry and analytics trigger handshake with API.

Non-responsibilities:

1. Business-critical payment verification state transitions.
2. Cross-tenant authorization logic.

## `app` (FastAPI)

Responsibilities:

1. Tenant-scoped business logic and authorization.
2. CRUD + workflow endpoints for dues/events/meetings/campaigns/links.
3. AI receipt extraction orchestration and review queue statuses.
4. Audit trails and export endpoints.

Non-responsibilities:

1. Rendering OG pages.
2. Frontend-only UI concerns.

## 4. Shared Packages

## `packages/ui`

1. Reusable primitives: cards, tables, badges, forms, shells, charts wrapper.
2. Theme tokens (brand-safe + accessibility constraints).
3. Mobile-first component variants for public donation/event pages.

## `packages/api-client`

1. OpenAPI-generated TypeScript client.
2. Centralized request wrapper (auth headers, tenant/workspace headers, retries).
3. Typed DTOs used in server actions and client hooks.

## `packages/config`

1. Shared formatting/linting/type-check settings.
2. Conventional commit and PR template rules.
3. Shared test runner configs.

## 5. Environment Strategy

Use one `.env` per app + shared examples:

1. `frontend/.env.local`
2. `.env`
3. `.env.example`

Key variables:

1. `MONGODB_CONNECTION_STRING`
2. `REDIS_URL`
3. `JWT_SECRET`
4. `OBJECT_STORAGE_BUCKET`
5. `VISION_MODEL_API_KEY`
6. `APP_BASE_DOMAIN` (for subdomain and short-link behavior)

## 6. CI/CD Baseline

Pipeline stages:

1. Lint and type-check (`web`, `api`, shared packages).
2. Unit tests.
3. Contract checks (OpenAPI drift and api-client generation freshness).
4. Integration tests against ephemeral Postgres + Redis.
5. Build artifacts.

Release strategy:

1. Single release tag for MVP (`v0.x`) across apps.
2. Later split into independent deployment tracks only if throughput needs it.

## 7. Progressive Migration Path (If You Later Need Multi-Repo)

Trigger to split:

1. Separate teams and release cadence divergence.
2. CI runtime or code ownership bottlenecks.

Order of extraction:

1. Extract `frontend` first (preserve API contracts).
2. Keep `packages/api-client` generated from API artifact.
3. Retain architecture docs in a dedicated docs repo.

## 8. Immediate Next Setup Tasks

1. Bootstrap `frontend` with Next.js and route groups.
2. Bootstrap `app` with FastAPI project layout and Alembic.
3. Create initial Postgres schema migration for core entities.
4. Add OpenAPI generation and TS client generation script.
5. Add local `docker-compose` for Postgres + Redis.
