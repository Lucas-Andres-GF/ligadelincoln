import type { APIRoute } from 'astro'

export const prerender = false

export const GET: APIRoute = async () => {
  if (!import.meta.env.DEV) return new Response(null, { status: 404 })
  const { readFile } = await import('node:fs/promises')
  try {
    const bulletins = JSON.parse(await readFile('.astro/boletines-preview.json', 'utf8'))
    return Response.json(bulletins, { headers: { 'Cache-Control': 'no-store' } })
  } catch (error) {
    return new Response(null, { status: (error as NodeJS.ErrnoException).code === 'ENOENT' ? 404 : 500 })
  }
}
