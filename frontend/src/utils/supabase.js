import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

export const supabase = supabase;

export function getEscudoPath(nombre) {
  if (!nombre) return '/escudos/argentino.png'
  const mapa = {
    'argentino': '/escudos/argentino.png',
    'atl. pasteur': '/escudos/atl.pasteur.png',
    'atl. roberts': '/escudos/atl.roberts.png',
    'ca. pintense': '/escudos/ca.pintense.png',
    'c a pintense': '/escudos/ca.pintense.png',
    'ca pintense': '/escudos/ca.pintense.png',
    'pintense': '/escudos/ca.pintense.png',
    'caset': '/escudos/caset.png',
    'dep. arenaza': '/escudos/dep.arenaza.png',
    'dep. gral pinto': '/escudos/dep.pinto.png',
    'dep gral pinto': '/escudos/dep.pinto.png',
    'el linqueño': '/escudos/el.linqueño.png',
    'juventud-unida': '/escudos/juventud.unida.png',
    'juventudunida': '/escudos/juventud.unida.png',
    'san martin': '/escudos/san.martin.png',
    'villa francia': '/escudos/villa.francia.png',
    'cael': '/escudos/el.linqueño.png',
  }
  const key = nombre.toLowerCase().trim()
  return mapa[key] || '/escudos/argentino.png'
}

export async function getPartidos(categoria) {
  const { data, error } = await supabase
    .from("partidos")
    .select(`
      id,
      fecha_id,
      dia,
      hora,
      goles_local,
      goles_visitante,
      estado,
      arbitro,
      cancha,
      observaciones,
      categoria,
      local_id,
      visitante_id,
      local:local_id ( nombre ),
      visitante:visitante_id ( nombre )
    `)
    .eq("categoria", categoria)
    .order("fecha_id")
    .order("id");

  if (error) throw error;
  return data;
}

export async function updatePartido(id, updates) {
  const { data, error } = await supabase
    .from("partidos")
    .update(updates)
    .eq("id", id)
    .select()
    .single();

  if (error) throw error;
  return data;
}

export async function getCategorias() {
  const { data, error } = await supabase
    .from("partidos")
    .select("categoria")
    .order("categoria");

  if (error) throw error;
  return [...new Set(data.map(p => p.categoria))];
}
