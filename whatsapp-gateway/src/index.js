const fs = require('fs/promises')
const path = require('path')

const express = require('express')
const pino = require('pino')
const QRCode = require('qrcode')
const { Boom } = require('@hapi/boom')
const {
  default: makeWASocket,
  Browsers,
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} = require('@whiskeysockets/baileys')

const app = express()
app.use(express.json({ limit: '1mb' }))

const logger = pino({ level: process.env.LOG_LEVEL || 'info' })
const HOST = process.env.HOST || '127.0.0.1'
const PORT = Number(process.env.PORT || 3001)
const INTERNAL_TOKEN = String(process.env.WHATSAPP_GATEWAY_TOKEN || '').trim()
const AUTH_ROOT = process.env.WHATSAPP_AUTH_ROOT || path.join(process.cwd(), '.auth', 'whatsapp')
const QUORUM_API_BASE_URL = String(process.env.QUORUM_API_BASE_URL || 'http://127.0.0.1:8000/api/v1').trim().replace(/\/$/, '')
const QUORUM_WHATSAPP_CHANNEL_ID = String(process.env.QUORUM_WHATSAPP_CHANNEL_ID || '').trim()
const QUORUM_WHATSAPP_CHANNEL_SECRET = String(process.env.QUORUM_WHATSAPP_CHANNEL_SECRET || '').trim()

const sessions = new Map()
const selectedGroupsCache = new Map()

app.use((req, res, next) => {
  if (!req.path.startsWith('/internal')) return next()
  if (!INTERNAL_TOKEN) return next()
  if (req.header('x-internal-token') !== INTERNAL_TOKEN) {
    return res.status(401).json({ error: 'unauthorized' })
  }
  next()
})

function nowIso() {
  return new Date().toISOString()
}

function sanitizePhoneNumber(value) {
  return String(value || '').replace(/\D+/g, '')
}

function normalizePairingMode(value) {
  const normalized = String(value || 'qr').trim().toLowerCase().replace(/-/g, '_')
  return normalized === 'pairing_code' ? 'pairing_code' : 'qr'
}

function sessionDirFor(channelId) {
  return path.join(AUTH_ROOT, String(channelId))
}

async function ensureAuthRoot() {
  await fs.mkdir(AUTH_ROOT, { recursive: true })
}

function derivePhoneNumberFromJid(jid) {
  const normalized = String(jid || '').trim()
  if (!normalized) return null
  const local = normalized.split('@')[0].split(':')[0]
  const digits = sanitizePhoneNumber(local)
  return digits || null
}

function normalizeMessageTimestamp(value) {
  if (value == null) return null
  if (typeof value === 'number') return value > 1_000_000_000_000 ? value : value * 1000
  if (typeof value === 'string') {
    const numeric = Number(value)
    return Number.isFinite(numeric) ? normalizeMessageTimestamp(numeric) : null
  }
  if (typeof value === 'object') {
    if (typeof value.toNumber === 'function') {
      try {
        return normalizeMessageTimestamp(value.toNumber())
      } catch {}
    }
    if (typeof value.low === 'number') return normalizeMessageTimestamp(value.low)
  }
  return null
}

function unwrapMessageContainer(message) {
  if (!message || typeof message !== 'object') return null
  if (message.ephemeralMessage?.message) return unwrapMessageContainer(message.ephemeralMessage.message)
  if (message.viewOnceMessage?.message) return unwrapMessageContainer(message.viewOnceMessage.message)
  if (message.viewOnceMessageV2?.message) return unwrapMessageContainer(message.viewOnceMessageV2.message)
  if (message.documentWithCaptionMessage?.message) return unwrapMessageContainer(message.documentWithCaptionMessage.message)
  if (message.editedMessage?.message) return unwrapMessageContainer(message.editedMessage.message)
  return message
}

function extractMessageText(message) {
  const unwrapped = unwrapMessageContainer(message)
  if (!unwrapped || typeof unwrapped !== 'object') return ''
  return String(
    unwrapped.conversation
      || unwrapped.extendedTextMessage?.text
      || unwrapped.imageMessage?.caption
      || unwrapped.videoMessage?.caption
      || unwrapped.documentMessage?.caption
      || unwrapped.buttonsResponseMessage?.selectedDisplayText
      || unwrapped.listResponseMessage?.title
      || unwrapped.listResponseMessage?.singleSelectReply?.selectedRowId
      || unwrapped.templateButtonReplyMessage?.selectedDisplayText
      || unwrapped.buttonsMessage?.contentText
      || ''
  ).trim()
}

