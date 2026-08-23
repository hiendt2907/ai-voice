import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const AUTH_ROUTES = ['/api/auth/login', '/api/auth/logout']

// Nguồn chân lý cho "role nào được xem trang nào" — PHẢI khớp với bảng NAV
// trong apps/portal/src/components/AppSidebar.tsx (dòng ~31-44). Route không
// có trong danh sách này (vd. /dashboard, /reports, /guide) = mọi role đã
// đăng nhập đều xem được, giống hành vi mặc định của NAV khi không set `roles`.
const ROUTE_ROLES: { prefix: string; roles: string[] }[] = [
  { prefix: '/scripts', roles: ['admin', 'operator'] },
  { prefix: '/knowledge', roles: ['admin', 'operator'] },
  { prefix: '/nlu', roles: ['admin', 'operator'] },
  { prefix: '/calls', roles: ['admin', 'operator', 'qa'] },
  { prefix: '/qa', roles: ['admin', 'qa'] },
  { prefix: '/learning', roles: ['admin', 'qa'] },
  { prefix: '/audit', roles: ['admin'] },
  { prefix: '/simulator', roles: ['admin', 'operator'] },
  { prefix: '/settings', roles: ['admin'] },
]

// Trang mặc định mà mọi role đã đăng nhập đều xem được — dùng làm điểm đến
// khi một route bị chặn theo role, để tránh vòng lặp redirect (không bao giờ
// được nằm trong ROUTE_ROLES ở trên).
const FALLBACK_ROUTE = '/dashboard'

function matchRouteRoles(pathname: string): string[] | null {
  // So khớp prefix dài nhất trước (vd. '/knowledge/test' phải khớp
  // '/knowledge' đúng như NAV, không có prefix con nào chi tiết hơn ở đây).
  const match = ROUTE_ROLES.filter(
    (r) => pathname === r.prefix || pathname.startsWith(`${r.prefix}/`),
  ).sort((a, b) => b.prefix.length - a.prefix.length)[0]
  return match ? match.roles : null
}

/**
 * Đọc role từ payload JWT mà KHÔNG xác minh chữ ký.
 *
 * HẠN CHẾ QUAN TRỌNG: middleware chạy ở Next.js Edge runtime. Thư viện
 * `jose` (đã có trong package.json, tương thích Edge) có thể verify chữ ký
 * HS256 thật sự, nhưng để làm vậy middleware cần đọc được JWT_SECRET — biến
 * này hiện chỉ được cấp cho pod API (apps/api), KHÔNG có trong cấu hình
 * deploy của Portal, và việc thêm nó đòi hỏi sửa deploy/k8s/portal — nằm
 * ngoài phạm vi file được phép sửa của thay đổi này. Vì vậy hàm này chỉ
 * decode phần payload (base64url) để đọc trường `role` cho mục đích ẩn/hiện
 * UI và điều hướng sớm — đây KHÔNG phải là một lớp bảo mật thật.
 *
 * Chốt chặn an ninh THẬT nằm ở tầng API: RolesGuard (apps/api/src/auth/guards/
 * roles.guard.ts) xác minh chữ ký JWT qua JwtAuthGuard trước, rồi mới kiểm
 * tra role — mọi request dữ liệu thật đều phải đi qua đó. Middleware này chỉ
 * là lớp UX (né việc hiện trang trống/vòng xoay loading rồi mới bị 403 từ
 * API), một token bị sửa tay vẫn sẽ bị API chặn dù qua được middleware.
 */
function decodeRoleUnverified(token: string): string | null {
  try {
    const [, payloadB64] = token.split('.')
    if (!payloadB64) return null
    // base64url → base64
    const normalized = payloadB64.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=')
    const json = atob(padded)
    const payload = JSON.parse(json) as { role?: unknown }
    return typeof payload.role === 'string' ? payload.role : null
  } catch {
    return null
  }
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const token = request.cookies.get('access_token')?.value

  // For NestJS proxy calls: inject Bearer from httpOnly cookie
  if (pathname.startsWith('/api/') && !AUTH_ROUTES.some((r) => pathname.startsWith(r))) {
    if (!token) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }
    const headers = new Headers(request.headers)
    headers.set('Authorization', `Bearer ${token}`)
    return NextResponse.next({ request: { headers } })
  }

  // Redirect to dashboard if already logged in
  if (token && pathname === '/login') {
    return NextResponse.redirect(new URL('/dashboard', request.url))
  }

  // Protect all non-login, non-api page routes
  if (!token && !pathname.startsWith('/login') && !pathname.startsWith('/api/')) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  // Kiểm tra role cho các trang giới hạn theo NAV (xem ROUTE_ROLES ở trên).
  // Chỉ có ý nghĩa UX — chốt chặn thật nằm ở RolesGuard phía API, xem docstring
  // của decodeRoleUnverified().
  if (token && pathname !== FALLBACK_ROUTE) {
    const requiredRoles = matchRouteRoles(pathname)
    if (requiredRoles) {
      const role = decodeRoleUnverified(token)
      if (!role || !requiredRoles.includes(role)) {
        // FALLBACK_ROUTE không nằm trong ROUTE_ROLES nên nhánh này không thể
        // tự redirect vào chính nó — tránh vòng lặp redirect.
        return NextResponse.redirect(new URL(FALLBACK_ROUTE, request.url))
      }
    }
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
