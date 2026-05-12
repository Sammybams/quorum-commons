# Quorum WhatsApp Gateway

Small Baileys-based bridge used only for Quorum WhatsApp group sync.

Environment variables:

```text
HOST=127.0.0.1
PORT=3001
WHATSAPP_GATEWAY_TOKEN=
WHATSAPP_AUTH_ROOT=
QUORUM_API_BASE_URL=http://127.0.0.1:8000/api/v1
QUORUM_WHATSAPP_CHANNEL_ID=
QUORUM_WHATSAPP_CHANNEL_SECRET=
```

Flow:

1. Create a WhatsApp channel in Quorum Integrations.
2. Copy the channel ID and shared secret into this gateway env.
3. Start the gateway with `npm install && npm start`.
4. Use the internal endpoints to connect the WhatsApp account.
5. The gateway fetches the selected group IDs from Quorum and forwards only those group messages.

Internal endpoints:

- `GET /health`
- `GET /internal/session`
- `POST /internal/session/connect`
- `POST /internal/session/disconnect`

All `/internal/*` routes require `x-internal-token` when `WHATSAPP_GATEWAY_TOKEN` is set.
