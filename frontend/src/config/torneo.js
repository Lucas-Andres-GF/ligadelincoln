import { parseTorneoId } from '../utils/torneoSelection'

export const ACTIVE_TORNEO_ID = parseTorneoId(
  import.meta.env.PUBLIC_ACTIVE_TORNEO_ID,
)

export const ACTIVE_TORNEO_NAME =
  import.meta.env.PUBLIC_ACTIVE_TORNEO_NAME || null
