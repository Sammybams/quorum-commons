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
const MAX_HISTORY_MESSAGES_PER_GROUP = Number(process.env.WHATSAPP_HISTORY_PER_GROUP || 150)

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

function extractAttachmentName(message) {
  const unwrapped = unwrapMessageContainer(message)
  if (!unwrapped || typeof unwrapped !== 'object') return null
  return String(
    unwrapped.documentMessage?.fileName
      || unwrapped.imageMessage?.fileName
      || unwrapped.videoMessage?.fileName
      || ''
  ).trim() || null
}

function extractAttachmentMimeType(message) {
  const unwrapped = unwrapMessageContainer(message)
  if (!unwrapped || typeof unwrapped !== 'object') return null
  return String(
    unwrapped.documentMessage?.mimetype
      || unwrapped.imageMessage?.mimetype
      || unwrapped.videoMessage?.mimetype
      || ''
  ).trim() || null
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
    qrUpdatedAt: session.qrUpdatedAt || null,
    lastError: session.lastError || null,
    connectedAt: session.connectedAt || null,
    updatedAt: session.updatedAt || null,
  }
}

function ensureSessionCaches(session) {
  if (!session.groupNames) session.groupNames = new Map()
  if (!session.historyCache) session.historyCache = new Map()
  if (!session.historyDeliveredIds) session.historyDeliveredIds = new Set()
}

function rememberGroupMetadata(session, groups = []) {
  ensureSessionCaches(session)
  for (const group of groups) {
    const groupId = String(group?.external_group_id || group?.id || '').trim()
    const groupName = String(group?.group_name || group?.subject || group?.name || '').trim()
    if (groupId && groupName) {
      session.groupNames.set(groupId, groupName)
    }
  }
}

function groupNameFor(session, remoteJid, fallback = null) {
  ensureSessionCaches(session)
  return session.groupNames.get(remoteJid) || fallback || remoteJid
}

function historyCacheKey(payload) {
  return payload?.remote_jid && payload?.message_id ? `${payload.remote_jid}:${payload.message_id}` : null
}

function cacheHistoryPayload(session, payload) {
  ensureSessionCaches(session)
  const cacheKey = historyCacheKey(payload)
  if (!cacheKey || session.historyDeliveredIds.has(cacheKey)) return

  const remoteJid = String(payload.remote_jid || '').trim()
  if (!remoteJid) return

  const existing = session.historyCache.get(remoteJid) || []
  if (existing.some((item) => historyCacheKey(item) === cacheKey)) return

  existing.push(payload)
  existing.sort((left, right) => Date.parse(String(left.received_at || 0)) - Date.parse(String(right.received_at || 0)))
  if (existing.length > MAX_HISTORY_MESSAGES_PER_GROUP) {
    existing.splice(0, existing.length - MAX_HISTORY_MESSAGES_PER_GROUP)
  }
  session.historyCache.set(remoteJid, existing)
}

function buildInboundPayload(session, inbound, options = {}) {
  if (!inbound?.key) return null
  const remoteJid = String(inbound.key.remoteJid || '').trim()
  if (!remoteJid || remoteJid === 'status@broadcast' || !remoteJid.endsWith('@g.us')) return null

  const body = extractMessageText(inbound.message)
  const messageType = detectMessageType(inbound.message)
  if (!body && !['image', 'document', 'video'].includes(messageType)) return null

  const senderJid = String(
    inbound.key.fromMe
      ? session.jid || inbound.key.participant || ''
      : inbound.key.participant || ''
  ).trim() || null
  const receivedAtMs = normalizeMessageTimestamp(inbound.messageTimestamp) || Date.now()

  return {
    account_id: session.channelId,
    remote_jid: remoteJid,
    phone_number: derivePhoneNumberFromJid(senderJid || remoteJid),
    sender_jid: senderJid,
    message_id: String(inbound.key.id || '').trim() || null,
    quoted_message_id: extractQuotedMessageId(inbound.message),
    body,
    chat_name: groupNameFor(session, remoteJid, options.chatName || remoteJid),
    message_type: messageType,
    attachment_name: extractAttachmentName(inbound.message),
    attachment_mime_type: extractAttachmentMimeType(inbound.message),
    push_name: String(
      inbound.pushName
        || (inbound.key.fromMe ? session.displayName || session.phoneNumber || '' : '')
    ).trim() || null,
    received_at: new Date(receivedAtMs).toISOString(),
    from_me: Boolean(inbound.key.fromMe),
    sync_source: String(options.syncSource || 'live'),
  }
}

function gatewayConfigUrl(channelId) {
  if (!QUORUM_API_BASE_URL || !channelId) return ''
  return `${QUORUM_API_BASE_URL}/community-channels/whatsapp/${channelId}/gateway-config`
}

function inboundUrl(channelId) {
  if (!QUORUM_API_BASE_URL || !channelId) return ''
  return `${QUORUM_API_BASE_URL}/community-channels/whatsapp/${channelId}/inbound`
}

function discoverGroupsUrl(channelId) {
  if (!QUORUM_API_BASE_URL || !channelId) return ''
  return `${QUORUM_API_BASE_URL}/community-channels/whatsapp/${channelId}/discover-groups`
}

