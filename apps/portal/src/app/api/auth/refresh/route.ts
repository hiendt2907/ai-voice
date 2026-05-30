import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get('refresh_token')?.value
  if (!refreshToken) {
    return NextResponse.json({ message: 'No refresh token' }, { status: 401 })
  }

  const apiUrl = process.env.API_INTERNAL_URL ?? 'http://localhost:3001'
  const upstream = await fetch(`${apiUrl}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refreshToken }),
  })

  if (!upstream.ok) {
    const response = NextResponse.json({ message: 'Refresh failed' }, { status: 401 })
    response.cookies.delete('access_token')
    response.cookies.delete('refresh_token')
    return response
  }

  const data = (await upstream.json()) as { accessToken: string }
  const response = NextResponse.json({ ok: true })
  response.cookies.set('access_token', data.accessToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 8,
    path: '/',
  })
  return response
}
