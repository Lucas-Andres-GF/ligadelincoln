import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { slugify } from "../utils/slugify";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

const CATEGORIAS = [
  { id: 1, nombre: "Primera" },
  { id: 2, nombre: "Séptima" },
  { id: 3, nombre: "Octava" },
  { id: 4, nombre: "Novena" },
  { id: 5, nombre: "Décima" },
];

function getEscudoPath(nombre) {
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
    'juventad-unida': '/escudos/juventud.unida.png',
    'juventadunida': '/escudos/juventud.unida.png',
    'juventud-unida': '/escudos/juventud.unida.png',
    'juventudunida': '/escudos/juventud.unida.png',
    'san martin': '/escudos/san.martin.png',
    'villa francia': '/escudos/villa.francia.png',
    'cael': '/escudos/el.linqueño.png',
  }
  const keyConEspacios = nombre.toLowerCase().trim()
  const keySinEspacios = nombre.toLowerCase().replace(' ', '').trim()
  return mapa[keyConEspacios] || mapa[keySinEspacios] || '/escudos/argentino.png'
}

function getInitialCategoriaId() {
  if (typeof window === 'undefined') return CATEGORIAS[0].id;
  const params = new URLSearchParams(window.location.search);
  const categoria = params.get("categoria");
  const parsed = parseInt(categoria, 10);
  if (parsed >= 1 && parsed <= 5) {
    return parsed;
  }
  return CATEGORIAS[0].id;
}

function formatearFecha(dia) {
  if (!dia) return "";
  if (dia.includes("/")) return dia;
  if (dia.includes("-")) {
    const [aa, mm, dd] = dia.split("-");
    return `${dd}/${mm}`;
  }
  return dia;
}

export default function ClubProfile({ club }) {
  const [categoriaId, setCategoriaId] = useState(getInitialCategoriaId);
  const [fixture, setFixture] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchFixture() {
      setIsLoading(true);
      const { data, error } = await supabase
        .from("partidos")
        .select(
          `fecha_id, dia, hora, goles_local, goles_visitante, estado, categoria_id, local:local_id ( id, nombre ), visitante:visitante_id ( id, nombre )`,
        )
        .or(`local_id.eq.${club.id},visitante_id.eq.${club.id}`)
        .eq("categoria_id", categoriaId)
        .order("fecha_id");
      setFixture(data || []);
      setIsLoading(false);
    }
    fetchFixture();
  }, [club.id, categoriaId]);

  return (
    <div className='max-w-2xl mx-auto'>
      <div className='flex items-center gap-5 mb-8'>
        {club.nombre && (
          <img
            src={getEscudoPath(club.nombre)}
            alt={club.nombre}
            className='w-20 h-20 object-contain'
          />
        )}
        <div>
          <h1 className='text-3xl font-extrabold text-white uppercase tracking-tight'>
            {club.nombre}
          </h1>
          <p className='text-green-500 text-sm font-medium mt-1'>
            Liga Amateur de Deportes de Lincoln
          </p>
        </div>
      </div>
      <div className='mb-6'>
        <label className='text-green-400 font-bold mr-2'>Categoría:</label>
        <select
          value={categoriaId}
          onChange={(e) => setCategoriaId(Number(e.target.value))}
          className='bg-green-950 text-green-400 border border-green-900 rounded px-2 py-1'
        >
          {CATEGORIAS.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.nombre}
            </option>
          ))}
        </select>
      </div>
      <div className='bg-[#143814] rounded-xl border border-green-900/40 overflow-hidden'>
        <div className='px-5 py-4 border-b border-green-900/40 bg-green-950/20'>
          <h2 className='text-sm font-bold uppercase tracking-wider text-green-400'>
            Fixture
          </h2>
        </div>
        <div className='divide-y divide-green-900/20'>
          {isLoading ? (
            <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
              Cargando...
            </div>
          ) : fixture.length === 0 ? (
            <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>
              No presenta la categoría seleccionada.
            </div>
          ) : (
            fixture.map((match, i) => {
              // DETECCIÓN DE LIBRE: Si no hay objeto visitante, el equipo queda libre
              const isLibre = !match.visitante;

              if (isLibre) {
                return (
                  <div
                    key={i}
                    className='flex items-center gap-3 px-5 py-3 bg-green-950/10'
                  >
                    <div className='text-[10px] text-green-700 font-bold uppercase w-14 shrink-0'>
                      <div>Fecha {match.fecha_id}</div>
                    </div>
                    <div className='flex-1 text-center'>
                      <span className='text-green-500 font-black text-xs tracking-[0.2em] uppercase'>
                        — LIBRE —
                      </span>
                    </div>
                    {/* Espacio vacío a la derecha para mantener simetría con los otros partidos */}
                    <div className='w-8 shrink-0'></div>
                  </div>
                );
              }

              const seJugo =
                match.goles_local !== null && match.goles_visitante !== null;
              const isLocal = match.local?.id === club.id;
              const rival = isLocal ? match.visitante : match.local;

              let resultado = null;
              if (seJugo) {
                const ge = isLocal ? match.goles_local : match.goles_visitante;
                const gr = isLocal ? match.goles_visitante : match.goles_local;
                if (ge > gr) resultado = "W";
                else if (ge === gr) resultado = "D";
                else resultado = "L";
              }

              const rowBg = {
                W: "bg-green-500/10",
                D: "bg-yellow-500/5",
                L: "bg-red-500/5",
              };

              return (
                <div
                  key={i}
                  className={`flex items-center gap-3 px-5 py-3 ${resultado ? rowBg[resultado] : ""}`}
                >
                  <div className='text-[10px] text-green-700 font-bold uppercase w-14 shrink-0'>
                    <div>Fecha {match.fecha_id}</div>
                    {match.dia && (
                      <div className='text-green-800 font-normal'>
                        {formatearFecha(match.dia)}
                      </div>
                    )}
                  </div>
                  <div className='text-[10px] text-green-600 font-bold w-8 shrink-0 text-center'>
                    {isLocal ? "LOC" : "VIS"}
                  </div>
                  <a
                    href={`/club/${slugify(rival?.nombre || "")}`}
                    className='flex items-center gap-2 flex-1 min-w-0 hover:opacity-80 transition-opacity'
                  >
                    {rival?.nombre && (
                      <img
                        src={getEscudoPath(rival.nombre)}
                        alt={rival.nombre}
                        className='w-5 h-5 object-contain shrink-0'
                      />
                    )}
                    <span className='text-green-100 font-semibold text-xs truncate'>
                      {rival?.nombre}
                    </span>
                  </a>
                  <div className='shrink-0 text-right'>
                    {seJugo ? (
                      <span className='font-black text-sm text-green-400'>
                        {match.goles_local} - {match.goles_visitante}
                      </span>
                    ) : (
                      <span className='text-green-700 text-xs font-medium'>
                        Próximo
                      </span>
                    )}
                  </div>
                  {resultado && (
                    <div
                      className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-black shrink-0 ${resultado === "W" ? "bg-green-500 text-black" : resultado === "D" ? "bg-yellow-500 text-black" : "bg-red-500 text-white"}`}
                    >
                      {resultado === "W" ? "G" : resultado === "D" ? "E" : "P"}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
      <div className='mt-6 text-center'>
        <a
          href='/'
          className='text-green-500 hover:text-green-400 text-sm font-medium transition-colors'
        >
          ← Volver al inicio
        </a>
      </div>
    </div>
  );
}