function extractMessageContextInfo(message) {
  const unwrapped = unwrapMessageContainer(message)
  if (!unwrapped || typeof unwrapped !== 'object') return null
  return (
    unwrapped.extendedTextMessage?.contextInfo
    || unwrapped.imageMessage?.contextInfo
    || unwrapped.videoMessage?.contextInfo
    || unwrapped.documentMessage?.contextInfo
    || unwrapped.buttonsResponseMessage?.contextInfo
    || unwrapped.listResponseMessage?.contextInfo
    || unwrapped.templateButtonReplyMessage?.contextInfo
    || null
  )
}

function extractQuotedMessageId(message) {
  const contextInfo = extractMessageContextInfo(message)
  const stanzaId = String(contextInfo?.stanzaId || '').trim()
  return stanzaId || null
}

function detectMessageType(message) {
  const unwrapped = unwrapMessageContainer(message)
  if (!unwrapped || typeof unwrapped !== 'object') return 'unknown'
  if (unwrapped.imageMessage) return 'image'
  if (unwrapped.videoMessage) return 'video'
  if (unwrapped.documentMessage) return 'document'
  if (unwrapped.extendedTextMessage || unwrapped.conversation) return 'text'
  return Object.keys(unwrapped)[0] || 'unknown'
}

async function toQrDataUrl(qr) {
  if (!qr) return null
  try {
    return await QRCode.toDataURL(qr, { margin: 1, width: 280 })
  } catch (error) {
    logger.warn({ error: String(error) }, 'Failed to render QR data URL')
    return null
  }
}

function markSessionUpdated(session) {
  session.updatedAt = nowIso()
}

function serializeSession(session) {
  return {
    channelId: session.channelId,
    state: session.state,
    isConnected: session.state === 'connected',
    phoneNumber: session.phoneNumber || null,
    pairingMode: session.pairingMode,
    jid: session.jid || null,
    displayName: session.displayName || null,
    qrCodeDataUrl: session.qrCodeDataUrl || null,
    pairingCode: session.pairingCode || null,
    lastError: session.lastError || null,
    connectedAt: session.connectedAt || null,
    updatedAt: session.updatedAt || null,
  }
}

function gatewayConfigUrl() {
  if (!QUORUM_API_BASE_URL || !QUORUM_WHATSAPP_CHANNEL_ID) return ''
  return `${QUORUM_API_BASE_URL}/community-channels/whatsapp/${QUORUM_WHATSAPP_CHANNEL_ID}/gateway-config`
}

function inboundUrl() {
  if (!QUORUM_API_BASE_URL || !QUORUM_WHATSAPP_CHANNEL_ID) return ''
  return `${QUORUM_API_BASE_URL}/community-channels/whatsapp/${QUORUM_WHATSAPP_CHANNEL_ID}/inbound`
}

async function fetchGatewayConfig() {
  const url = gatewayConfigUrl()
  if (!url) return { selected_group_ids: [] }
  const cached = selectedGroupsCache.get(url)
  if (cached && Date.now() - cached.fetchedAt < 30_000) {
    return cached.payload
  }
  const response = await fetch(url, {
    headers: QUORUM_WHATSAPP_CHANNEL_SECRET ? { 'x-quorum-channel-secret': QUORUM_WHATSAPP_CHANNEL_SECRET } : {},
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`Failed to load gateway config: ${response.status} ${detail.slice(0, 300)}`)
  }
  const payload = await response.json()
  selectedGroupsCache.set(url, { fetchedAt: Date.now(), payload })
  return payload
}

async function postInboundMessage(payload) {
  const url = inboundUrl()
  if (!url) return
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(QUORUM_WHATSAPP_CHANNEL_SECRET ? { 'x-quorum-channel-secret': QUORUM_WHATSAPP_CHANNEL_SECRET } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`Inbound delivery failed: ${response.status} ${detail.slice(0, 300)}`)
  }
}

