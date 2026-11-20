export function sortOfficialScorers(rows) {
  return [...rows].sort((a, b) => (
    b.goles - a.goles
    || a.club.localeCompare(b.club, 'es', { sensitivity: 'base' })
    || a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' })
  ))
}
