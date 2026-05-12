from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from .. import schemas
from ..database import DESC, MongoStore, get_db
from ..rbac import require_workspace_permission
from ..services.telegram import TelegramServiceError, telegram_get_me, telegram_set_webhook


router = APIRouter(prefix="/workspaces/{workspace_id}/community-channels", tags=["community-channels"])
inbound_router = APIRouter(prefix="/community-channels", tags=["community-channels"])


def _channel_out(channel) -> schemas.CommunityChannelOut:
    metadata = {
        "webhook_url": channel.get("webhook_url"),
        "bot_username": channel.get("bot_username"),
        "display_name": channel.get("display_name"),
        "gateway_account_id": channel.get("gateway_account_id"),
        "selected_group_count": channel.get("selected_group_count", 0),
        "discovered_group_count": channel.get("discovered_group_count", 0),
        "last_error": channel.get("last_error"),
        "webhook_secret": channel.get("webhook_secret"),
    }
    return schemas.CommunityChannelOut(
        id=channel.id,
        workspace_id=channel.workspace_id,
        provider=channel.provider,
        label=channel.label,
        status=channel.status,
        connected_at=channel.get("connected_at"),
        metadata={key: value for key, value in metadata.items() if value not in (None, "")},
        created_at=channel.created_at,
    )


def _group_out(link) -> schemas.ChannelGroupLinkOut:
    return schemas.ChannelGroupLinkOut(
        id=link.id,
        workspace_id=link.workspace_id,
        channel_id=link.channel_id,
        provider=link.provider,
        external_group_id=link.external_group_id,
        group_name=link.group_name,
        sync_enabled=bool(link.get("sync_enabled")),
        last_seen_at=link.get("last_seen_at"),
        last_message_at=link.get("last_message_at"),
        message_count=int(link.get("message_count") or 0),
        created_at=link.created_at,
    )


def _discover_or_update_group(
    db: MongoStore,
    *,
    workspace_id: int,
    channel_id: int,
    provider: str,
    external_group_id: str,
    group_name: str,
    seen_at: datetime,
):
    group = db.find_one(
        "channel_group_links",
        {"workspace_id": workspace_id, "channel_id": channel_id, "external_group_id": external_group_id},
    )
    if group:
        group["group_name"] = group_name or group.get("group_name") or external_group_id
        group["last_seen_at"] = seen_at
        db.save("channel_group_links", group)
        return group

    return db.insert(
        "channel_group_links",
        {
            "workspace_id": workspace_id,
            "channel_id": channel_id,
            "provider": provider,
            "external_group_id": external_group_id,
            "group_name": group_name or external_group_id,
            "sync_enabled": False,
            "last_seen_at": seen_at,
            "last_message_at": None,
            "message_count": 0,
        },
    )


def _persist_channel_message(
    db: MongoStore,
    *,
    workspace_id: int,
    channel_id: int,
    group_link,
    provider: str,
    external_message_id: str | None,
    sender_name: str | None,
    sender_handle: str | None,
    message_type: str,
    text: str,
    raw_payload: dict,
    received_at: datetime,
):
    message_key = f"{group_link.external_group_id}:{external_message_id}" if external_message_id else None
    if message_key and db.find_one("channel_messages", {"workspace_id": workspace_id, "external_message_id": message_key}):
        return

    db.insert(
        "channel_messages",
        {
            "workspace_id": workspace_id,
            "channel_id": channel_id,
            "group_link_id": group_link.id,
            "provider": provider,
            "external_group_id": group_link.external_group_id,
            "external_message_id": message_key,
            "sender_name": sender_name,
            "sender_handle": sender_handle,
            "message_type": message_type,
            "text": text,
            "raw_payload": raw_payload,
            "received_at": received_at,
        },
    )
    group_link["last_message_at"] = received_at
    group_link["last_seen_at"] = received_at
    group_link["message_count"] = int(group_link.get("message_count") or 0) + 1
    db.save("channel_group_links", group_link)


def _refresh_channel_counts(db: MongoStore, channel):
    discovered = db.count("channel_group_links", {"workspace_id": channel.workspace_id, "channel_id": channel.id})
    selected = db.count(
        "channel_group_links",
        {"workspace_id": channel.workspace_id, "channel_id": channel.id, "sync_enabled": True},
    )
    channel["discovered_group_count"] = discovered
    channel["selected_group_count"] = selected
    channel["updated_at"] = datetime.utcnow()
    db.save("community_channels", channel)


