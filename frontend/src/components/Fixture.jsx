import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { slugify } from "../utils/slugify";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

const TOTAL_FECHAS = 11;

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
  const key = nombre.toLowerCase().trim()
  return mapa[key] || '/escudos/argentino.png'
}

function parseDate(dia) {
  if (!dia) return null;
  const anio = new Date().getFullYear();
  if (dia.includes("/")) {
    const parts = dia.split("/");
    if (parts.length === 3) {
      const [dd, mm, aa] = parts;
      return new Date(aa.includes("20") ? anio : `20${aa}`, parseInt(mm) - 1, parseInt(dd));
    }
    const [dd, mm] = parts.map(Number);
    if (dd > 12) {
      return new Date(anio, parseInt(mm) - 1, dd);
    }
    return new Date(anio, dd - 1, parseInt(mm));
  }
  if (dia.includes("-")) {
    const [aa, mm, dd] = dia.split("-");
    return new Date(aa.includes("20") ? anio : `20${aa}`, parseInt(mm) - 1, parseInt(dd));
  }
  return null;
}

function detectarFechaActual(grouped) {
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const anio = hoy.getFullYear();

  let mejor = null;
  let menorDiff = Infinity;
  let fechas = Object.keys(grouped)
    .map(Number)
    .sort((a, b) => a - b);

  for (const fechaNum of fechas) {
    const dia = grouped[fechaNum][0]?.dia;
    if (!dia) continue;
    // Permitir tanto formato dd/mm como yyyy-mm-dd
    let fechaPartido;
    if (dia.includes("/")) {
      const [dd, mm] = dia.split("/").map(Number);
      fechaPartido = new Date(anio, mm - 1, dd);
    } else {
      fechaPartido = new Date(dia);
    }
    const diff = fechaPartido - hoy;
    if (diff >= 0 && diff < menorDiff) {
      menorDiff = diff;
      mejor = Number(fechaNum);
    }
  }

  // Si no encontró ninguna futura, usar la menor (primera) fecha
  if (mejor === null) {
    mejor = Math.min(...fechas);
  }

  return mejor;
}

