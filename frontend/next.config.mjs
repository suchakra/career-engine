/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Static export (10.7): the app is effectively an SPA (all client components,
  // client-side auth + data), so `next build` emits static HTML/JS to `out/`, which
  // FastAPI serves same-origin (one Cloud Run service, no CORS). `trailingSlash`
  // makes each route a `dir/index.html` that StaticFiles(html=True) serves directly.
  output: "export",
  trailingSlash: true,
  // The client talks to the FastAPI backend at NEXT_PUBLIC_API_BASE_URL (same origin
  // in the single-container image, so the default localhost:8080 is dev-only).
  eslint: {
    // Lint is run explicitly via `npm run lint` (its own step in `make frontend-check`
    // and the CI lane); skip it during `next build` so the gate doesn't lint twice.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