async function stopSession(channelId, { logout = false, removeAuth = false } = {}) {
  const session = sessions.get(String(channelId))
  if (session) {
    session.shouldReconnect = false
    if (logout && session.socket) {
      try {
        await session.socket.logout()
      } catch (error) {
        logger.warn({ channelId, error: String(error) }, 'WhatsApp logout failed')
      }
    }
    try {
      session.socket?.end?.(new Error('session closed'))
    } catch {}
    sessions.delete(String(channelId))
  }
  if (removeAuth) {
    await fs.rm(sessionDirFor(channelId), { recursive: true, force: true })
  }
}

async function startSession({ channelId, phoneNumber = null, pairingMode = 'qr' }) {
  const key = String(channelId)
  const existing = sessions.get(key)
  if (existing?.socket) return existing

  await ensureAuthRoot()
  const authDir = sessionDirFor(channelId)
  await fs.mkdir(authDir, { recursive: true })

  const session = existing || {
    channelId,
    phoneNumber: sanitizePhoneNumber(phoneNumber) || null,
    pairingMode: normalizePairingMode(pairingMode),
    state: 'connecting',
    socket: null,
    qrCodeDataUrl: null,
    pairingCode: null,
    jid: null,
    displayName: null,
    connectedAt: null,
    updatedAt: nowIso(),
    lastError: null,
    pairingCodeRequested: false,
    shouldReconnect: true,
  }
  session.phoneNumber = sanitizePhoneNumber(phoneNumber) || session.phoneNumber
  session.pairingMode = normalizePairingMode(pairingMode)
  session.state = 'connecting'
  session.lastError = null
  session.qrCodeDataUrl = null
  session.pairingCode = null
  session.pairingCodeRequested = false
  session.shouldReconnect = true
  markSessionUpdated(session)
  sessions.set(key, session)

  const { state, saveCreds } = await useMultiFileAuthState(authDir)
  const { version } = await fetchLatestBaileysVersion()
  const socket = makeWASocket({
    version,
    auth: state,
    browser: Browsers.macOS('Quorum WhatsApp Gateway'),
    printQRInTerminal: false,
    logger: logger.child({ module: 'baileys', channelId, level: 'silent' }),
    syncFullHistory: false,
    shouldSyncHistoryMessage: () => false,
    markOnlineOnConnect: false,
  })
  session.socket = socket

  socket.ev.on('creds.update', saveCreds)
  socket.ev.on('messages.upsert', async (event) => {
    if (!event || event.type !== 'notify') return
    const config = await fetchGatewayConfig().catch((error) => {
      logger.warn({ channelId, error: String(error) }, 'Failed to load WhatsApp selected groups')
      return { selected_group_ids: [] }
    })
    const selectedGroups = Array.isArray(config.selected_group_ids) ? config.selected_group_ids : []
    const connectedAtMs = session.connectedAt ? Date.parse(session.connectedAt) : null

    for (const inbound of event.messages || []) {
      if (!inbound?.key || inbound.key.fromMe) continue
      const remoteJid = String(inbound.key.remoteJid || '').trim()
      if (!remoteJid || remoteJid === 'status@broadcast' || !remoteJid.endsWith('@g.us')) continue
      if (selectedGroups.length === 0 || !selectedGroups.includes(remoteJid)) continue

      const body = extractMessageText(inbound.message)
      if (!body) continue

      const receivedAtMs = normalizeMessageTimestamp(inbound.messageTimestamp) || Date.now()
      if (connectedAtMs && receivedAtMs < connectedAtMs) continue

      const payload = {
        account_id: channelId,
        remote_jid: remoteJid,
        phone_number: derivePhoneNumberFromJid(remoteJid),
        sender_jid: String(inbound.key.participant || '').trim() || null,
        message_id: String(inbound.key.id || '').trim() || null,
        quoted_message_id: extractQuotedMessageId(inbound.message),
        body,
        chat_name: remoteJid,
        message_type: detectMessageType(inbound.message),
        push_name: String(inbound.pushName || '').trim() || null,
        received_at: new Date(receivedAtMs).toISOString(),
      }

      try {
        await postInboundMessage(payload)
      } catch (error) {
        logger.warn({ channelId, remoteJid, error: String(error) }, 'Failed to forward WhatsApp message to Quorum')
      }
    }
  })

  socket.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update
    if (qr) {
      session.state = session.pairingMode === 'pairing_code' ? 'pairing_pending' : 'qr_pending'
      session.qrCodeDataUrl = await toQrDataUrl(qr)
      markSessionUpdated(session)
    }

    if (
      session.pairingMode === 'pairing_code' &&
      !session.pairingCodeRequested &&
      !session.socket?.authState?.creds?.registered &&
      (connection === 'connecting' || Boolean(qr))
    ) {
      const targetPhone = sanitizePhoneNumber(session.phoneNumber)
      if (targetPhone) {
        session.pairingCodeRequested = true
        try {
          const code = await session.socket.requestPairingCode(targetPhone)
          session.state = 'pairing_pending'
          session.pairingCode = code
          session.qrCodeDataUrl = null
          session.lastError = null
          markSessionUpdated(session)
        } catch (error) {
          session.pairingCodeRequested = false
          session.lastError = String(error)
          markSessionUpdated(session)
        }
      }
    }

    if (connection === 'open') {
      session.state = 'connected'
      session.connectedAt = session.connectedAt || nowIso()
      session.qrCodeDataUrl = null
      session.pairingCode = null
      session.pairingCodeRequested = false
      session.lastError = null
      session.jid = socket.user?.id || session.jid
      session.displayName = socket.user?.name || session.displayName
      session.phoneNumber = derivePhoneNumberFromJid(session.jid) || session.phoneNumber
      markSessionUpdated(session)
      return
    }

    if (connection === 'close') {
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode
      session.socket = null
      session.qrCodeDataUrl = null
      session.pairingCode = null
      session.pairingCodeRequested = false
      session.lastError = lastDisconnect?.error ? String(lastDisconnect.error) : null
      session.state = statusCode === DisconnectReason.loggedOut ? 'logged_out' : 'disconnected'
      markSessionUpdated(session)

      if (statusCode === DisconnectReason.loggedOut) {
        try {
          await fs.rm(sessionDirFor(channelId), { recursive: true, force: true })
        } catch {}
        return
      }

      if (session.shouldReconnect) {
        setTimeout(() => {
          startSession({
            channelId,
            phoneNumber: session.phoneNumber,
            pairingMode: session.pairingMode,
          }).catch((error) => {
            session.lastError = String(error)
            session.state = 'disconnected'
            markSessionUpdated(session)
          })
        }, 1500)
      }
    }
  })

  return session
}

