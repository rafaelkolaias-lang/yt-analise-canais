import { NextRequest, NextResponse } from "next/server";

/**
 * Guard de autenticação das PÁGINAS (a API tem o guard próprio no backend).
 *
 * Sem cookie `auth_token` → redireciona pra /login. O cookie só diz "há uma
 * sessão salva" — a validade real é checada pela API em toda request (401
 * derruba pro /login via lib/api).
 */
export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasToken = Boolean(req.cookies.get("auth_token")?.value);

  if (pathname === "/login") {
    // Já logado? Vai direto pro dashboard.
    if (hasToken) {
      return NextResponse.redirect(new URL("/", req.url));
    }
    return NextResponse.next();
  }

  if (!hasToken) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}

export const config = {
  // Tudo exceto assets estáticos do Next e favicon.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.png$).*)"],
};
