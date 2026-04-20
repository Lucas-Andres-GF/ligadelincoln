import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { cachedQuery } from "../utils/supabaseCached";
import { slugify } from "../utils/slugify";

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
}) {
  const [standings, setStandings] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function getStandingsData() {
      const cacheKey = `standings_categoria_${categoriaId}`
      
      const { data, error } = await cachedQuery(cacheKey, () =>
        supabase
          .from("posiciones")
          .select(
            `pts, pj, pg, pe, pp, gf, gc, dif, ultimos_5, clubes ( nombre )`,
          )
          .eq("categoria_id", categoriaId)
          .order("pts", { ascending: false })
          .order("dif", { ascending: false })
      )

      if (error) {
        console.error("Supabase error:", error);
        setStandings([]);
      } else {
        setStandings(data || []);
      }
      setIsLoading(false);
    }
    getStandingsData();
  }, [categoriaId]);

  if (isLoading)
    return (
      <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
        Cargando...
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
      <div className='w-full overflow-x-auto text-xs'>
        <table className='w-full border-collapse min-w-[500px]'>
        <thead>
          <tr className='text-green-500/50 border-b border-green-900/30 uppercase italic'>
            <th className='py-1 text-left px-1'>Club</th>
            <th className='py-1 px-1 text-center text-green-400 font-bold'>PTS</th>
            <th className='py-1 px-1 text-center'>PJ</th>
            <th className='py-1 px-1 text-center'>PG</th>
            <th className='py-1 px-1 text-center'>PE</th>
            <th className='py-1 px-1 text-center'>PP</th>
            <th className='py-1 px-1 text-center'>GF</th>
            <th className='py-1 px-1 text-center'>GC</th>
            <th className='py-1 px-1 text-center'>DIF</th>
            {showUltimos5 && <th className='py-1 px-1 text-center'>Últ. 5</th>}
          </tr>
        </thead>
        <tbody className='divide-y divide-green-900/20'>
          {standings.map((row, index) => (
            <tr
              key={index}
              className='hover:bg-green-400/5 transition-colors group'
            >
              <td className='py-2 px-1 font-bold text-green-100'>
                <a
                  href={`/club/${slugify(row.clubes?.nombre || "")}?categoria=${categoriaId}`}
                  className='flex items-center gap-1 hover:opacity-80 transition-opacity'
                >
                  <span className='text-[9px] text-green-700 w-3'>
                    {index + 1}
                  </span>
                  {row.clubes?.nombre && (
                      <img
                        src={getEscudoPath(row.clubes.nombre)}
                        alt={row.clubes.nombre}
                        className="w-5 h-5 object-contain"
                      />
                  )}
                  <span className='truncate text-[10px]'>{row.clubes?.nombre}</span>
                </a>
              </td>
              <td className='py-2 px-1 text-center font-black text-green-400 text-[10px]'>
                {row.pts}
              </td>
              <td className='py-2 px-1 text-center text-green-400/60 text-[10px]'>
                {row.pj}
              </td>
              <td className='py-2 px-1 text-center text-green-400/60 text-[10px]'>
                {row.pg}
              </td>
              <td className='py-2 px-1 text-center text-green-400/60 text-[10px]'>
                {row.pe}
              </td>
              <td className='py-2 px-1 text-center text-green-400/60 text-[10px]'>
                {row.pp}
              </td>
              <td className='py-2 px-1 text-center text-green-400/60 text-[10px]'>
                {row.gf}
              </td>
              <td className='py-2 px-1 text-center text-green-400/60 text-[10px]'>
                {row.gc}
              </td>
              <td className='py-2 px-1 text-center text-green-400/60 text-[10px]'>
                {row.dif}
              </td>
              {showUltimos5 && (
                <td className='py-3 px-3 text-center'>
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
                          className={`w-4 h-4 flex items-center justify-center rounded text-[10px] font-bold ${
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
      <div className='pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-[#0f2d0f] to-transparent md:hidden flex items-center justify-end pr-2'>
        <svg className='w-4 h-4 text-green-600 animate-pulse' fill='none' viewBox='0 0 24 24' stroke='currentColor'>
          <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M9 5l7 7-7 7' />
        </svg>
      </div>
    </div>
  );
}