async function fetchGatewayConfig(session, options = {}) {
  const url = gatewayConfigUrl(session.channelId)
  if (!url) return { selected_group_ids: [] }
  const forceRefresh = Boolean(options.forceRefresh)
  const cached = selectedGroupsCache.get(url)
  if (!forceRefresh && cached && Date.now() - cached.fetchedAt < 5_000) {
    return cached.payload
  }
  const response = await fetch(url, {
    headers: session.sharedSecret ? { 'x-quorum-channel-secret': session.sharedSecret } : {},
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`Failed to load gateway config: ${response.status} ${detail.slice(0, 300)}`)
  }
  const payload = await response.json()
  selectedGroupsCache.set(url, { fetchedAt: Date.now(), payload })
  return payload
}

async function postInboundMessage(session, payload) {
  const url = inboundUrl(session.channelId)
  if (!url) return
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(session.sharedSecret ? { 'x-quorum-channel-secret': session.sharedSecret } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`Inbound delivery failed: ${response.status} ${detail.slice(0, 300)}`)
  }
  return response.json().catch(() => ({ ok: true }))
}

async function discoverGroupsForSession(session) {
  if (!session?.socket) return []
  const participating = await session.socket.groupFetchAllParticipating()
  const groups = Object.values(participating || {})
    .map((group) => ({
      external_group_id: String(group?.id || '').trim(),
      group_name: String(group?.subject || group?.name || group?.id || '').trim(),
    }))
    .filter((group) => group.external_group_id.endsWith('@g.us') && group.group_name)
  rememberGroupMetadata(session, groups)
  return groups
}

async function postDiscoveredGroups(session, groups) {
  const url = discoverGroupsUrl(session.channelId)
  if (!url) return
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(session.sharedSecret ? { 'x-quorum-channel-secret': session.sharedSecret } : {}),
    },
    body: JSON.stringify({ groups }),
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`Group discovery delivery failed: ${response.status} ${detail.slice(0, 300)}`)
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

async function syncSelectedGroupHistory(session) {
  if (!session?.socket || session.state !== 'connected') {
    throw new Error('session_not_connected')
  }

  ensureSessionCaches(session)
  const config = await fetchGatewayConfig(session, { forceRefresh: true })
  const selectedGroups = Array.isArray(config.selected_group_ids) ? config.selected_group_ids : []
  let syncedMessages = 0

  for (const groupId of selectedGroups) {
    const history = session.historyCache.get(groupId) || []
    for (const payload of history) {
      const cacheKey = historyCacheKey(payload)
      if (!cacheKey || session.historyDeliveredIds.has(cacheKey)) continue
      try {
        await postInboundMessage(session, payload)
        session.historyDeliveredIds.add(cacheKey)
        syncedMessages += 1
      } catch (error) {
        logger.warn({ channelId: session.channelId, groupId, error: String(error) }, 'Failed to deliver cached WhatsApp history message')
      }
    }
  }

  markSessionUpdated(session)
  return {
    channelId: session.channelId,
    selectedGroups: selectedGroups.length,
    syncedMessages,
  }
}

