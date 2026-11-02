import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cop, fecha, llamar } from "../api.js";
import { Aviso, Cargando, InsigniaEstado, Vacio, mensajeError } from "../componentes.jsx";
import { useSesion } from "../sesion.jsx";

/** Seguimiento (§10): solicitudes con estado, resultado de la evaluación y motivo. */
export default function Solicitudes() {
  const { esAdmin } = useSesion();
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);

  const cargar = useCallback(async () => {
    try {
      const respuesta = await llamar("prestamos", "/prestamos?pagina=1&tamano=50");
      setDatos(respuesta);
      setError(null);
    } catch (exc) {
      setError(mensajeError(exc));
      setDatos({ items: [] });
    }
  }, []);

  useEffect(() => {
    cargar();
    const reloj = setInterval(cargar, 5000);   // la lista también se refresca (§10)
    return () => clearInterval(reloj);
  }, [cargar]);

  return (
    <>
      <h1>{esAdmin ? "Solicitudes de préstamo" : "Mis solicitudes"}</h1>
      <p className="subtitulo">
        Estado y resultado de la evaluación de riesgo. Un resultado favorable del modelo NO es la
        aprobación final: la aprobación ocurre cuando Inventario confirma la reserva.
      </p>
      <Aviso tipo="error" texto={error} />
      {datos === null && <Cargando texto="Cargando solicitudes…" />}
      {datos?.items?.length === 0 && <Vacio texto="Aún no hay solicitudes; solicite financiación desde el catálogo." />}
      {datos?.items?.length > 0 && (
        <table className="tabla">
          <thead>
            <tr>
              <th>Solicitud</th><th>Producto</th><th>Monto</th><th>Riesgo</th><th>Estado</th><th>Creada</th>
            </tr>
          </thead>
          <tbody>
            {datos.items.map((p) => (
              <tr key={p.id}>
                <td><Link to={`/solicitudes/${p.id}`}>{p.id.slice(0, 8)}…</Link></td>
                <td>{p.producto_id.slice(0, 8)}… × {p.cantidad}<br />
                  <span className="meta">{p.plazo_meses} meses</span></td>
                <td>{cop(p.monto_total_cop)}<br />
                  <span className="meta">cuota {cop(p.cuota_mensual_cop)}</span></td>
                <td>{(p.probabilidad_incumplimiento * 100).toFixed(1)}%<br />
                  <span className="meta">umbral {(p.umbral * 100).toFixed(0)}% · {p.modelo_version}</span></td>
                <td><InsigniaEstado estado={p.estado} /></td>
                <td className="meta">{fecha(p.creado_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