@router.get("", response_model=list[schemas.CommunityChannelOut])
def list_community_channels(
    workspace_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channels = db.find_many("community_channels", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    for channel in channels:
        _refresh_channel_counts(db, channel)
    refreshed = db.find_many("community_channels", {"workspace_id": workspace_id}, sort=[("created_at", DESC)])
    return [_channel_out(channel) for channel in refreshed]


@router.post("/telegram", response_model=schemas.CommunityChannelOut, status_code=201)
def connect_telegram_channel(
    workspace_id: int,
    payload: schemas.TelegramChannelConnectRequest,
    request: Request,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    existing = db.find_one(
        "community_channels",
        {"workspace_id": workspace_id, "provider": "telegram", "label": payload.label.strip()},
    )
    channel_id = existing.id if existing else db.next_id("community_channels")
    secret = existing.get("webhook_secret") if existing else secrets.token_urlsafe(24)
    webhook_url = str(request.url_for("telegram_channel_webhook", channel_id=channel_id))
    bot_username = None
    display_name = None
    status = "configured"
    last_error = None
    try:
        profile = telegram_get_me(payload.bot_token).get("result") or {}
        bot_username = profile.get("username")
        display_name = profile.get("first_name")
        telegram_set_webhook(
            payload.bot_token,
            webhook_url=webhook_url,
            secret_token=secret,
            allowed_updates=["message"],
        )
        status = "connected"
    except TelegramServiceError as exc:
        last_error = str(exc)

    record = {
        "id": channel_id,
        "workspace_id": workspace_id,
        "provider": "telegram",
        "label": payload.label.strip(),
        "status": status,
        "bot_token": payload.bot_token,
        "bot_username": bot_username,
        "display_name": display_name,
        "webhook_url": webhook_url,
        "webhook_secret": secret,
        "connected_at": existing.get("connected_at") if existing else datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "selected_group_count": existing.get("selected_group_count", 0) if existing else 0,
        "discovered_group_count": existing.get("discovered_group_count", 0) if existing else 0,
        "last_error": last_error,
    }
    if existing:
        existing.update(record)
        channel = db.save("community_channels", existing)
    else:
        channel = db.insert("community_channels", record)
    return _channel_out(channel)


@router.post("/whatsapp", response_model=schemas.CommunityChannelOut, status_code=201)
def connect_whatsapp_channel(
    workspace_id: int,
    payload: schemas.WhatsAppChannelConnectRequest,
    request: Request,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    if not db.find_by_id("workspaces", workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    existing = db.find_one(
        "community_channels",
        {"workspace_id": workspace_id, "provider": "whatsapp", "label": payload.label.strip()},
    )
    channel_id = existing.id if existing else db.next_id("community_channels")
    secret = existing.get("webhook_secret") if existing else secrets.token_urlsafe(24)
    inbound_url = str(request.url_for("whatsapp_channel_inbound", channel_id=channel_id))
    record = {
        "id": channel_id,
        "workspace_id": workspace_id,
        "provider": "whatsapp",
        "label": payload.label.strip(),
        "status": "pending_gateway",
        "gateway_account_id": payload.gateway_account_id,
        "webhook_url": inbound_url,
        "webhook_secret": secret,
        "connected_at": existing.get("connected_at") if existing else datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "selected_group_count": existing.get("selected_group_count", 0) if existing else 0,
        "discovered_group_count": existing.get("discovered_group_count", 0) if existing else 0,
        "last_error": None,
    }
    if existing:
        existing.update(record)
        channel = db.save("community_channels", existing)
    else:
        channel = db.insert("community_channels", record)
    return _channel_out(channel)


@router.delete("/{channel_id}", response_model=schemas.AuthStatusResponse)
def disconnect_channel(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete_many("channel_group_links", {"workspace_id": workspace_id, "channel_id": channel_id})
    db.delete_many("channel_messages", {"workspace_id": workspace_id, "channel_id": channel_id})
    db.delete_one("community_channels", {"workspace_id": workspace_id, "id": channel_id})
    return schemas.AuthStatusResponse(message="Channel disconnected.")


@router.get("/{channel_id}/groups", response_model=list[schemas.ChannelGroupLinkOut])
def list_channel_groups(
    workspace_id: int,
    channel_id: int,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    groups = db.find_many(
        "channel_group_links",
        {"workspace_id": workspace_id, "channel_id": channel_id},
        sort=[("last_seen_at", DESC), ("created_at", DESC)],
    )
    return [_group_out(group) for group in groups]


@router.patch("/{channel_id}/groups/{group_id}", response_model=schemas.ChannelGroupLinkOut)
def update_channel_group_sync(
    workspace_id: int,
    channel_id: int,
    group_id: int,
    payload: schemas.ChannelGroupSyncUpdate,
    db: MongoStore = Depends(get_db),
    _membership=Depends(require_workspace_permission("integrations.manage")),
):
    channel = db.find_one("community_channels", {"workspace_id": workspace_id, "id": channel_id})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    group = db.find_one("channel_group_links", {"workspace_id": workspace_id, "channel_id": channel_id, "id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    group["sync_enabled"] = payload.sync_enabled
    group["updated_at"] = datetime.utcnow()
    db.save("channel_group_links", group)
    _refresh_channel_counts(db, channel)
    return _group_out(group)


@inbound_router.post("/telegram/{channel_id}/webhook", name="telegram_channel_webhook")
async def telegram_channel_webhook(
    channel_id: int,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
):
    channel = db.find_one("community_channels", {"id": channel_id, "provider": "telegram"})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.get("webhook_secret") and channel.get("webhook_secret") != x_telegram_bot_api_secret_token:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")

    payload = await request.json()
    message = payload.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") not in {"group", "supergroup"}:
        return {"ok": True, "status": "ignored_non_group"}

    text = (message.get("text") or message.get("caption") or "").strip()
    if not text:
        return {"ok": True, "status": "ignored_empty"}

    received_at = datetime.utcfromtimestamp(int(message.get("date") or datetime.utcnow().timestamp()))
    group = _discover_or_update_group(
        db,
        workspace_id=channel.workspace_id,
        channel_id=channel.id,
        provider="telegram",
        external_group_id=str(chat.get("id")),
        group_name=str(chat.get("title") or chat.get("username") or chat.get("id")),
        seen_at=received_at,
    )
    _refresh_channel_counts(db, channel)
    if not group.get("sync_enabled"):
        return {"ok": True, "status": "ignored_unselected_group"}

    sender = message.get("from") or {}
    _persist_channel_message(
        db,
        workspace_id=channel.workspace_id,
        channel_id=channel.id,
        group_link=group,
        provider="telegram",
        external_message_id=str(message.get("message_id")) if message.get("message_id") is not None else None,
        sender_name=sender.get("first_name") or sender.get("username"),
        sender_handle=sender.get("username"),
        message_type="text" if message.get("text") else "caption",
        text=text,
        raw_payload=payload,
        received_at=received_at,
    )
    return {"ok": True, "status": "stored"}


@inbound_router.post("/whatsapp/{channel_id}/inbound", name="whatsapp_channel_inbound")
async def whatsapp_channel_inbound(
    channel_id: int,
    request: Request,
    x_quorum_channel_secret: str | None = Header(default=None),
    db: MongoStore = Depends(get_db),
):
    channel = db.find_one("community_channels", {"id": channel_id, "provider": "whatsapp"})
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.get("webhook_secret") and channel.get("webhook_secret") != x_quorum_channel_secret:
        raise HTTPException(status_code=403, detail="Invalid WhatsApp channel secret")

    payload = await request.json()
    remote_jid = str(payload.get("remote_jid") or "").strip()
    if not remote_jid.endswith("@g.us"):
        return {"ok": True, "status": "ignored_non_group"}

    text = str(payload.get("body") or payload.get("caption") or "").strip()
    if not text:
        return {"ok": True, "status": "ignored_empty"}

    received_at_raw = payload.get("received_at")
    if received_at_raw:
        received_at = datetime.fromisoformat(str(received_at_raw).replace("Z", "+00:00")).replace(tzinfo=None)
    else:
        received_at = datetime.utcnow()

    group = _discover_or_update_group(
        db,
        workspace_id=channel.workspace_id,
        channel_id=channel.id,
        provider="whatsapp",
        external_group_id=remote_jid,
        group_name=str(payload.get("chat_name") or payload.get("group_name") or remote_jid),
        seen_at=received_at,
    )
    _refresh_channel_counts(db, channel)
    if not group.get("sync_enabled"):
        return {"ok": True, "status": "ignored_unselected_group"}

    _persist_channel_message(
        db,
        workspace_id=channel.workspace_id,
        channel_id=channel.id,
        group_link=group,
        provider="whatsapp",
        external_message_id=str(payload.get("message_id")) if payload.get("message_id") else None,
        sender_name=payload.get("push_name"),
        sender_handle=payload.get("sender_jid") or payload.get("phone_number"),
        message_type=str(payload.get("message_type") or "text"),
        text=text,
        raw_payload=payload,
        received_at=received_at,
    )
    channel["status"] = "connected"
    channel["last_error"] = None
    db.save("community_channels", channel)
    return {"ok": True, "status": "stored"}
