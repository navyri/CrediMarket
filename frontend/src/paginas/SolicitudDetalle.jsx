import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { cop, fecha, llamar } from "../api.js";
import { Aviso, Cargando, InsigniaEstado, esEstadoFinal, mensajeError } from "../componentes.jsx";
import { useSesion } from "../sesion.jsx";

const INTERVALO_MS = 2500;

/**
 * Detalle de solicitud con actualización automática (§10): hace polling hasta
 * un estado final. En PENDIENTE_INVENTARIO la decisión de riesgo es favorable
 * pero la solicitud NO está aprobada hasta que Inventario confirma la reserva.
 */
export default function SolicitudDetalle() {
  const { id } = useParams();
  const { esAdmin } = useSesion();
  const [prestamo, setPrestamo] = useState(null);
  const [error, setError] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [cancelando, setCancelando] = useState(false);
  const reloj = useRef(null);

  const cargar = useCallback(async () => {
    try {
      const respuesta = await llamar("prestamos", `/prestamos/${id}`);
      setPrestamo(respuesta);
      setError(null);
      return respuesta;
    } catch (exc) {
      setError(mensajeError(exc));
      return null;
    }
  }, [id]);

  // Polling: activo mientras la solicitud siga en movimiento (§10).
  useEffect(() => {
    let vivo = true;
    const arrancar = async () => {
      const actual = await cargar();
      if (!vivo) return;
      if (actual && !esEstadoFinal(actual.estado)) {
        reloj.current = setInterval(async () => {
          const siguiente = await cargar();
          if (siguiente && esEstadoFinal(siguiente.estado)) clearInterval(reloj.current);
        }, INTERVALO_MS);
      }
    };
    arrancar();
    return () => { vivo = false; if (reloj.current) clearInterval(reloj.current); };
  }, [cargar]);

  const cancelar = async () => {
    setCancelando(true);
    try {
      await llamar("prestamos", `/prestamos/${id}/cancelar`, { metodo: "POST" });
      setAviso("Cancelación solicitada: se libera la reserva (si existe) y la solicitud termina en estado final.");
      await cargar();
    } catch (exc) {
      setError(mensajeError(exc));
    } finally {
      setCancelando(false);
    }
  };

  if (error && !prestamo) return <><Aviso tipo="error" texto={error} /><Link to="/solicitudes">← Volver</Link></>;
  if (!prestamo) return <Cargando texto="Cargando solicitud…" />;

  const enMovimiento = !esEstadoFinal(prestamo.estado);
  const esMia = !esAdmin;
  const cancelable = ["PENDIENTE_INVENTARIO", "APROBADA"].includes(prestamo.estado);

  return (
    <>
      <p><Link to="/solicitudes">← Volver a solicitudes</Link></p>
      <h1>Solicitud {prestamo.id.slice(0, 8)}…</h1>
      <p className="subtitulo">
        <InsigniaEstado estado={prestamo.estado} />
        {enMovimiento && <> · actualización automática cada {INTERVALO_MS / 1000} s…</>}
      </p>

      <Aviso tipo="error" texto={error} />
      <Aviso tipo="ok" texto={aviso} />

      {prestamo.estado === "PENDIENTE_INVENTARIO" && (
        <Aviso tipo="info" texto="Decisión de riesgo FAVORABLE, pero la solicitud sigue pendiente de
          reserva de inventario: hasta que Inventario confirme la reserva, NO es una aprobación." />
      )}
      {prestamo.estado === "APROBADA" && (
        <Aviso tipo="ok" texto="Reserva de inventario confirmada: aprobación final del préstamo." />
      )}
      {prestamo.estado === "RECHAZADA" && (
        <Aviso tipo="error" texto={`Rechazada por riesgo: ${prestamo.motivo || "evaluación desfavorable"}.`} />
      )}
      {prestamo.estado === "CANCELADA" && prestamo.motivo && (
        <Aviso tipo="info" texto={`Cancelada: ${prestamo.motivo}`} />
      )}

      <div className="panel" style={{ marginTop: "1rem" }}>
        <h2 style={{ margin: 0 }}>Decisión de riesgo</h2>
        <div className="fila">
          <Dato etiqueta="Probabilidad de incumplimiento" valor={`${(prestamo.probabilidad_incumplimiento * 100).toFixed(2)} %`} />
          <Dato etiqueta="Umbral del modelo" valor={`${(prestamo.umbral * 100).toFixed(0)} %`} />
          <Dato etiqueta="Versión del modelo" valor={prestamo.modelo_version} />
        </div>
        <div className="fila">
          <Dato etiqueta="Cuota mensual" valor={cop(prestamo.cuota_mensual_cop)} />
          <Dato etiqueta="Tasa mensual" valor={`${(prestamo.tasa_mensual * 100).toFixed(2)} %`} />
          <Dato etiqueta="Monto total" valor={cop(prestamo.monto_total_cop)} />
        </div>
        <div className="fila">
          <Dato etiqueta="Precio unitario usado" valor={cop(prestamo.precio_unitario_cop)} />
          <Dato etiqueta="Versión del precio" valor={String(prestamo.precio_producto_version)} />
          <Dato etiqueta="Reserva" valor={prestamo.reserva_id || "sin reserva"} />
        </div>
        <div className="fila">
          <Dato etiqueta="Producto" valor={prestamo.producto_id} />
          <Dato etiqueta="Cantidad · plazo" valor={`${prestamo.cantidad} · ${prestamo.plazo_meses} meses`} />
          <Dato etiqueta="Creada" valor={fecha(prestamo.creado_en)} />
        </div>
        {prestamo.motivo && (
          <p className="meta"><strong>Motivo:</strong> {prestamo.motivo}</p>
        )}
      </div>

      {esMia && cancelable && (
        <div style={{ marginTop: "1rem" }}>
          <button className="peligro" disabled={cancelando} onClick={cancelar}>
            {cancelando ? "Cancelando…" : prestamo.estado === "APROBADA" ? "Cancelar y liberar reserva" : "Cancelar solicitud"}
          </button>
        </div>
      )}
    </>
  );
}

function Dato({ etiqueta, valor }) {
  return (
    <div className="campo" style={{ flex: 1, minWidth: 180 }}>
      <span className="meta">{etiqueta}</span>
      <strong>{valor}</strong>
    </div>
  );
}
