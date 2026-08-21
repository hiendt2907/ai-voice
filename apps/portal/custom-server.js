/**
 * Custom server wrapping Next's standalone output to add a raw WebSocket
 * proxy for /ws/call. The Simulator page runs in the visitor's browser and
 * cannot reach the voice worker's ClusterIP directly — Portal and voice run
 * in the same cluster, so this server (which already does) forwards the
 * upgrade to voice's internal Service, letting the browser connect to the
 * same origin as the Portal page (wss://<portal-domain>/ws/call) instead of
 * needing voice exposed anywhere.
 *
 * No new dependencies — pure Node core `http`, manually replaying the
 * upgrade handshake and piping the two sockets together.
 *
 * Deployed alongside (not replacing) Next's auto-generated server.js — see
 * Dockerfile: this file is copied in as an extra file and run via CMD
 * instead, since `.next/standalone` output regenerates server.js on every
 * build and would silently discard any edits made to it directly.
 */
const path = require('path')
const http = require('http')
const next = require('next')

const dir = path.join(__dirname)
process.env.NODE_ENV = 'production'

const port = parseInt(process.env.PORT, 10) || 3000
const hostname = process.env.HOSTNAME || '0.0.0.0'
// ClusterIP DNS — reachable because portal and voice run in the same
// k8s namespace. Not the Tailscale NodePort (that's for the Mac-side SIP
// bridge, which is outside the cluster); this is an in-cluster hop.
const voiceInternalUrl = process.env.VOICE_INTERNAL_URL || 'http://voice:8000'

const app = next({ dev: false, dir })
const handle = app.getRequestHandler()

app.prepare().then(() => {
  const server = http.createServer((req, res) => handle(req, res))

  server.on('upgrade', (req, clientSocket, head) => {
    if (!req.url || !req.url.startsWith('/ws/call')) {
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

  server.listen(port, hostname, () => {
    console.log(`Portal (custom server, ws-proxy enabled) ready on http://${hostname}:${port}`)
  })
}).catch((err) => {
  console.error(err)
  process.exit(1)
})
