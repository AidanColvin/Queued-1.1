/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export for zero-config Vercel hosting (Screen 1/2 are client-rendered
  // and talk to the backend at runtime via NEXT_PUBLIC_API_URL).
  output: 'export',
  reactStrictMode: true,
  // next/export cannot run the image optimizer, so serve images as-is.
  images: { unoptimized: true },
  trailingSlash: true,
};

module.exports = nextConfig;
