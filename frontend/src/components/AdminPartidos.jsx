import { useState, useEffect } from "react";
import { createClient } from "@supabase/supabase-js";

const CATEGORIAS = [
  { id: 1, nombre: "primera" },
  { id: 2, nombre: "septima" },
  { id: 3, nombre: "octava" },
  { id: 4, nombre: "novena" },
  { id: 5, nombre: "decima" },
];

export default function AdminPartidos({ supabaseUrl, supabaseKey }) {
  const supabase = createClient(supabaseUrl, supabaseKey);
  const [categoria, setCategoria] = useState(1);
  const [partidos, setPartidos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editando, setEditando] = useState({});
  const [guardando, setGuardando] = useState(false);

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
      setPartidos(data || []);
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
      goles_local: partido.goles_local === "" ? null : Number(partido.goles_local),
      goles_visitante: partido.goles_visitante === "" ? null : Number(partido.goles_visitante),
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
      fetchPartidos();
    }
    setGuardando(false);
  }

  function iniciarEdicion(partido) {
    setEditando((prev) => ({
      ...(prev || {}),
      [partido.id]: { ...partido },
    }));
  }

  function cancelarEdicion(id) {
    setEditando((prev) => {
      const newState = { ...(prev || {}) };
      delete newState[id];
      return newState;
    });
  }

  function handleChange(id, field, value) {
    setEditando((prev) => ({
      ...(prev || {}),
      [id]: {
        ...(prev?.[id] || {}),
        [field]: value,
      },
    }));
  }

  const groupedByFecha = {};
  for (const p of partidos) {
    if (!groupedByFecha[p.fecha_id]) groupedByFecha[p.fecha_id] = [];
    groupedByFecha[p.fecha_id].push(p);
  }

  return (
    <div>
      <div className="mb-6">
        <label className="block text-green-400 text-sm font-medium mb-2">
          Categoría
        </label>
        <select
          value={categoria}
          onChange={(e) => setCategoria(Number(e.target.value))}
          className="px-4 py-2 bg-green-950/30 border border-green-900/50 rounded-lg text-white focus:outline-none focus:border-green-500"
        >
          {CATEGORIAS.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.nombre.charAt(0).toUpperCase() + cat.nombre.slice(1)}
            </option>
          ))}
        </select>
      </div>

      <pre className="text-green-400 text-xs mb-4">
        Loading: {loading ? 'true' : 'false'}
        Error: {error || 'none'}
        Partidos: {partidos.length}
      </pre>

      {loading ? (
        <p className="text-green-400 animate-pulse">Cargando...</p>
      ) : error ? (
        <p className="text-red-400">Error: {error}</p>
      ) : partidos.length === 0 ? (
        <p className="text-green-400">No hay partidos en esta categoría</p>
      ) : (
        <div className="space-y-8">
          {Object.entries(groupedByFecha).map(([fechaId, partidosFecha]) => (
            <div key={fechaId}>
              <h3 className="text-green-400 font-bold mb-3 text-lg">
                Fecha {fechaId}
              </h3>
              <div className="space-y-3">
                {partidosFecha.map((partido) => {
                  const editing = getEditing(partido.id);
                  const isLibre = partido.visitante_id === null;

                  if (isLibre) {
                    return (
                      <div
                        key={partido.id}
                        className="p-3 bg-green-950/20 border border-green-900/30 rounded-lg"
                      >
                        <span className="text-green-600 font-medium">
                          {partido.local?.nombre} - LIBRE
                        </span>
                      </div>
                    );
                  }

                  return (
                    <div
                      key={partido.id}
                      className="p-4 bg-green-950/20 border border-green-900/50 rounded-lg"
                    >
                      <div className="flex items-center gap-3 mb-3">
                        <span className="text-green-400 font-bold">
                          {partido.local?.nombre}
                        </span>
                        <span className="text-green-600">vs</span>
                        <span className="text-green-400 font-bold">
                          {partido.visitante?.nombre}
                        </span>
                      </div>

                      {editing ? (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div>
                            <label className="block text-green-500 text-xs mb-1">
                              Día
                            </label>
                            <input
                              type="text"
                              value={editing.dia || ""}
                              onChange={(e) =>
                                handleChange(partido.id, "dia", e.target.value)
                              }
                              className="w-full px-2 py-1 bg-green-950/50 border border-green-800 rounded text-white text-sm"
                              placeholder="dd/mm"
                            />
                          </div>
                          <div>
                            <label className="block text-green-500 text-xs mb-1">
                              Hora
                            </label>
                            <input
                              type="text"
                              value={editing.hora || ""}
                              onChange={(e) =>
                                handleChange(partido.id, "hora", e.target.value)
                              }
                              className="w-full px-2 py-1 bg-green-950/50 border border-green-800 rounded text-white text-sm"
                              placeholder="15:00"
                            />
                          </div>
                          <div>
                            <label className="block text-green-500 text-xs mb-1">
                              Estado
                            </label>
                            <select
                              value={editing.estado || "pendiente"}
                              onChange={(e) =>
                                handleChange(partido.id, "estado", e.target.value)
                              }
                              className="w-full px-2 py-1 bg-green-950/50 border border-green-800 rounded text-white text-sm"
                            >
                              <option value="pendiente">Pendiente</option>
                              <option value="jugado">Jugado</option>
                              <option value="suspendido">Suspendido</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-green-500 text-xs mb-1">
                              Goles Local
                            </label>
                            <input
                              type="number"
                              value={editing.goles_local ?? ""}
                              onChange={(e) =>
                                handleChange(
                                  partido.id,
                                  "goles_local",
                                  e.target.value
                                )
                              }
                              className="w-full px-2 py-1 bg-green-950/50 border border-green-800 rounded text-white text-sm"
                              placeholder="0"
                            />
                          </div>
                          <div>
                            <label className="block text-green-500 text-xs mb-1">
                              Goles Visitante
                            </label>
                            <input
                              type="number"
                              value={editing.goles_visitante ?? ""}
                              onChange={(e) =>
                                handleChange(
                                  partido.id,
                                  "goles_visitante",
                                  e.target.value
                                )
                              }
                              className="w-full px-2 py-1 bg-green-950/50 border border-green-800 rounded text-white text-sm"
                              placeholder="0"
                            />
                          </div>
                          <div>
                            <label className="block text-green-500 text-xs mb-1">
                              Árbitro
                            </label>
                            <input
                              type="text"
                              value={editing.arbitro || ""}
                              onChange={(e) =>
                                handleChange(
                                  partido.id,
                                  "arbitro",
                                  e.target.value
                                )
                              }
                              className="w-full px-2 py-1 bg-green-950/50 border border-green-800 rounded text-white text-sm"
                              placeholder="Nombre"
                            />
                          </div>
                          <div>
                            <label className="block text-green-500 text-xs mb-1">
                              Cancha
                            </label>
                            <input
                              type="text"
                              value={editing.cancha || ""}
                              onChange={(e) =>
                                handleChange(partido.id, "cancha", e.target.value)
                              }
                              className="w-full px-2 py-1 bg-green-950/50 border border-green-800 rounded text-white text-sm"
                              placeholder="Nombre"
                            />
                          </div>
                          <div className="flex items-end gap-2">
                            <button
                              onClick={() => guardarPartido(partido.id)}
                              disabled={guardando}
                              className="px-3 py-1 bg-green-600 hover:bg-green-500 text-black text-sm font-medium rounded transition-colors disabled:opacity-50"
                            >
                              {guardando ? "..." : "Guardar"}
                            </button>
                            <button
                              onClick={() => cancelarEdicion(partido.id)}
                              className="px-3 py-1 bg-gray-600 hover:bg-gray-500 text-white text-sm font-medium rounded transition-colors"
                            >
                              Cancelar
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex flex-wrap items-center gap-4 text-sm">
                          <span className="text-green-300">
                            <span className="text-green-600">Día:</span>{" "}
                            {partido.dia || "-"}
                          </span>
                          <span className="text-green-300">
                            <span className="text-green-600">Hora:</span>{" "}
                            {partido.hora || "-"}
                          </span>
                          <span className="text-green-300">
                            <span className="text-green-600">Estado:</span>{" "}
                            {partido.estado || "pendiente"}
                          </span>
                          <span className="text-green-300">
                            <span className="text-green-600">Resultado:</span>{" "}
                            {partido.goles_local !== null
                              ? `${partido.goles_local} - ${partido.goles_visitante}`
                              : "-"}
                          </span>
                          <span className="text-green-300">
                            <span className="text-green-600">Árbitro:</span>{" "}
                            {partido.arbitro || "-"}
                          </span>
                          <span className="text-green-300">
                            <span className="text-green-600">Cancha:</span>{" "}
                            {partido.cancha || "-"}
                          </span>
                          <button
                            onClick={() => iniciarEdicion(partido)}
                            className="ml-auto px-3 py-1 bg-green-700 hover:bg-green-600 text-white text-xs font-medium rounded transition-colors"
                          >
                            Editar
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
