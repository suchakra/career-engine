/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The App Router client talks to the FastAPI backend at NEXT_PUBLIC_API_BASE_URL;
  // no rewrites/proxy here (CORS is wired in slice 10.7).
  eslint: {
    // Lint is run explicitly via `npm run lint` (its own step in `make frontend-check`
    // and the CI lane); skip it during `next build` so the gate doesn't lint twice.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
