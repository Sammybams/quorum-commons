from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import PhoneCodeExpiredError, PhoneCodeInvalidError, SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.utils import get_display_name


class TelegramServiceError(RuntimeError):
    pass


@dataclass
class TelegramSessionStartResult:
    phone_code_hash: str
    temp_session: str


@dataclass
class TelegramSessionCompleteResult:
    session_string: str
    user_id: int | None
    username: str | None
    display_name: str | None


@dataclass
class TelegramGroupSummary:
    external_group_id: str
    group_name: str
    username: str | None
    group_type: str


@dataclass
class TelegramMessageSummary:
    external_group_id: str
    external_message_id: str
    sender_name: str | None
    sender_handle: str | None
    message_type: str
    text: str
    received_at: datetime
    raw_payload: dict[str, object]


def _normalize_phone_number(value: str) -> str:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if not digits:
        raise TelegramServiceError("A valid Telegram phone number is required.")
    return f"+{digits}"


def _message_type(message) -> str:
    if getattr(message, "photo", None):
        return "image"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "document", None):
        return "document"
    if getattr(message, "sticker", None):
        return "sticker"
    return "text"


async def telegram_session_start(*, api_id: int, api_hash: str, phone_number: str) -> TelegramSessionStartResult:
    client = TelegramClient(StringSession(""), api_id, api_hash)
    await client.connect()
    try:
        sent = await client.send_code_request(_normalize_phone_number(phone_number))
        return TelegramSessionStartResult(
            phone_code_hash=sent.phone_code_hash,
            temp_session=client.session.save(),
        )
    except Exception as exc:
        raise TelegramServiceError(str(exc)) from exc
    finally:
        await client.disconnect()


async def telegram_session_complete(
    *,
    api_id: int,
    api_hash: str,
    temp_session: str,
    phone_number: str,
    code: str,
    phone_code_hash: str,
    password: str | None = None,
) -> TelegramSessionCompleteResult:
    client = TelegramClient(StringSession(temp_session or ""), api_id, api_hash)
    await client.connect()
    try:
        try:
            await client.sign_in(
                phone=_normalize_phone_number(phone_number),
                code="".join(str(code or "").split()),
                phone_code_hash=phone_code_hash,
            )
        except PhoneCodeExpiredError as exc:
            raise TelegramServiceError("Telegram code expired. Start a fresh login code request.") from exc
        except PhoneCodeInvalidError as exc:
            raise TelegramServiceError("Telegram code is invalid. Enter the latest code and try again.") from exc
        except SessionPasswordNeededError as exc:
            if not password:
                raise TelegramServiceError("Telegram two-step password is required for this account.") from exc
            await client.sign_in(password=password)

        me = await client.get_me()
        return TelegramSessionCompleteResult(
            session_string=client.session.save(),
            user_id=getattr(me, "id", None),
            username=getattr(me, "username", None),
            display_name=get_display_name(me) or getattr(me, "first_name", None),
        )
    except TelegramServiceError:
        raise
    except Exception as exc:
        raise TelegramServiceError(str(exc)) from exc
    finally:
        await client.disconnect()


async def telegram_list_groups(*, api_id: int, api_hash: str, session_string: str) -> list[TelegramGroupSummary]:
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.connect()
    try:
        dialogs = await client.get_dialogs(limit=None)
        groups: list[TelegramGroupSummary] = []
        for dialog in dialogs:
            if not (dialog.is_group or dialog.is_channel):
                continue
            entity = dialog.entity
            group_type = "channel" if dialog.is_channel else "group"
            if getattr(entity, "megagroup", False):
                group_type = "supergroup"
            groups.append(
                TelegramGroupSummary(
                    external_group_id=str(dialog.id),
                    group_name=str(dialog.name or get_display_name(entity) or dialog.id),
                    username=getattr(entity, "username", None),
                    group_type=group_type,
                )
            )
        return groups
    except Exception as exc:
        raise TelegramServiceError(str(exc)) from exc
    finally:
        await client.disconnect()


async def telegram_sync_group_messages(
    *,
    api_id: int,
    api_hash: str,
    session_string: str,
    external_group_ids: list[str],
    last_synced_message_ids: dict[str, int] | None = None,
    per_group_limit: int = 50,
) -> list[TelegramMessageSummary]:
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.connect()
    try:
        dialogs = await client.get_dialogs(limit=None)
        entities_by_group_id = {
            str(dialog.id): dialog.entity
            for dialog in dialogs
            if dialog.is_group or dialog.is_channel
        }
        synced: list[TelegramMessageSummary] = []
        for external_group_id in external_group_ids:
            entity = entities_by_group_id.get(str(external_group_id))
            if entity is None:
                continue
            min_id = int((last_synced_message_ids or {}).get(str(external_group_id), 0) or 0)
            batch: list[TelegramMessageSummary] = []
            async for message in client.iter_messages(entity, limit=per_group_limit, min_id=min_id):
                text = str(getattr(message, "message", "") or "").strip()
                if not text:
                    continue
                sender = await message.get_sender()
                sender_name = get_display_name(sender) if sender else None
                sender_handle = getattr(sender, "username", None) or getattr(sender, "phone", None)
                received_at = message.date.astimezone(timezone.utc).replace(tzinfo=None) if message.date else datetime.utcnow()
                batch.append(
                    TelegramMessageSummary(
                        external_group_id=str(external_group_id),
                        external_message_id=str(message.id),
                        sender_name=sender_name,
                        sender_handle=sender_handle,
                        message_type=_message_type(message),
                        text=text,
                        received_at=received_at,
                        raw_payload={
                            "message_id": message.id,
                            "chat_id": external_group_id,
                            "sender_id": getattr(message, "sender_id", None),
                            "text": text,
                            "date": received_at.isoformat(),
                            "reply_to_msg_id": getattr(message, "reply_to_msg_id", None),
                        },
                    )
                )
            batch.sort(key=lambda item: int(item.external_message_id))
            synced.extend(batch)
        return synced
    except Exception as exc:
        raise TelegramServiceError(str(exc)) from exc
    finally:
        await client.disconnect()
