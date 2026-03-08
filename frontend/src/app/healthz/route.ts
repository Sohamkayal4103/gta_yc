import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  try {
    const backendHealthUrl = new URL('/api/health', request.url).toString();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(backendHealthUrl, {
      cache: 'no-store',
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      return NextResponse.json(
        {
          status: 'degraded',
          service: 'realmcast-frontend',
          backend: { reachable: false, code: res.status },
        },
        { status: 503 },
      );
    }

    const backend = await res.json();
    return NextResponse.json({
      status: 'ok',
      service: 'realmcast-frontend',
      backend,
    });
  } catch (error: any) {
    return NextResponse.json(
      {
        status: 'degraded',
        service: 'realmcast-frontend',
        backend: { reachable: false, error: error?.message || 'unknown_error' },
      },
      { status: 503 },
    );
  }
}
