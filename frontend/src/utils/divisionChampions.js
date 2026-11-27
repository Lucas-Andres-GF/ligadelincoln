import { supabase } from './supabase'

export async function fetchDivisionChampions({ torneoId = null, categoriaId = null } = {}) {
  const { data, error } = await supabase.rpc('campeones_de_torneo', {
    p_torneo_id: torneoId,
    p_categoria_id: categoriaId,
  })
  if (!error) return data ?? []
  if (error.code !== 'PGRST202') throw error

  let query = supabase.from('palmares')
    .select('nombre,temporada,club_id,torneo_id,categoria_id,club:club_id(nombre)')
  if (torneoId !== null) query = query.eq('torneo_id', torneoId)
  if (categoriaId !== null) query = query.eq('categoria_id', categoriaId)
  const { data: stored, error: storedError } = await query
  if (storedError) throw storedError
  const history = (stored ?? []).map(({ club, ...row }) => ({
    ...row, club_nombre: club?.nombre, torneo_nombre: row.nombre, tipo: 'oficial',
  })).filter((row) => row.club_nombre)

  if (!import.meta.env.DEV) return history

  const preview = await fetch('/api/campeones-preview')
  if (preview.status === 404) return history
  if (!preview.ok) throw new Error('No se pudo leer la vista local de campeones.')

  const savedGroups = new Set(history.map((row) => `${row.torneo_id}:${row.categoria_id}`))
  const previewRows = (await preview.json()).filter((row) => (
    (torneoId === null || row.torneo_id === torneoId)
    && (categoriaId === null || row.categoria_id === categoriaId)
    && !savedGroups.has(`${row.torneo_id}:${row.categoria_id}`)
  ))
  return [...history, ...previewRows]
}
