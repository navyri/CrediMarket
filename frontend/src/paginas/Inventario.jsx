import { useCallback, useEffect, useState } from "react";
import { fecha, llamar } from "../api.js";
import { Aviso, Cargando, Vacio, mensajeError } from "../componentes.jsx";

/** Inventario (§10, solo administrador): existencias, reservas, movimientos y entradas. */
export default function Inventario() {
  const [existencias, setExistencias] = useState(null);
  const [reservas, setReservas] = useState(null);
  const [movimientos, setMovimientos] = useState(null);
  const [nombres, setNombres] = useState({});
  const [error, setError] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [ocupado, setOcupado] = useState(false);

  const nombreDe = (id) => nombres[id] || `${id.slice(0, 8)}…`;

  const cargar = useCallback(async () => {
    try {
      const [e, r, m, p] = await Promise.all([
        llamar("inventario", "/existencias"),
        llamar("inventario", "/reservas?limite=50"),
        llamar("inventario", "/movimientos?limite=50"),
        llamar("productos", "/productos?pagina=1&tamano=100").catch(() => ({ items: [] })),
      ]);
      setExistencias(e);
      setReservas(r);
      setMovimientos(m);
      setNombres(Object.fromEntries(p.items.map((prod) => [prod.id, prod.nombre])));
      setError(null);
    } catch (exc) {
      setError(mensajeError(exc));
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const ejecutar = async (etiqueta, accion) => {
    setOcupado(true);
    setError(null);
    try {
      await accion();
      setAviso(etiqueta);
      await cargar();
    } catch (exc) {
      setError(mensajeError(exc));
    } finally {
      setOcupado(false);
    }
  };

  const entregar = (id) => ejecutar(`Entrega confirmada de la reserva ${id.slice(0, 8)}…: salió el stock y el préstamo pasa a COMPLETADA.`, () =>
    llamar("inventario", `/reservas/${id}/entrega`, { metodo: "POST" }));

  const liberar = (id) => ejecutar(`Reserva ${id.slice(0, 8)}… liberada: el stock vuelve a estar disponible.`, () =>
    llamar("inventario", `/reservas/${id}/liberar`, { metodo: "POST" }));

  return (
    <>
      <h1>Inventario</h1>
      <p className="subtitulo">
        Las reservas NO se crean por esta interfaz: llegan desde Préstamos por el broker con
        transacción atómica. Aquí se confirman entregas y se libera stock.
      </p>
      <Aviso tipo="ok" texto={aviso} onCerrar={() => setAviso(null)} />
      <Aviso tipo="error" texto={error} />

      <PanelEntrada onRegistrado={(msg) => { setAviso(msg); cargar(); }} />

      <h2>Existencias</h2>
      {existencias === null && <Cargando texto="Cargando existencias…" />}
      {existencias?.length === 0 && <Vacio texto="Sin existencias registradas; registre una entrada." />}
      {existencias?.length > 0 && (
        <table className="tabla">
          <thead><tr><th>Producto</th><th>Total</th><th>Reservada</th><th>Disponible</th><th>Actualizado</th></tr></thead>
          <tbody>
            {existencias.map((e) => (
              <tr key={e.producto_id}>
                <td>{nombreDe(e.producto_id)}</td>
                <td>{e.total}</td>
                <td>{e.reservada}</td>
                <td><strong>{e.disponible}</strong></td>
                <td className="meta">{fecha(e.actualizado_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Reservas</h2>
      {reservas?.length === 0 && <Vacio texto="No hay reservas." />}
      {reservas?.length > 0 && (
        <table className="tabla">
          <thead><tr><th>Reserva</th><th>Préstamo</th><th>Producto</th><th>Cant.</th><th>Estado</th><th>Vence</th><th>Acciones</th></tr></thead>
          <tbody>
            {reservas.map((r) => (
              <tr key={r.id}>
                <td>{r.id.slice(0, 8)}…</td>
                <td>{r.prestamo_id.slice(0, 8)}…</td>
                <td>{nombreDe(r.producto_id)}</td>
                <td>{r.cantidad}</td>
                <td>
                  <span className={`insignia ${r.estado === "RESERVADA" ? "proceso" : r.estado === "ENTREGADA" ? "ok" : ""}`}>
                    {r.estado}
                  </span>
                </td>
                <td className="meta">{fecha(r.vence_en)}</td>
                <td>
                  {r.estado === "RESERVADA" && (
                    <>
                      <button className="mini" disabled={ocupado} onClick={() => entregar(r.id)}>Entregar</button>{" "}
                      <button className="mini secundario" disabled={ocupado} onClick={() => liberar(r.id)}>Liberar</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Movimientos</h2>
      {movimientos?.length === 0 && <Vacio texto="Sin movimientos." />}
      {movimientos?.length > 0 && (
        <table className="tabla">
          <thead><tr><th>Tipo</th><th>Producto</th><th>Cant.</th><th>Referencia</th><th>Fecha</th></tr></thead>
          <tbody>
            {movimientos.map((m) => (
              <tr key={m.id}>
                <td><span className="insignia">{m.tipo}</span></td>
                <td>{nombreDe(m.producto_id)}</td>
                <td>{m.cantidad}</td>
                <td className="meta">{m.referencia || "—"}</td>
                <td className="meta">{fecha(m.creado_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function PanelEntrada({ onRegistrado }) {
  const [datos, setDatos] = useState({ producto_id: "", cantidad: "", referencia: "" });
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const campo = (k) => ({ value: datos[k], onChange: (e) => setDatos({ ...datos, [k]: e.target.value }) });

  const enviar = async (e) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await llamar("inventario", "/entradas", {
        metodo: "POST",
        cuerpo: {
          producto_id: datos.producto_id,
          cantidad: Number(datos.cantidad),
          ...(datos.referencia && { referencia: datos.referencia }),
        },
      });
      setDatos({ producto_id: "", cantidad: "", referencia: "" });
      onRegistrado(`Entrada registrada: +${datos.cantidad} unidades.`);
    } catch (exc) {
      setError(mensajeError(exc));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form className="panel" onSubmit={enviar}>
      <h2 style={{ margin: 0 }}>Registrar entrada de stock</h2>
      <Aviso tipo="error" texto={error} />
      <div className="fila">
        <div className="campo">
          <label>ID del producto</label>
          <input required placeholder="5e819ef2-…" {...campo("producto_id")} />
        </div>
        <div className="campo">
          <label>Cantidad</label>
          <input type="number" min="1" max="100000" required {...campo("cantidad")} />
        </div>
        <div className="campo">
          <label>Referencia</label>
          <input placeholder="nota de compra" {...campo("referencia")} />
        </div>
        <button type="submit" disabled={enviando}>{enviando ? "Registrando…" : "Registrar entrada"}</button>
      </div>
    </form>
  );
}
