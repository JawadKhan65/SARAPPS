/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // API URL will be injected at build time via NEXT_PUBLIC_API_URL
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '/api',
  },
  // Optional: If you want to deploy admin under /admin path
  // basePath: '/admin',
  // assetPrefix: '/admin',
}

module.exports = nextConfig

