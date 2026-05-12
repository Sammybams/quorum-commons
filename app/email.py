import html
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class EmailResult:
    status: str
    error: str | None = None
    provider: str | None = None
    sender: str | None = None


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL"))


def _frontend_url() -> str:
    return (
        os.getenv("FRONTEND_URL")
        or os.getenv("PUBLIC_APP_URL")
        or os.getenv("APP_URL")
        or "http://localhost:3000"
    ).rstrip("/")


def invitation_url(token: str) -> str:
    return f"{_frontend_url()}/invites/{token}"


def verification_url(token: str) -> str:
    return f"{_frontend_url()}/verify-email?token={token}"


def reset_password_url(token: str) -> str:
    return f"{_frontend_url()}/reset-password/{token}"


def send_invitation_email(
    *,
    to_email: str,
    workspace_name: str,
    role_name: str,
    token: str,
    note: str | None = None,
    reply_to: str | None = None,
) -> EmailResult:
    if not _smtp_configured():
        return EmailResult(status="not_configured", provider="smtp")

    from_email = os.getenv("SMTP_FROM_EMAIL", "")
    from_name = os.getenv("SMTP_FROM_NAME", "Quorum")
    message = build_invitation_email(
        to_email=to_email,
        workspace_name=workspace_name,
        role_name=role_name,
        token=token,
        note=note,
        reply_to=reply_to,
        from_email=from_email,
        from_name=from_name,
    )

    try:
        _deliver(message)
    except Exception as exc:  # SMTP providers raise several different exception types.
        return EmailResult(status="failed", error=str(exc), provider="smtp", sender=from_email)

    return EmailResult(status="sent", provider="smtp", sender=from_email)


def build_invitation_email(
    *,
    to_email: str,
    workspace_name: str,
    role_name: str,
    token: str,
    note: str | None = None,
    reply_to: str | None = None,
    from_email: str,
    from_name: str,
) -> EmailMessage:
    link = invitation_url(token)
    subject = f"Join {workspace_name} on Quorum"

    safe_workspace = html.escape(workspace_name)
    safe_role = html.escape(role_name)
    safe_note = html.escape(note or "")
    safe_link = html.escape(link)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(
        "\n".join(
            [
                f"You have been invited to join {workspace_name} as {role_name}.",
                "",
                note or "",
                "",
                f"Accept the invitation: {link}",
            ]
        )
    )
    message.add_alternative(
        f"""
        <!doctype html>
        <html>
          <body style="margin:0;background:#f8fafc;font-family:Inter,Arial,sans-serif;color:#0f172a;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:32px 16px;">
              <tr>
                <td align="center">
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;padding:28px;">
                    <tr>
                      <td>
                        <p style="margin:0 0 12px;color:#64748b;font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;">Quorum invite</p>
                        <h1 style="margin:0 0 12px;font-size:24px;line-height:1.2;color:#0f172a;">Join {safe_workspace}</h1>
                        <p style="margin:0 0 18px;font-size:15px;line-height:1.6;color:#475569;">You have been invited to join <strong>{safe_workspace}</strong> as <strong>{safe_role}</strong>.</p>
                        {f'<p style="margin:0 0 18px;font-size:14px;line-height:1.6;color:#475569;">{safe_note}</p>' if safe_note else ''}
                        <p style="margin:0 0 24px;font-size:14px;line-height:1.6;color:#64748b;">This invite expires in 72 hours.</p>
                        <a href="{safe_link}" style="display:inline-block;background:#1b5ef7;color:#ffffff;text-decoration:none;border-radius:8px;padding:12px 18px;font-weight:600;font-size:14px;">Accept invitation</a>
                        <p style="margin:24px 0 0;font-size:12px;line-height:1.5;color:#94a3b8;">If the button does not work, paste this link into your browser:<br>{safe_link}</p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </body>
        </html>
        """,
        subtype="html",
    )
    return message


def send_verification_email(*, to_email: str, full_name: str, token: str) -> EmailResult:
    if not _smtp_configured():
        return EmailResult(status="not_configured")

    link = verification_url(token)
    subject = "Verify your Quorum email"
    return _send_simple_email(
        to_email=to_email,
        subject=subject,
        intro=f"Hi {full_name}, verify your email to finish setting up Quorum.",
        action_label="Verify email",
        action_url=link,
        footer="This link expires in 24 hours.",
    )


def send_password_reset_email(*, to_email: str, full_name: str, token: str) -> EmailResult:
    if not _smtp_configured():
        return EmailResult(status="not_configured")

    link = reset_password_url(token)
    subject = "Reset your Quorum password"
    return _send_simple_email(
        to_email=to_email,
        subject=subject,
        intro=f"Hi {full_name}, use the button below to reset your password.",
        action_label="Reset password",
        action_url=link,
        footer="This link expires in 1 hour. If you did not request this, you can ignore this email.",
    )


def _send_simple_email(
    *,
    to_email: str,
    subject: str,
    intro: str,
    action_label: str,
    action_url: str,
    footer: str,
) -> EmailResult:
    from_email = os.getenv("SMTP_FROM_EMAIL", "")
    from_name = os.getenv("SMTP_FROM_NAME", "Quorum")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message.set_content("\n".join([intro, "", action_url, "", footer]))
    message.add_alternative(
        f"""
        <!doctype html>
        <html>
          <body style="margin:0;background:#f8fafc;font-family:Inter,Arial,sans-serif;color:#0f172a;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:32px 16px;">
              <tr>
                <td align="center">
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;padding:28px;">
                    <tr>
                      <td>
                        <p style="margin:0 0 18px;font-size:15px;line-height:1.6;color:#475569;">{html.escape(intro)}</p>
                        <a href="{html.escape(action_url)}" style="display:inline-block;background:#1b5ef7;color:#ffffff;text-decoration:none;border-radius:8px;padding:12px 18px;font-weight:600;font-size:14px;">{html.escape(action_label)}</a>
                        <p style="margin:24px 0 0;font-size:12px;line-height:1.5;color:#94a3b8;">{html.escape(footer)}<br>{html.escape(action_url)}</p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </body>
        </html>
        """,
        subtype="html",
    )

    try:
        _deliver(message)
    except Exception as exc:
        return EmailResult(status="failed", error=str(exc))

    return EmailResult(status="sent")


def send_announcement_email(
    *,
    to_email: str,
    full_name: str,
    workspace_name: str,
    title: str,
    body: str,
) -> EmailResult:
    if not _smtp_configured():
        return EmailResult(status="not_configured")

    return _send_simple_email(
        to_email=to_email,
        subject=f"{workspace_name}: {title}",
        intro=f"Hi {full_name}, {workspace_name} shared an announcement: {title}",
        action_label="Open Quorum",
        action_url=_frontend_url(),
        footer=body[:400],
    )


def _deliver(message: EmailMessage) -> None:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=10) as server:
            if username and password:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls(context=ssl.create_default_context())
            if username and password:
                server.login(username, password)
            server.send_message(message)
