/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // In dev, proxy /api/v1/* to the FastAPI on :8000 so the browser stays
  // same-origin (no CORS, httpOnly cookies just work). In prod, an upstream
  // ingress (nginx, traefik, vercel rewrite, etc.) is expected to do the
  // same job — set NEXT_PUBLIC_STRIX_API_BASE if you don't want a rewrite.
  async rewrites() {
    const apiUrl = process.env.STRIX_API_URL || "http://localhost:8000";
    return [
      { source: "/api/v1/:path*", destination: `${apiUrl}/api/v1/:path*` },
    ];
  },
}

module.exports = nextConfig