app.get('/health', (_req, res) => {
  res.json({ ok: true, channelId: QUORUM_WHATSAPP_CHANNEL_ID || null, sessions: sessions.size })
})

app.get('/internal/session', async (_req, res) => {
  const session = sessions.get(String(QUORUM_WHATSAPP_CHANNEL_ID))
  res.json(session ? serializeSession(session) : { channelId: QUORUM_WHATSAPP_CHANNEL_ID || null, state: 'idle' })
})

app.post('/internal/session/connect', async (req, res) => {
  if (!QUORUM_WHATSAPP_CHANNEL_ID) {
    return res.status(400).json({ error: 'QUORUM_WHATSAPP_CHANNEL_ID is required' })
  }
  try {
    const session = await startSession({
      channelId: QUORUM_WHATSAPP_CHANNEL_ID,
      phoneNumber: req.body?.phoneNumber || null,
      pairingMode: req.body?.pairingMode || 'qr',
    })
    res.json(serializeSession(session))
  } catch (error) {
    logger.error({ error: String(error) }, 'Failed to start Quorum WhatsApp session')
    res.status(500).json({ error: String(error) })
  }
})

app.post('/internal/session/disconnect', async (req, res) => {
  if (!QUORUM_WHATSAPP_CHANNEL_ID) {
    return res.status(400).json({ error: 'QUORUM_WHATSAPP_CHANNEL_ID is required' })
  }
  try {
    await stopSession(QUORUM_WHATSAPP_CHANNEL_ID, {
      logout: Boolean(req.body?.logout),
      removeAuth: Boolean(req.body?.removeAuth),
    })
    res.json({ ok: true })
  } catch (error) {
    logger.error({ error: String(error) }, 'Failed to stop Quorum WhatsApp session')
    res.status(500).json({ error: String(error) })
  }
})

app.listen(PORT, HOST, () => {
  logger.info({ host: HOST, port: PORT, channelId: QUORUM_WHATSAPP_CHANNEL_ID || null }, 'Quorum WhatsApp gateway listening')
})
