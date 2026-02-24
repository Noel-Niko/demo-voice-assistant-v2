/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Following 12-factor: config from environment
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8765',
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8765',
  },
  // Turbopack config (Next.js 16 default)
  turbopack: {},
  // Dev indicators configuration
  devIndicators: {
    buildActivity: true,
    buildActivityPosition: 'bottom-right',
  },
}

module.exports = nextConfig
