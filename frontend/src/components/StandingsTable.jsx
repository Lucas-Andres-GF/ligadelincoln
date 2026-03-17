import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { slugify } from "../utils/slugify";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

export default function StandingsTable({
  categoriaId = 1,
  showUltimos5 = true,
}) {
  const [standings, setStandings] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function getStandingsData() {
      const { data, error } = await supabase
        .from("posiciones")
        .select(
          `pts, pj, pg, pe, pp, gf, gc, dif, ultimos_5, clubes ( nombre, escudo_url )`,
        )
        .eq("categoria_id", categoriaId)
        .order("pts", { ascending: false })
        .order("dif", { ascending: false });

      if (error) {
        console.error("Supabase error:", error);
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

  return (
    <div className='w-full overflow-hidden text-xs'>
      <table className='w-full border-collapse'>
        <thead>
          <tr className='text-green-500/50 border-b border-green-900/30 uppercase italic'>
            <th className='py-2 text-left px-2'>Club</th>
            <th className='py-2 px-3 text-center text-green-400 font-bold'>
              PTS
            </th>
            <th className='py-2 px-3 text-center'>PJ</th>
            <th className='py-2 px-3 text-center'>PG</th>
            <th className='py-2 px-3 text-center'>PE</th>
            <th className='py-2 px-3 text-center'>PP</th>
            <th className='py-2 px-3 text-center'>GF</th>
            <th className='py-2 px-3 text-center'>GC</th>
            <th className='py-2 px-3 text-center'>DIF</th>
            {showUltimos5 && <th className='py-2 px-3 text-center'>Últ. 5</th>}
          </tr>
        </thead>
        <tbody className='divide-y divide-green-900/20'>
          {standings.map((row, index) => (
            <tr
              key={index}
              className='hover:bg-green-400/5 transition-colors group'
            >
              <td className='py-3 px-2 font-bold text-green-100'>
                <a
                  href={`/club/${slugify(row.clubes?.nombre || "")}`}
                  className='flex items-center gap-2 hover:opacity-80 transition-opacity'
                >
                  <span className='text-[10px] text-green-700 w-3'>
                    {index + 1}
                  </span>
                  {row.clubes?.escudo_url && (
                    <img
                      src={row.clubes.escudo_url}
                      alt={row.clubes.nombre}
                      className='w-5 h-5 object-contain'
                    />
                  )}
                  <span className='truncate'>{row.clubes?.nombre}</span>
                </a>
              </td>
              <td className='py-3 px-3 text-center font-black text-green-400'>
                {row.pts}
              </td>
              <td className='py-3 px-3 text-center text-green-400/60'>
                {row.pj}
              </td>
              <td className='py-3 px-3 text-center text-green-400/60'>
                {row.pg}
              </td>
              <td className='py-3 px-3 text-center text-green-400/60'>
                {row.pe}
              </td>
              <td className='py-3 px-3 text-center text-green-400/60'>
                {row.pp}
              </td>
              <td className='py-3 px-3 text-center text-green-400/60'>
                {row.gf}
              </td>
              <td className='py-3 px-3 text-center text-green-400/60'>
                {row.gc}
              </td>
              <td className='py-3 px-3 text-center text-green-400/60'>
                {row.dif}
              </td>
              {showUltimos5 && (
                <td className='py-3 px-3 text-center text-green-400/60'>
                  {row.ultimos_5 || "-"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
