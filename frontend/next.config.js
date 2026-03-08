/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
      {
        source: '/uploads/:path*',
        destination: 'http://localhost:8000/uploads/:path*',
      },
      {
        source: '/static/games/:path*',
        destination: 'http://localhost:8000/static/games/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
