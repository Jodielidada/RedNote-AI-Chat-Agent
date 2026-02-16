/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      // 使用 127.0.0.1 避免 IPv6(::1) 导致代理卡住/超时
      { source: '/api/docs', destination: 'http://127.0.0.1:8000/docs' },
      { source: '/api/docs/:path*', destination: 'http://127.0.0.1:8000/docs/:path*' },
      { source: '/api/openapi.json', destination: 'http://127.0.0.1:8000/openapi.json' },
      { source: '/api/crawl', destination: 'http://127.0.0.1:8000/api/crawl' },
      { source: '/api/chat', destination: 'http://127.0.0.1:8000/api/chat' },
      { source: '/api/:path*', destination: 'http://127.0.0.1:8000/api/:path*' },
    ]
  },
}

module.exports = nextConfig