export default function Fixture() {
  const [allMatches, setAllMatches] = useState({});
  const [fechaActual, setFechaActual] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  useEffect(() => {
    async function fetchFixture() {
      const { data, error } = await supabase
        .from("partidos")
        .select(
          `
          fecha_id,
          dia,
          hora,
          goles_local,
          goles_visitante,
          estado,
          local_id,
          visitante_id,
          local:local_id ( nombre ),
          visitante:visitante_id ( nombre )
        `,
        )
        .order("fecha_id")
        .order("id");

      if (error) {
        console.error("Error fetching partidos:", error);
      } else {
        const grouped = {};
        for (const m of data) {
          if (!grouped[m.fecha_id]) grouped[m.fecha_id] = [];
          grouped[m.fecha_id].push(m);
        }
        
        // Ordenar cada fecha por dia y hora
        for (const fecha of Object.keys(grouped)) {
          grouped[fecha].sort((a, b) => {
            // LIBRE siempre al final
            if (a.visitante_id === null && b.visitante_id !== null) return 1;
            if (b.visitante_id === null && a.visitante_id !== null) return -1;
            
            const fechaA = parseDate(a.dia);
            const fechaB = parseDate(b.dia);
            if (fechaA && fechaB) {
              if (fechaA.getTime() !== fechaB.getTime()) {
                return fechaA - fechaB;
              }
            } else if (fechaA) return -1;
            else if (fechaB) return 1;
            
            const horaA = a.hora || "";
            const horaB = b.hora || "";
            return horaA.localeCompare(horaB);
          });
        }
        
        setAllMatches(grouped);
        setFechaActual(detectarFechaActual(grouped));
      }
      setIsLoading(false);
    }
    fetchFixture();
  }, []);

  const matches = allMatches[fechaActual] || [];

  if (isLoading) {
    return (
      <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
        Cargando...
      </div>
    );
  }

  return (
    <div className='p-4'>
      {" "}
      {/* Agregué un contenedor padre que faltaba */}
      <div className='flex items-center justify-between mb-4'>
        <button
          onClick={() => setFechaActual((f) => Math.max(1, f - 1))}
          disabled={fechaActual === 1}
          className='w-8 h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30'
        >
          ‹
        </button>

        <div className='relative'>
          <div
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className='flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-900/40 text-green-400 hover:bg-green-900/60 transition-all font-bold text-sm uppercase tracking-wide cursor-pointer'
          >
            Fecha {fechaActual}
            <svg
              className={`w-3 h-3 transition-transform ${dropdownOpen ? "rotate-180" : ""}`}
              fill='none'
              viewBox='0 0 24 24'
              stroke='currentColor'
            >
              <path
                strokeLinecap='round'
                strokeLinejoin='round'
                strokeWidth={3}
                d='M19 9l-7 7-7-7'
              />
            </svg>
          </div>

          {dropdownOpen && (
            <div className='absolute top-full left-1/2 -translate-x-1/2 mt-1 bg-[#143814] border border-green-900/60 rounded-lg shadow-xl z-50 overflow-y-auto max-h-60'>
              {Array.from({ length: TOTAL_FECHAS }, (_, i) => i + 1).map(
                (f) => (
                  <button
                    key={f}
                    onClick={() => {
                      setFechaActual(f);
                      setDropdownOpen(false);
                    }}
                    className={`block w-full px-6 py-1.5 text-left text-xs font-semibold whitespace-nowrap transition-colors ${
                      f === fechaActual
                        ? "bg-green-400 text-black"
                        : "text-green-400 hover:bg-green-900/40"
                    }`}
                  >
                    Fecha {f}
                  </button>
                ),
              )}
            </div>
          )}
        </div>

        <button
          onClick={() => setFechaActual((f) => Math.min(TOTAL_FECHAS, f + 1))}
          disabled={fechaActual === TOTAL_FECHAS}
          className='w-8 h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30'
        >
          ›
        </button>
      </div>
      {/* Fecha del partido */}
      {matches[0]?.dia && (
        <div className='text-center mb-3'>
          <span className='text-green-600 text-[11px] font-medium'>            {matches[0].dia}
          </span>
        </div>
      )}
      {/* Partidos */}
      <div className='space-y-2'>
        {matches.map((match, i) => {
          const isLibre = match.visitante_id === null;
          const seJugo =
            match.goles_local !== null && match.goles_visitante !== null;

          if (isLibre) {
            return (
              <div
                key={i}
                className='flex items-center gap-2 py-2 px-3 rounded-lg bg-green-950/20 border border-dashed border-green-900/30'
              >
                <span className='text-[10px] text-green-700 font-mono w-10 shrink-0 text-center'></span>
                <a
                  href={`/equipo/${slugify(match.local?.nombre || "")}`}
                  className='flex items-center gap-1.5 flex-1 justify-end min-w-0 hover:opacity-80'
                >
                  {match.local?.nombre && (
                      <img
                        src={getEscudoPath(match.local.nombre)}
                        alt={match.local.nombre}
                        className="w-6 h-6 object-contain"
                      />
                  )}
                  <span className='truncate text-green-100 font-semibold text-right'>
                    {match.local?.nombre}
                  </span>
                </a>
                <span className='text-green-700 font-bold text-sm '></span>
                <span className='flex-1 text-left text-green-400 font-bold uppercase '>
                  LIBRE
                </span>
              </div>
            );
          }

          return (
            <div
              key={i}
              className='flex items-center gap-2 py-2 px-3 rounded-lg bg-green-950/30 hover:bg-green-400/5 transition-colors'
            >
              <span className='text-[10px] text-green-700 font-mono w-10 shrink-0 text-center'>
                {match.hora || "hh:mm"}
              </span>
              <a
                href={`/equipo/${slugify(match.local?.nombre || "")}`}
                className='flex items-center gap-1.5 flex-1 justify-end min-w-0 hover:opacity-80'
              >
                <span className='truncate text-green-100 font-semibold text-right'>
                  {match.local?.nombre}
                </span>
                {match.local?.nombre && (
                    <img
                      src={getEscudoPath(match.local.nombre)}
                      alt={match.local.nombre}
                      className="w-4 h-4 object-contain"
                    />
                )}
              </a>
              <div className='flex items-center gap-1 shrink-0 px-2'>
                {seJugo ? (
                  <>
                    <span className='font-black text-green-400 text-sm w-4 text-center'>
                      {match.goles_local}
                    </span>
                    <span className='text-green-700'>–</span>
                    <span className='font-black text-green-400 text-sm w-4 text-center'>
                      {match.goles_visitante}
                    </span>
                  </>
                ) : (
                  <span className='text-green-700 font-bold text-sm'>vs</span>
                )}
              </div>
              <a
                href={`/equipo/${slugify(match.visitante?.nombre || "")}`}
                className='flex items-center gap-1.5 flex-1 min-w-0 hover:opacity-80'
              >
                {match.visitante?.nombre && (
                    <img
                      src={getEscudoPath(match.visitante.nombre)}
                      alt={match.visitante.nombre}
                      className="w-4 h-4 object-contain"
                    />
                )}
                <span className='truncate text-green-100 font-semibold'>
                  {match.visitante?.nombre}
                </span>
              </a>
            </div>
          );
        })}
      </div>
    </div>
  );
}
