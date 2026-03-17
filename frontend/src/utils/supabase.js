import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

export const supabase = supabase;

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
      local:local_id ( nombre, escudo_url ),
      visitante:visitante_id ( nombre, escudo_url )
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
