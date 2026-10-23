/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    // Optional dev proxy: /api -> backend, so the UI can also run same-origin.
    const api = process.env.API_PROXY_TARGET;
    if (!api) return [];
    return [{ source: "/backend/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
