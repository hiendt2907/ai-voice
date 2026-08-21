/**
 * Standalone WebSocket proxy for /ws/call — forwards the browser-based
 * Portal Simulator's connection to the voice worker's ClusterIP.
 *
 * Runs as a SEPARATE process/port from Next.js on purpose: Next's
 * `output: 'standalone'` build regenerates apps/portal/server.js on every
 * build via internal APIs (getRequestHandlers/next/dist/server/lib/...)
 * that aren't part of its public surface and aren't guaranteed to be
 * present in the trimmed dependency trace — wrapping them in a custom
 * server broke ("Cannot find module next/dist/compiled/webpack/webpack").
 * A plain Node `http` proxy has zero Next.js dependency, so it can't be
 * broken by that trace at all. Traefik routes /ws/call on the same host
 * to this process's port (see deploy/k8s/portal/ingress.yaml) so the
 * browser still connects same-origin as the Portal page.
 */
const http = require('http')

const port = parseInt(process.env.WS_PROXY_PORT, 10) || 3001
// ClusterIP DNS — reachable because portal and voice run in the same
// k8s namespace (not the Tailscale NodePort, which is for the Mac-side
// SIP bridge outside the cluster). Reuses the same env var other
// in-cluster callers already use (see deploy/k8s/config/configmap.yaml).
const voiceInternalUrl = process.env.VOICE_WORKER_URL || 'http://voice:8000'
// This route is reachable on the public Ingress (aivoice.asia/ws/call) so
// the browser-based Simulator can reach it same-origin — but /ws/call
// itself drives a real call (real LLM/TTS spend, no auth of its own), so
// unlike the Mac-side SIP bridge (kept Tailscale-only, never public) this
// MUST gate on the caller actually being a logged-in Portal user.
const apiInternalUrl = process.env.API_INTERNAL_URL || 'http://localhost:3001'

function extractCookie(cookieHeader, name) {
  if (!cookieHeader) return null
  for (const part of cookieHeader.split(';')) {
    const [k, ...rest] = part.trim().split('=')
    if (k === name) return decodeURIComponent(rest.join('='))
  }
  return null
}

async function isAuthenticated(req) {
  const token = extractCookie(req.headers.cookie, 'access_token')
  if (!token) return false
  try {
    const res = await fetch(`${apiInternalUrl}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    return res.ok
  } catch (err) {
    console.error('[ws-proxy] auth check failed:', err.message)
    return false
  }
}

const server = http.createServer((_req, res) => {
  res.writeHead(426, { 'Content-Type': 'text/plain' })
  res.end('This endpoint only accepts WebSocket upgrades.')
})

server.on('upgrade', async (req, clientSocket, head) => {
  // /ws/call drives a real call (real LLM/TTS spend); /ws/watch/:phone is
  // read-only fan-out of an already-running call's turn traces — both need
  // a logged-in Portal user, neither should be reachable by anyone else.
  if (!req.url || !(req.url.startsWith('/ws/call') || req.url.startsWith('/ws/watch/'))) {
    clientSocket.destroy()
    return
  }

  if (!(await isAuthenticated(req))) {
    clientSocket.write('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n')
    clientSocket.destroy()
    return
  }

  const target = new URL(req.url, voiceInternalUrl)
  const proxyReq = http.request({
    hostname: target.hostname,
    port: target.port || 80,
    path: target.pathname + target.search,
    method: req.method,
    headers: req.headers,
  })

  proxyReq.on('upgrade', (proxyRes, proxySocket, proxyHead) => {
    const headerLines = Object.entries(proxyRes.headers)
      .map(([k, v]) => `${k}: ${v}`)
      .join('\r\n')
    clientSocket.write(`HTTP/1.1 101 Switching Protocols\r\n${headerLines}\r\n\r\n`)
    if (proxyHead && proxyHead.length) proxySocket.unshift(proxyHead)
    if (head && head.length) clientSocket.unshift(head)
    proxySocket.pipe(clientSocket)
    clientSocket.pipe(proxySocket)
  })

  proxyReq.on('error', (err) => {
    console.error('[ws-proxy] upstream connect failed:', err.message)
    clientSocket.destroy()
  })
  clientSocket.on('error', () => proxyReq.destroy())

  proxyReq.end()
})

server.listen(port, '0.0.0.0', () => {
  console.log(`ws-proxy listening on :${port} -> ${voiceInternalUrl}`)
})
