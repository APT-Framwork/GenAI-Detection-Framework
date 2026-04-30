// Server-side auth gate. Runs before any matched page renders, so
// unauthenticated users never see dashboard markup.
//
// We check for `strix_access` — it's path=/ so the middleware can see it.
// `strix_refresh` is path=/api/v1/auth/refresh so it isn't visible here.
// `strix_csrf` is path=/ and lives as long as the refresh token (7d), so
// it's a useful belt-and-braces "session was opened" marker for cases
// where strix_access has expired but the user still has a valid refresh.
// The SPA's apiFetch handles silent /auth/refresh on 401, so once past
// the gate the session keeps itself alive.

import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

const PUBLIC_ROUTES = new Set<string>([
  "/login",
  "/register",
])

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl

  if (PUBLIC_ROUTES.has(pathname)) {
    return NextResponse.next()
  }

  const access = req.cookies.get("strix_access")?.value
  const csrf = req.cookies.get("strix_csrf")?.value
  if (access || csrf) {
    return NextResponse.next()
  }

  const loginUrl = req.nextUrl.clone()
  loginUrl.pathname = "/login"
  loginUrl.search = ""
  if (pathname !== "/") {
    loginUrl.searchParams.set("next", pathname + (search ?? ""))
  }
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: [
    // Match everything except: Next.js internals, the API proxy path
    // (/api/v1/* is rewritten to FastAPI — must not be gated here), static
    // assets, and the login/register pages (also handled inside middleware
    // as belt-and-braces).
    "/((?!api/|_next/|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
}