async function startSession({ channelId, sharedSecret, phoneNumber = null, pairingMode = 'qr', label = null }) {
  const key = String(channelId)
  const existing = sessions.get(key)
  if (existing?.socket) return existing

  await ensureAuthRoot()
  const authDir = sessionDirFor(channelId)
  await fs.mkdir(authDir, { recursive: true })

  const session = existing || {
    channelId,
    label,
    sharedSecret: String(sharedSecret || '').trim() || null,
    phoneNumber: sanitizePhoneNumber(phoneNumber) || null,
    pairingMode: normalizePairingMode(pairingMode),
    state: 'connecting',
    socket: null,
    qrCodeDataUrl: null,
    qrUpdatedAt: null,
    jid: null,
    displayName: null,
    connectedAt: null,
    updatedAt: nowIso(),
    lastError: null,
    pairingCodeRequested: false,
    shouldReconnect: true,
    groupNames: new Map(),
    historyCache: new Map(),
    historyDeliveredIds: new Set(),
  }
  session.phoneNumber = sanitizePhoneNumber(phoneNumber) || session.phoneNumber
  session.pairingMode = 'qr'
  session.label = label || session.label || null
  session.sharedSecret = String(sharedSecret || '').trim() || session.sharedSecret || null
  session.state = 'connecting'
  session.lastError = null
  session.qrCodeDataUrl = null
  session.qrUpdatedAt = null
  session.pairingCodeRequested = false
  session.shouldReconnect = true
  ensureSessionCaches(session)
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
    syncFullHistory: true,
    markOnlineOnConnect: false,
  })
  session.socket = socket

  socket.ev.on('creds.update', saveCreds)
  socket.ev.on('messaging-history.set', async (event) => {
    const messages = Array.isArray(event?.messages) ? event.messages : []
    for (const inbound of messages) {
      const payload = buildInboundPayload(session, inbound, { syncSource: 'history' })
      if (!payload) continue
      cacheHistoryPayload(session, payload)
    }
    markSessionUpdated(session)
  })
  socket.ev.on('messages.upsert', async (event) => {
    if (!event || event.type !== 'notify') return
    const config = await fetchGatewayConfig(session).catch((error) => {
      logger.warn({ channelId, error: String(error) }, 'Failed to load WhatsApp selected groups')
      return { selected_group_ids: [] }
    })
    const selectedGroups = Array.isArray(config.selected_group_ids) ? config.selected_group_ids : []

    for (const inbound of event.messages || []) {
      const payload = buildInboundPayload(session, inbound, { syncSource: 'live' })
      if (!payload) continue
      if (selectedGroups.length === 0 || !selectedGroups.includes(payload.remote_jid)) continue

      try {
        await postInboundMessage(session, payload)
      } catch (error) {
        logger.warn({ channelId, remoteJid: payload.remote_jid, error: String(error) }, 'Failed to forward WhatsApp message to Quorum')
      }
    }
  })
  socket.ev.on('groups.upsert', (groups) => rememberGroupMetadata(session, groups || []))
  socket.ev.on('groups.update', (groups) => rememberGroupMetadata(session, groups || []))

  socket.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update
    if (qr) {
      session.state = 'qr_pending'
      session.qrCodeDataUrl = await toQrDataUrl(qr)
      session.qrUpdatedAt = nowIso()
      markSessionUpdated(session)
    }

    if (connection === 'open') {
      session.state = 'connected'
      session.connectedAt = session.connectedAt || nowIso()
      session.qrCodeDataUrl = null
      session.qrUpdatedAt = nowIso()
      session.pairingCodeRequested = false
      session.lastError = null
      session.jid = socket.user?.id || session.jid
      session.displayName = socket.user?.name || session.displayName
      session.phoneNumber = derivePhoneNumberFromJid(session.jid) || session.phoneNumber
      markSessionUpdated(session)
      try {
        const groups = await discoverGroupsForSession(session)
        await postDiscoveredGroups(session, groups)
      } catch (error) {
        logger.warn({ channelId, error: String(error) }, 'Failed to discover WhatsApp groups after connect')
      }
      return
    }

    if (connection === 'close') {
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode
      session.socket = null
      session.qrCodeDataUrl = null
      session.qrUpdatedAt = null
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
            sharedSecret: session.sharedSecret,
            label: session.label,
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
  res.json({ ok: true, sessions: sessions.size })
})

app.get('/internal/sessions/:channelId', async (req, res) => {
  const channelId = Number(req.params.channelId)
  const session = sessions.get(String(channelId))
  if (!session) {
    return res.status(404).json({ error: 'session_not_found' })
  }
  res.json(serializeSession(session))
})

app.post('/internal/sessions/connect', async (req, res) => {
  const channelId = Number(req.body?.channelId)
  if (!channelId) {
    return res.status(400).json({ error: 'channelId is required' })
  }
  try {
    const session = await startSession({
      channelId,
      sharedSecret: req.body?.sharedSecret || null,
      label: req.body?.label || null,
      pairingMode: 'qr',
    })
    res.json(serializeSession(session))
  } catch (error) {
    logger.error({ error: String(error) }, 'Failed to start Quorum WhatsApp session')
    res.status(500).json({ error: String(error) })
  }
})

app.post('/internal/sessions/:channelId/disconnect', async (req, res) => {
  const channelId = Number(req.params.channelId)
  if (!channelId) {
    return res.status(400).json({ error: 'channelId is required' })
  }
  try {
    await stopSession(channelId, {
      logout: Boolean(req.body?.logout),
      removeAuth: Boolean(req.body?.removeAuth),
    })
    res.json({ ok: true })
  } catch (error) {
    logger.error({ error: String(error) }, 'Failed to stop Quorum WhatsApp session')
    res.status(500).json({ error: String(error) })
  }
})

app.get('/internal/sessions/:channelId/groups', async (req, res) => {
  const channelId = Number(req.params.channelId)
  const session = sessions.get(String(channelId))
  if (!session?.socket || session.state !== 'connected') {
    return res.status(409).json({ error: 'session_not_connected' })
  }
  try {
    const groups = await discoverGroupsForSession(session)
    await postDiscoveredGroups(session, groups)
    res.json({ channelId, groups })
  } catch (error) {
    logger.error({ channelId, error: String(error) }, 'Failed to discover WhatsApp groups')
    res.status(500).json({ error: String(error) })
  }
})

app.post('/internal/sessions/:channelId/sync-history', async (req, res) => {
  const channelId = Number(req.params.channelId)
  const session = sessions.get(String(channelId))
  if (!session?.socket || session.state !== 'connected') {
    return res.status(409).json({ error: 'session_not_connected' })
  }
  try {
    const result = await syncSelectedGroupHistory(session)
    res.json(result)
  } catch (error) {
    logger.error({ channelId, error: String(error) }, 'Failed to sync cached WhatsApp history')
    res.status(500).json({ error: String(error) })
  }
})

app.listen(PORT, HOST, () => {
  logger.info({ host: HOST, port: PORT }, 'Quorum WhatsApp gateway listening')
})
