import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
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
    'juventud-unida': '/escudos/juventud.unida.png',
    'san martin': '/escudos/san.martin.png',
    'villa francia': '/escudos/villa.francia.png',
    'cael': '/escudos/el.linqueño.png',
  }
  const key = nombre.toLowerCase().trim()
  return mapa[key] || '/escudos/argentino.png'
}

export default function TeamProfile({ equipo }) {
  const [matches, setMatches] = useState([]);
  const [posicion, setPosicion] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      const [fixtureRes, posRes] = await Promise.all([
        supabase
          .from("fixture")
          .select(
            `fecha, dia, hora, goles_local, goles_visitante, observaciones,
             local:equipos!fixture_local_id_fkey ( id, nombre ),
             visitante:equipos!fixture_visitante_id_fkey ( id, nombre )`,
          )
          .or(`local_id.eq.${equipo.id},visitante_id.eq.${equipo.id}`)
          .order("fecha"),
        supabase
          .from("posiciones")
          .select("pts, j, g, e, p, gf, gc")
          .eq("equipo_id", equipo.id)
          .single(),
      ]);

      setMatches(fixtureRes.data || []);
      setPosicion(posRes.data);
      setIsLoading(false);
    }
    fetchData();
  }, [equipo.id]);

  if (isLoading)
    return (
      <div className='text-center py-16 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
        Cargando...
      </div>
    );

  return (
    <div className='max-w-2xl mx-auto'>
      {/* Header */}
      <div className='flex items-center gap-5 mb-8'>
        {equipo.nombre && (
            <img
              src={getEscudoPath(equipo.nombre)}
              alt={equipo.nombre}
              className='w-16 h-16 object-contain'
            />
        )}
        <div>
          <h1 className='text-3xl font-extrabold text-white uppercase tracking-tight'>
            {equipo.nombre}
          </h1>
          <p className='text-green-500 text-sm font-medium mt-1'>
            Liga Amateur de Deportes de Lincoln
          </p>
        </div>
      </div>

      {/* Stats */}
      {posicion && (
        <div className='grid grid-cols-5 gap-3 mb-8'>
          {[
            { label: "PTS", value: posicion.pts, highlight: true },
            { label: "PJ", value: posicion.j },
            { label: "G", value: posicion.g },
            { label: "E", value: posicion.e },
            { label: "P", value: posicion.p },
          ].map((stat) => (
            <div
              key={stat.label}
              className='bg-[#143814] rounded-xl border border-green-900/40 p-3 text-center'
            >
              <div
                className={`text-2xl font-black ${
                  stat.highlight ? "text-green-400" : "text-green-100"
                }`}
              >
                {stat.value}
              </div>
              <div className='text-[10px] text-green-600 uppercase tracking-wider font-bold mt-1'>
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Fixture del equipo */}
      <div className='bg-[#143814] rounded-xl border border-green-900/40 overflow-hidden'>
        <div className='px-5 py-4 border-b border-green-900/40 bg-green-950/20'>
          <h2 className='text-sm font-bold uppercase tracking-wider text-green-400'>
            Fixture
          </h2>
        </div>
        <div className='divide-y divide-green-900/20'>
          {matches.map((match, i) => {
            const isLibre = match.observaciones === "LIBRE";
            const seJugo =
              match.goles_local !== null && match.goles_visitante !== null;
            const isLocal = match.local?.id === equipo.id;
            const rival = isLocal ? match.visitante : match.local;

            let resultado = null;
            if (seJugo && !isLibre) {
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
                  <div>Fecha {match.fecha}</div>
                  {match.dia && (
                    <div className='text-green-800 font-normal'>
                      {match.dia}
                    </div>
                  )}
                </div>

                {isLibre ? (
                  <div className='flex-1 text-center text-green-600 font-semibold text-xs'>
                    LIBRE
                  </div>
                ) : (
                  <>
                    <div className='text-[10px] text-green-600 font-bold w-8 shrink-0 text-center'>
                      {isLocal ? "LOC" : "VIS"}
                    </div>

                    <a
                      href={`/equipo/${slugify(rival?.nombre || "")}`}
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
                        className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-black shrink-0 ${
                          resultado === "W"
                            ? "bg-green-500 text-black"
                            : resultado === "D"
                              ? "bg-yellow-500 text-black"
                              : "bg-red-500 text-white"
                        }`}
                      >
                        {resultado === "W"
                          ? "G"
                          : resultado === "D"
                            ? "E"
                            : "P"}
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Volver */}
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
