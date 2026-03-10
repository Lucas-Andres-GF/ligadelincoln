import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { slugify } from "../utils/slugify";

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

const TOTAL_FECHAS = 11;

function detectarFechaActual(grouped) {
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const anio = hoy.getFullYear();

  let mejor = 1;
  let menorDiff = Infinity;

  for (const fechaNum in grouped) {
    const dia = grouped[fechaNum][0]?.dia;
    if (!dia) continue;
    const [dd, mm] = dia.split("/").map(Number);
    const fechaPartido = new Date(anio, mm - 1, dd);
    const diff = fechaPartido - hoy;

    // Preferir la fecha más cercana >= hoy, o si ya pasaron todas, la última jugada
    if (diff >= 0 && diff < menorDiff) {
      menorDiff = diff;
      mejor = Number(fechaNum);
    }
  }

  // Si no encontró ninguna futura, usar la última fecha
  if (menorDiff === Infinity) {
    mejor = Math.max(...Object.keys(grouped).map(Number));
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
        .from("fixture")
        .select(
          `fecha, dia, hora, goles_local, goles_visitante, observaciones,
           local:equipos!fixture_local_id_fkey ( nombre, escudo_url ),
           visitante:equipos!fixture_visitante_id_fkey ( nombre, escudo_url )`,
        )
        .order("fecha")
        .order("id");

      if (error) {
        console.error("Error fetching fixture:", error);
      } else {
        const grouped = {};
        for (const m of data) {
          if (!grouped[m.fecha]) grouped[m.fecha] = [];
          grouped[m.fecha].push(m);
        }
        setAllMatches(grouped);
        setFechaActual(detectarFechaActual(grouped));
      }
      setIsLoading(false);
    }
    fetchFixture();
  }, []);

  const matches = allMatches[fechaActual] || [];

  if (isLoading)
    return (
      <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
        Cargando...
      </div>
    );

  return (
    <div className='w-full text-xs'>
      {/* Header con flechas y selector de fecha */}
      <div className='flex items-center justify-between mb-4 px-1'>
        <button
          onClick={() => setFechaActual((f) => Math.max(1, f - 1))}
          disabled={fechaActual === 1}
          className='w-8 h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed'
        >
          ‹
        </button>

        <div className='relative'>
          <button
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
          </button>

          {dropdownOpen && (
            <div
              className='absolute top-full left-1/2 -translate-x-1/2 mt-1 bg-[#143814] border border-green-900/60 rounded-lg shadow-xl z-50 overflow-y-auto max-h-60 scrollbar-none'
              style={{ scrollbarWidth: "none" }}
            >
              {Array.from({ length: TOTAL_FECHAS }, (_, i) => i + 1).map(
                (f) => (
                  <button
                    key={f}
                    onClick={() => {
                      setFechaActual(f);
                      setDropdownOpen(false);
                    }}
                    className={`block w-full px-6 py-1.5 text-left text-xs font-semibold whitespace-nowrap cursor-pointer transition-colors ${
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
          className='w-8 h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed'
        >
          ›
        </button>
      </div>

      {/* Fecha del partido */}
      {matches[0]?.dia && (
        <div className='text-center mb-3'>
          <span className='text-green-600 text-[11px] font-medium'>
            Dom {matches[0].dia}
          </span>
        </div>
      )}

      {/* Partidos */}
      <div className='space-y-2'>
        {matches.map((match, i) => {
          const isLibre = match.observaciones === "LIBRE";
          const seJugo =
            match.goles_local !== null && match.goles_visitante !== null;

          if (isLibre) {
            return (
              <div
                key={i}
                className='flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-green-950/20 border border-dashed border-green-900/30'
              >
                <span className='text-green-600 font-semibold'>LIBRE:</span>
                <a
                  href={`/equipo/${slugify(match.local?.nombre || "")}`}
                  className='flex items-center gap-1.5 hover:opacity-80 transition-opacity'
                >
                  {match.local?.escudo_url && (
                    <img
                      src={match.local.escudo_url}
                      alt={match.local.nombre}
                      className='w-5 h-5 object-contain'
                    />
                  )}
                  <span className='text-green-400 font-semibold'>
                    {match.local?.nombre}
                  </span>
                </a>
              </div>
            );
          }

          return (
            <div
              key={i}
              className='flex items-center gap-2 py-2 px-3 rounded-lg bg-green-950/30 hover:bg-green-400/5 transition-colors'
            >
              <span className='text-[10px] text-green-700 font-mono w-10 shrink-0 text-center'>
                {match.hora || "15:00"}
              </span>
              <a
                href={`/equipo/${slugify(match.local?.nombre || "")}`}
                className='flex items-center gap-1.5 flex-1 justify-end min-w-0 hover:opacity-80 transition-opacity'
              >
                <span className='truncate text-green-100 font-semibold text-right'>
                  {match.local?.nombre}
                </span>
                {match.local?.escudo_url && (
                  <img
                    src={match.local.escudo_url}
                    alt={match.local.nombre}
                    className='w-5 h-5 object-contain shrink-0'
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
                className='flex items-center gap-1.5 flex-1 min-w-0 hover:opacity-80 transition-opacity'
              >
                {match.visitante?.escudo_url && (
                  <img
                    src={match.visitante.escudo_url}
                    alt={match.visitante.nombre}
                    className='w-5 h-5 object-contain shrink-0'
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
