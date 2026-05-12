import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import store
from .routers import (
    announcements,
    auth,
    budgets,
    campaigns,
    dues,
    events,
    health,
    integrations,
    invitations,
    links,
    meetings,
    members,
    public,
    reports,
    roles,
    tasks,
    webhooks,
    workspaces,
)

app = FastAPI(title=os.getenv("APP_NAME", "Quorum API"))

frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")
allowed_origins = [frontend_origin] if frontend_origin != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    store.ensure_indexes()


api_prefix = os.getenv("API_PREFIX", "/api/v1")

app.include_router(health.router, prefix=api_prefix)
app.include_router(workspaces.router, prefix=api_prefix)
app.include_router(auth.router, prefix=api_prefix)
app.include_router(members.router, prefix=api_prefix)
app.include_router(roles.router, prefix=api_prefix)
app.include_router(invitations.router, prefix=api_prefix)
app.include_router(invitations.public_router, prefix=api_prefix)
app.include_router(integrations.router, prefix=api_prefix)
app.include_router(integrations.callback_router, prefix=api_prefix)
app.include_router(dues.router, prefix=api_prefix)
app.include_router(dues.payments_router, prefix=api_prefix)
app.include_router(events.router, prefix=api_prefix)
app.include_router(campaigns.router, prefix=api_prefix)
app.include_router(links.router, prefix=api_prefix)
app.include_router(announcements.router, prefix=api_prefix)
app.include_router(tasks.router, prefix=api_prefix)
app.include_router(meetings.router, prefix=api_prefix)
app.include_router(budgets.router, prefix=api_prefix)
app.include_router(reports.router, prefix=api_prefix)
app.include_router(public.router, prefix=api_prefix)
app.include_router(webhooks.router, prefix=api_prefix)


@app.get("/")
def root():
    return {
        "name": os.getenv("APP_NAME", "Quorum API"),
        "project": "Quorum",
        "description": "Multi-tenant platform for student-body operations.",
        "api_prefix": api_prefix,
        "docs": app.docs_url,
        "openapi": app.openapi_url,
    }
