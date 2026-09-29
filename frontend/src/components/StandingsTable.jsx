import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { cachedQuery } from "../utils/supabaseCached";
import { slugify } from "../utils/slugify";
import { getSelectedTorneoId, listenToTorneoChange, parseTorneoId, withTorneoParam } from "../utils/torneoSelection";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

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

export default function StandingsTable({
  categoriaId = 1,
  showUltimos5 = true,
  torneoId = null,
}) {
  const [standings, setStandings] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedTorneoId, setSelectedTorneoId] = useState(() => getSelectedTorneoId(torneoId));

  useEffect(() => listenToTorneoChange(setSelectedTorneoId), []);

  useEffect(() => {
    let cancelled = false;

    async function getStandingsData() {
      setStandings([]);
      setError(null);
      const scopedTorneoId = parseTorneoId(selectedTorneoId);
      if (scopedTorneoId === null) {
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      const cacheKey = `standings_torneo_${scopedTorneoId}_categoria_${categoriaId}`
      const { data, error: standingsError } = await cachedQuery(cacheKey, () =>
        supabase
          .from("posiciones")
          .select(
            `pts, pj, pg, pe, pp, gf, gc, dif, ultimos_5, clubes ( nombre )`,
          )
          .eq("categoria_id", categoriaId)
          .eq("torneo_id", scopedTorneoId)
          .order("pts", { ascending: false })
          .order("dif", { ascending: false })
      )

      if (cancelled) return;
      if (standingsError) {
        console.error("Supabase error:", standingsError);
        setError("No se pudo cargar la tabla de posiciones.");
      } else {
        setStandings(data || []);
      }
      setIsLoading(false);
    }
    getStandingsData();
    return () => {
      cancelled = true;
    };
  }, [categoriaId, selectedTorneoId]);

  if (parseTorneoId(selectedTorneoId) === null)
    return (
      <div className='text-center py-8 text-yellow-200 text-xs uppercase tracking-widest' role='status'>
        Seleccioná un torneo válido para ver la tabla.
      </div>
    );

  if (isLoading)
    return (
      <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
        Cargando posiciones...
      </div>
    );

  if (error)
    return (
      <div className='text-center py-8 text-red-300 text-xs font-semibold' role='alert'>
        {error}
      </div>
    );

  if (!standings || standings.length === 0)
    return (
      <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>
        No hay posiciones disponibles
      </div>
    );

  return (
    <div className='relative'>
      <div className='w-full overflow-x-auto rounded-xl border border-green-800/55 bg-green-950/20 text-xs'>
        <table className='w-full min-w-[620px] border-collapse'>
        <thead>
          <tr className='border-b border-green-800/60 bg-[#092716] font-[var(--font-display)] text-[10px] font-bold uppercase tracking-[0.12em] text-green-600'>
            <th className='px-3 py-2.5 text-left'>Posición / club</th>
            <th className='px-2 py-2.5 text-center text-yellow-200'>PTS</th>
            <th className='px-2 py-2.5 text-center'>PJ</th>
            <th className='px-2 py-2.5 text-center'>PG</th>
            <th className='px-2 py-2.5 text-center'>PE</th>
            <th className='px-2 py-2.5 text-center'>PP</th>
            <th className='px-2 py-2.5 text-center'>GF</th>
            <th className='px-2 py-2.5 text-center'>GC</th>
            <th className='px-2 py-2.5 text-center'>DIF</th>
            {showUltimos5 && <th className='px-3 py-2.5 text-center'>Forma</th>}
          </tr>
        </thead>
        <tbody className='divide-y divide-green-800/45'>
          {standings.map((row, index) => (
            <tr
              key={index}
              className={`group transition-colors hover:bg-green-400/[0.055] ${index === 0 ? 'bg-yellow-300/[0.035]' : ''}`}
            >
              <td className='px-3 py-2.5 font-bold text-green-100'>
                <a
                  href={withTorneoParam(`/club/${slugify(row.clubes?.nombre || "")}?categoria=${categoriaId}`, selectedTorneoId)}
                  className='flex items-center gap-2 transition-opacity hover:opacity-80'
                >
                  <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-md font-[var(--font-display)] text-xs font-black ${index === 0 ? 'bg-yellow-300 text-[#082310]' : index < 3 ? 'bg-green-400/15 text-green-300' : 'bg-black/10 text-green-600'}`}>
                    {index + 1}
                  </span>
                  {row.clubes?.nombre && (
                      <img
                        src={getEscudoPath(row.clubes.nombre)}
                        alt={row.clubes.nombre}
                        className="h-7 w-7 object-contain"
                      />
                  )}
                  <span className='truncate text-[11px] font-extrabold sm:text-xs'>{row.clubes?.nombre}</span>
                </a>
              </td>
              <td className='px-2 py-2.5 text-center font-[var(--font-display)] text-base font-black text-yellow-100'>
                {row.pts}
              </td>
              <td className='px-2 py-2.5 text-center text-[10px] font-semibold text-green-300/70'>
                {row.pj}
              </td>
              <td className='px-2 py-2.5 text-center text-[10px] font-semibold text-green-300/70'>
                {row.pg}
              </td>
              <td className='px-2 py-2.5 text-center text-[10px] font-semibold text-green-300/70'>
                {row.pe}
              </td>
              <td className='px-2 py-2.5 text-center text-[10px] font-semibold text-green-300/70'>
                {row.pp}
              </td>
              <td className='px-2 py-2.5 text-center text-[10px] font-semibold text-green-300/70'>
                {row.gf}
              </td>
              <td className='px-2 py-2.5 text-center text-[10px] font-semibold text-green-300/70'>
                {row.gc}
              </td>
              <td className='px-2 py-2.5 text-center text-[10px] font-bold text-green-100'>
                {row.dif}
              </td>
              {showUltimos5 && (
                <td className='px-3 py-2.5 text-center'>
                  <div className='flex items-center justify-center gap-0.5'>
                    {(() => {
                      const ult = row.ultimos_5;
                      if (!ult) return <span className='text-green-700/50'>-</span>;
                      const arr = typeof ult === 'string' ? JSON.parse(ult) : ult;
                      if (!Array.isArray(arr) || arr.length === 0) return <span className='text-green-700/50'>-</span>;
                      // Invertir para mostrar el más reciente a la izquierda
                      const arrInvertido = [...arr].reverse();
                      return arrInvertido.map((r, i) => (
                        <span
                          key={i}
                          className={`flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-black ${
                            r === 'G'
                              ? 'bg-green-500/20 text-green-400'
                              : r === 'P'
                              ? 'bg-red-500/20 text-red-400'
                              : 'bg-yellow-500/20 text-yellow-400'
                          }`}
                        >
                          {r}
                        </span>
                      ));
                    })()}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className='pointer-events-none absolute bottom-0 right-0 top-0 flex w-10 items-center justify-end bg-gradient-to-l from-[#0b2e1a] to-transparent pr-2 md:hidden'>
        <svg className='w-4 h-4 text-green-600 animate-pulse' fill='none' viewBox='0 0 24 24' stroke='currentColor'>
          <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M9 5l7 7-7 7' />
        </svg>
      </div>
    </div>
  );
}
