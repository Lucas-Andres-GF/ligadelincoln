import type { APIRoute } from 'astro'

export const prerender = false

export const GET: APIRoute = async () => {
  if (!import.meta.env.DEV) return new Response(null, { status: 404 })

  const { readFile } = await import('node:fs/promises')
  try {
    const rows = await readFile('.astro/campeones-preview.json', 'utf8')
    return new Response(rows, {
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    })
  } catch (error) {
    return new Response(null, {
      status: (error as NodeJS.ErrnoException).code === 'ENOENT' ? 404 : 500,
    })
  }
}
