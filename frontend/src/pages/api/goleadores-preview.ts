import type { APIRoute } from 'astro'

export const prerender = false

export const GET: APIRoute = async ({ url }) => {
  if (!import.meta.env.DEV) return new Response(null, { status: 404 })

  const { readFile } = await import('node:fs/promises')
  try {
    const report = JSON.parse(await readFile('.astro/goleadores-preview.json', 'utf8'))
    if (String(report.torneo_id) !== url.searchParams.get('torneo')) {
      return new Response(null, { status: 404 })
    }
    const category = Number(url.searchParams.get('categoria'))
    const filas = report.filas.filter((row: { categoria_id: number }) => row.categoria_id === category)
    return Response.json({ emitido_en: report.emitido_en, filas }, { headers: { 'Cache-Control': 'no-store' } })
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
      return new Response(null, { status: 404 })
    }
    return new Response(null, { status: 500 })
  }
}
