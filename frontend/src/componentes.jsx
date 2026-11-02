import { ErrorApi } from "./api.js";

export function Cargando({ texto = "Cargando…" }) {
  return <p className="cargando">{texto}</p>;
}

export function Vacio({ texto = "Sin resultados." }) {
  return <p className="vacio">{texto}</p>;
}

/** Aviso de éxito/error; `error` acepta ErrorApi (muestra status + detail). */
export function Aviso({ tipo = "info", texto, onCerrar }) {
  if (!texto) return null;
  return (
    <div className={`aviso ${tipo}`} role="status">
      {texto}
      {onCerrar && (
        <button className="mini secundario" style={{ float: "right" }} onClick={onCerrar}>
          ✕
        </button>
      )}
    </div>
  );
}

export function mensajeError(exc) {
  if (exc instanceof ErrorApi) {
    const prefijo = exc.status ? `[${exc.status}] ` : "";
    return `${prefijo}${exc.message}`;
  }
  return exc?.message || "Error inesperado";
}

/** Insignia de estado de préstamo (máquina T1–T9, §4). */
export function InsigniaEstado({ estado }) {
  const mapa = {
    PENDIENTE_INVENTARIO: ["proceso", "Pendiente de reserva"],
    APROBADA: ["ok", "Aprobada (reserva confirmada)"],
    COMPLETADA: ["ok", "Completada (entregada)"],
    RECHAZADA: ["error", "Rechazada"],
    CANCELADA: ["", "Cancelada"],
    CANCELADA_SIN_STOCK: ["error", "Cancelada · sin stock"],
    CANCELADA_VENCIDA: ["aviso", "Cancelada · reserva vencida"],
  };
  const [clase, texto] = mapa[estado] || ["", estado];
  return <span className={`insignia ${clase}`}>{texto}</span>;
}

/** Estados en los que la solicitud ya no cambia (fin del polling, §10). */
export function esEstadoFinal(estado) {
  return ["APROBADA", "COMPLETADA", "RECHAZADA", "CANCELADA",
          "CANCELADA_SIN_STOCK", "CANCELADA_VENCIDA"].includes(estado);
}
