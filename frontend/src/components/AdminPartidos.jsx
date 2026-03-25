import { useState, useEffect } from "react";
import { createClient } from "@supabase/supabase-js";
import { slugify } from "../utils/slugify";

const CATEGORIAS = [
  { id: 1, nombre: "primera" },
  { id: 2, nombre: "septima" },
  { id: 3, nombre: "octava" },
  { id: 4, nombre: "novena" },
  { id: 5, nombre: "decima" },
];

const TOTAL_FECHAS = 11;

function formatearFecha(dia) {
  if (!dia) return "";
  if (dia.includes("/")) return dia;
  if (dia.includes("-")) {
    const [aa, mm, dd] = dia.split("-");
    return `${dd}/${mm}`;
  }
  return dia;
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

  if (mejor === null) {
    mejor = Math.min(...fechas);
  }

  return mejor;
}

export default function AdminPartidos({ supabaseUrl, supabaseKey }) {
  const supabase = createClient(supabaseUrl, supabaseKey);
  const [categoria, setCategoria] = useState(1);
  const [allMatches, setAllMatches] = useState({});
  const [fechaActual, setFechaActual] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editando, setEditando] = useState({});
  const [guardando, setGuardando] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [partidoEditando, setPartidoEditando] = useState(null);

  useEffect(() => {
    fetchPartidos();
  }, [categoria]);

  async function fetchPartidos() {
    setLoading(true);
    try {
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
          categoria_id,
          local_id,
          visitante_id,
          local:local_id ( nombre, escudo_url ),
          visitante:visitante_id ( nombre, escudo_url )
        `)
        .eq("categoria_id", categoria)
        .order("fecha_id")
        .order("id");

      if (error) {
        console.error("Supabase error:", error);
        setError(error.message);
      } else {
        const grouped = {};
        for (const m of data) {
          if (!grouped[m.fecha_id]) grouped[m.fecha_id] = [];
          grouped[m.fecha_id].push(m);
        }
        setAllMatches(grouped);
        setFechaActual(detectarFechaActual(grouped));
        setError(null);
      }
    } catch (e) {
      console.error("Catch error:", e);
      setError(e.message);
    }
    setLoading(false);
  }

  function getEditing(id) {
    return editando?.[id];
  }

  async function guardarPartido(id) {
    setGuardando(true);
    const partido = getEditing(id);
    
    const updates = {
      dia: partido.dia,
      hora: partido.hora,
      arbitro: partido.arbitro,
      cancha: partido.cancha,
      estado: partido.estado,
      goles_local: partido.goles_local === "" || partido.goles_local === null ? null : Number(partido.goles_local),
      goles_visitante: partido.goles_visitante === "" || partido.goles_visitante === null ? null : Number(partido.goles_visitante),
    };

    const { error } = await supabase
      .from("partidos")
      .update(updates)
      .eq("id", id);

    if (error) {
      alert("Error al guardar: " + error.message);
    } else {
      setEditando((prev) => {
        const newState = { ...(prev || {}) };
        delete newState[id];
        return newState;
      });
      setModalOpen(false);
      setPartidoEditando(null);
      fetchPartidos();
    }
    setGuardando(false);
  }

  function iniciarEdicion(partido) {
    setEditando((prev) => ({
      ...(prev || {}),
      [partido.id]: { ...partido },
    }));
    setPartidoEditando(partido);
    setModalOpen(true);
  }

  function cerrarModal() {
    setModalOpen(false);
    setPartidoEditando(null);
    setEditando({});
  }

  function handleChange(field, value) {
    if (!partidoEditando) return;
    setEditando((prev) => ({
      ...(prev || {}),
      [partidoEditando.id]: {
        ...(prev?.[partidoEditando.id] || partidoEditando),
        [field]: value,
      },
    }));
  }

  const matches = allMatches[fechaActual] || [];

  return (
    <div className="p-4">
      {/* Selector de categoría */}
      <div className="flex items-center justify-between mb-4">
        <select
          value={categoria}
          onChange={(e) => setCategoria(Number(e.target.value))}
          className="px-4 py-2 bg-green-950/30 border border-green-900/50 rounded-lg text-green-400 focus:outline-none focus:border-green-500 font-bold text-sm uppercase"
        >
          {CATEGORIAS.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.nombre.charAt(0).toUpperCase() + cat.nombre.slice(1)}
            </option>
          ))}
        </select>
        
        {/* Navegación de fechas */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFechaActual((f) => Math.max(1, f - 1))}
            disabled={fechaActual === 1}
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30"
          >
            ‹
          </button>

          <div className="relative">
            <div
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-900/40 text-green-400 hover:bg-green-900/60 transition-all font-bold text-sm uppercase tracking-wide cursor-pointer"
            >
              Fecha {fechaActual}
              <svg
                className={`w-3 h-3 transition-transform ${dropdownOpen ? "rotate-180" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={3}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </div>

            {dropdownOpen && (
              <div className="absolute top-full left-1/2 -translate-x-1/2 mt-1 bg-[#143814] border border-green-900/60 rounded-lg shadow-xl z-50 overflow-y-auto max-h-60">
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
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30"
          >
            ›
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-green-400 animate-pulse text-center py-8">Cargando...</p>
      ) : error ? (
        <p className="text-red-400 text-center py-8">Error: {error}</p>
      ) : matches.length === 0 ? (
        <p className="text-green-400 text-center py-8">No hay partidos</p>
      ) : (
        /* Partidos */
        <div className="space-y-2">
          {matches.map((match, i) => {
            const isLibre = match.visitante_id === null;
            const seJugo = match.estado === "jugado" || (match.goles_local !== null && match.goles_visitante !== null);

            if (isLibre) {
              return (
                <div
                  key={i}
                  className="flex items-center gap-2 py-2 px-3 rounded-lg bg-green-950/20 border border-dashed border-green-900/30"
                >
                  <span className="text-[10px] text-green-700 font-mono w-10 shrink-0 text-center"></span>
                  <a
                    href={`/equipo/${slugify(match.local?.nombre || "")}`}
                    className="flex items-center gap-1.5 flex-1 justify-end min-w-0 hover:opacity-80"
                  >
                    {match.local?.escudo_url && (
                      <img
                        src={match.local.escudo_url}
                        alt={match.local.nombre}
                        className="w-5 h-5 object-contain"
                      />
                    )}
                    <span className="truncate text-green-100 font-semibold text-right">
                      {match.local?.nombre}
                    </span>
                  </a>
                  <span className="text-green-700 font-bold text-sm"></span>
                  <span className="flex-1 text-left text-green-400 font-bold uppercase ">
                    LIBRE
                  </span>
                </div>
              );
            }

            return (
              <div
                key={i}
                className="flex items-center gap-2 py-2 px-3 rounded-lg bg-green-950/30 hover:bg-green-400/5 transition-colors"
              >
                <span className="text-[10px] text-green-700 font-mono w-16 shrink-0 text-left">
                  {seJugo ? (
                    <span>
                      {formatearFecha(match.dia) ? (
                        <span>{formatearFecha(match.dia)} <span className="font-bold text-green-400">JUGADO</span></span>
                      ) : (
                        <span className="font-bold text-green-400">JUGADO</span>
                      )}
                    </span>
                  ) : (match.hora ? `${formatearFecha(match.dia) || "A DEFINIR"} - ${match.hora.slice(0, 5)}hs` : (formatearFecha(match.dia) || <span className="font-bold text-green-400">A DEFINIR</span>))}
                </span>
                <a
                  href={`/equipo/${slugify(match.local?.nombre || "")}`}
                  className="flex items-center gap-1.5 flex-1 justify-end min-w-0 hover:opacity-80"
                >
                  <span className="truncate text-green-100 font-semibold text-right">
                    {match.local?.nombre}
                  </span>
                  {match.local?.escudo_url && (
                    <img
                      src={match.local.escudo_url}
                      alt={match.local.nombre}
                      className="w-5 h-5 object-contain shrink-0"
                    />
                  )}
                </a>
                <div className="flex items-center gap-1 shrink-0 px-2">
                  {seJugo ? (
                    <>
                      <span className="font-black text-green-400 text-sm w-4 text-center">
                        {match.goles_local}
                      </span>
                      <span className="text-green-700">–</span>
                      <span className="font-black text-green-400 text-sm w-4 text-center">
                        {match.goles_visitante}
                      </span>
                    </>
                  ) : (
                    <span className="text-green-700 font-bold text-sm">vs</span>
                  )}
                </div>
                <a
                  href={`/equipo/${slugify(match.visitante?.nombre || "")}`}
                  className="flex items-center gap-1.5 flex-1 min-w-0 hover:opacity-80"
                >
                  {match.visitante?.escudo_url && (
                    <img
                      src={match.visitante.escudo_url}
                      alt={match.visitante.nombre}
                      className="w-5 h-5 object-contain shrink-0"
                    />
                  )}
                  <span className="truncate text-green-100 font-semibold">
                    {match.visitante?.nombre}
                  </span>
                </a>
                <button
                  onClick={() => iniciarEdicion(match)}
                  className="ml-2 px-3 py-1 bg-green-700 hover:bg-green-600 text-white text-xs font-medium rounded transition-colors shrink-0"
                >
                  Editar
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal de edición */}
      {modalOpen && partidoEditando && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-[#143814] border border-green-900/50 rounded-lg p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-green-400 font-bold text-lg">
                Editar Partido
              </h2>
              <button
                onClick={cerrarModal}
                className="text-green-400 hover:text-green-300 text-2xl"
              >
                ×
              </button>
            </div>
            
            <div className="mb-4 text-green-300 text-sm text-center">
              <span className="font-bold">{partidoEditando.local?.nombre}</span>
              {" vs "}
              <span className="font-bold">{partidoEditando.visitante?.nombre}</span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-green-500 text-xs mb-1">
                  Día
                </label>
                <input
                  type="text"
                  value={getEditing(partidoEditando.id)?.dia || partidoEditando.dia || ""}
                  onChange={(e) => handleChange("dia", e.target.value)}
                  className="w-full px-3 py-2 bg-green-950/50 border border-green-800 rounded text-white"
                  placeholder="dd/mm"
                />
              </div>
              <div>
                <label className="block text-green-500 text-xs mb-1">
                  Hora
                </label>
                <input
                  type="text"
                  value={getEditing(partidoEditando.id)?.hora || partidoEditando.hora || ""}
                  onChange={(e) => handleChange("hora", e.target.value)}
                  className="w-full px-3 py-2 bg-green-950/50 border border-green-800 rounded text-white"
                  placeholder="hh:mm"
                />
              </div>
              <div>
                <label className="block text-green-500 text-xs mb-1">
                  Estado
                </label>
                <select
                  value={getEditing(partidoEditando.id)?.estado || partidoEditando.estado || "programado"}
                  onChange={(e) => handleChange("estado", e.target.value)}
                  className="w-full px-3 py-2 bg-green-950/50 border border-green-800 rounded text-white"
                >
                  <option value="programado">Programado</option>
                  <option value="jugado">Jugado</option>
                  <option value="suspendido">Suspendido</option>
                </select>
              </div>
              <div>
                <label className="block text-green-500 text-xs mb-1">
                  Árbitro
                </label>
                <input
                  type="text"
                  value={getEditing(partidoEditando.id)?.arbitro || partidoEditando.arbitro || ""}
                  onChange={(e) => handleChange("arbitro", e.target.value)}
                  className="w-full px-3 py-2 bg-green-950/50 border border-green-800 rounded text-white"
                  placeholder="Nombre"
                />
              </div>
              <div>
                <label className="block text-green-500 text-xs mb-1">
                  Cancha
                </label>
                <input
                  type="text"
                  value={getEditing(partidoEditando.id)?.cancha || partidoEditando.cancha || ""}
                  onChange={(e) => handleChange("cancha", e.target.value)}
                  className="w-full px-3 py-2 bg-green-950/50 border border-green-800 rounded text-white"
                  placeholder="Nombre"
                />
              </div>
              <div>
                <label className="block text-green-500 text-xs mb-1">
                  Goles Local
                </label>
                <input
                  type="number"
                  value={getEditing(partidoEditando.id)?.goles_local ?? partidoEditando.goles_local ?? ""}
                  onChange={(e) => handleChange("goles_local", e.target.value)}
                  className="w-full px-3 py-2 bg-green-950/50 border border-green-800 rounded text-white"
                  placeholder="0"
                />
              </div>
              <div>
                <label className="block text-green-500 text-xs mb-1">
                  Goles Visitante
                </label>
                <input
                  type="number"
                  value={getEditing(partidoEditando.id)?.goles_visitante ?? partidoEditando.goles_visitante ?? ""}
                  onChange={(e) => handleChange("goles_visitante", e.target.value)}
                  className="w-full px-3 py-2 bg-green-950/50 border border-green-800 rounded text-white"
                  placeholder="0"
                />
              </div>
            </div>

            <div className="flex gap-2 mt-6">
              <button
                onClick={() => guardarPartido(partidoEditando.id)}
                disabled={guardando}
                className="flex-1 py-2 bg-green-600 hover:bg-green-500 text-black font-semibold rounded transition-colors disabled:opacity-50"
              >
                {guardando ? "Guardando..." : "Guardar"}
              </button>
              <button
                onClick={cerrarModal}
                className="px-6 py-2 bg-gray-600 hover:bg-gray-500 text-white font-medium rounded transition-colors"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
