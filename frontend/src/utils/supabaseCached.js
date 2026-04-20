import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY

// Crear cliente base
export const supabase = createClient(supabaseUrl, supabaseKey)

// Cache simple en memoria (se limpia al navegar)
const memoryCache = new Map()
const CACHE_TTL = 5 * 60 * 1000 // 5 minutos

/**
 * Query wrapper con caché en memoria
 * @param {string} key - Clave única para cachear
 * @param {Function} queryFn - Función que retorna la query de Supabase
 * @returns {Promise} Resultado de la query
 */
export async function cachedQuery(key, queryFn) {
  const now = Date.now()
  const cached = memoryCache.get(key)

  if (cached && (now - cached.timestamp < CACHE_TTL)) {
    return cached.data
  }

  const result = await queryFn()

  if (!result.error) {
    memoryCache.set(key, {
      data: result,
      timestamp: now,
    })
  }

  return result
}

/**
 * Invalida el caché completamente
 */
export function clearCache() {
  memoryCache.clear()
}

/**
 * Invalida una clave específica del caché
 * @param {string} key - Clave a invalidar
 */
export function invalidateCache(key) {
  memoryCache.delete(key)
}

/**
 * Invalida todas las queries relacionadas con una categoría
 * @param {number} categoriaId - ID de la categoría
 */
export function invalidateCategoriaCache(categoriaId) {
  for (const key of memoryCache.keys()) {
    if (key.includes(`categoria_${categoriaId}`)) {
      memoryCache.delete(key)
    }
  }
}