import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
  const body = await req.json() as { email: string; password: string }
  const apiUrl = process.env.API_INTERNAL_URL ?? 'http://localhost:3001'

  const upstream = await fetch(`${apiUrl}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const data = await upstream.json() as { accessToken?: string; refreshToken?: string; user?: unknown; message?: string }

  if (!upstream.ok) {
    return NextResponse.json({ message: data.message ?? 'Sai email hoặc mật khẩu' }, { status: upstream.status })
  }

  const response = NextResponse.json({ user: data.user })
  response.cookies.set('access_token', data.accessToken!, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 8,
    path: '/',
  })
  if (data.refreshToken) {
    response.cookies.set('refresh_token', data.refreshToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 7,
      path: '/',
    })
  }
  return response
}
