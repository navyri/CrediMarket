import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { cop, llamar } from "../api.js";
import { Aviso, Cargando, Vacio, mensajeError } from "../componentes.jsx";
import { useSesion } from "../sesion.jsx";

/**
 * Catálogo (§10): listado y detalle con precio; el cliente elige cantidad y
 * plazo para solicitar financiación. El navegador NUNCA envía precio ni tasa
 * (§4): el precio definitivo lo fija el sistema en la decisión.
 */
export default function Catalogo() {
  const { esAdmin, activa, clienteId } = useSesion();
  const navegar = useNavigate();
  const [productos, setProductos] = useState(null);
  const [error, setError] = useState(null);
  const [aviso, setAviso] = useState(null);

  const cargar = useCallback(async () => {
    try {
      const respuesta = await llamar("productos", "/productos?pagina=1&tamano=50");
      setProductos(respuesta.items);
      setError(null);
    } catch (exc) {
      setError(mensajeError(exc));
      setProductos([]);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  return (
    <>
      <h1>Catálogo de productos</h1>
      <p className="subtitulo">
        Seleccione un producto, la cantidad y el plazo: el precio y la tasa los calcula el sistema
        con la cotización oficial de Productos.
      </p>
      <Aviso tipo="ok" texto={aviso} onCerrar={() => setAviso(null)} />
      <Aviso tipo="error" texto={error} />
      {productos === null && <Cargando texto="Cargando productos…" />}
      {productos?.length === 0 && <Vacio texto="No hay productos publicados." />}

      {esAdmin && <PanelProducto onCreado={() => { setAviso("Producto creado."); cargar(); }} />}

      <div className="rejilla" style={{ marginTop: esAdmin ? "1.2rem" : 0 }}>
        {productos?.map((p) => (
          <TarjetaProducto
            key={p.id}
            producto={p}
            esAdmin={esAdmin}
            clienteId={clienteId}
            puedeSolicitar={activa && !esAdmin && Boolean(clienteId)}
            onCambio={() => { setAviso("Producto actualizado (versión nueva, caché invalidada)."); cargar(); }}
            onSolicitado={(id) => navegar(`/solicitudes/${id}`)}
            onAviso={setAviso}
          />
        ))}
      </div>
    </>
  );
}

function TarjetaProducto({ producto, esAdmin, clienteId, puedeSolicitar, onCambio, onSolicitado, onAviso }) {
  const [cantidad, setCantidad] = useState(1);
  const [plazo, setPlazo] = useState(12);
  // Clave de idempotencia (§9): se genera al solicitar y se CONSERVA si el
  // reintento falla, para que un envío repetido no duplique la solicitud.
  const [clave, setClave] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  const [precio, setPrecio] = useState("");

  const solicitar = async (event) => {
    event.preventDefault();
    setEnviando(true);
    setError(null);
    const claveSolicitud = clave || crypto.randomUUID();
    setClave(claveSolicitud);
    try {
      const respuesta = await llamar("prestamos", "/prestamos", {
        metodo: "POST",
        cabeceras: { "Idempotency-Key": claveSolicitud },
        cuerpo: { cliente_id: clienteId, producto_id: producto.id, cantidad, plazo_meses: plazo },
      });
      setClave(null);                    // ya confirmada: la próxima nace nueva
      onSolicitado(respuesta.prestamo_id ?? respuesta.id);
    } catch (exc) {
      // La clave queda intacta: "Reintentar" reenvía la MISMA solicitud (§9).
      setError(mensajeError(exc));
    } finally {
      setEnviando(false);
    }
  };

  const guardarPrecio = async (e) => {
    e.preventDefault();
    try {
      await llamar("productos", `/productos/${producto.id}`, {
        metodo: "PATCH",
        cuerpo: { precio_cop: Number(precio) },
      });
      setPrecio("");
      onCambio();
    } catch (exc) {
      onAviso?.(null);
      setError(mensajeError(exc));
    }
  };

  const desactivar = async () => {
    try {
      await llamar("productos", `/productos/${producto.id}/desactivar`, { metodo: "POST" });
      onCambio();
    } catch (exc) {
      setError(mensajeError(exc));
    }
  };

  return (
    <article className="tarjeta">
      <h3>{producto.nombre}</h3>
      <span className="precio">{cop(producto.precio_cop)}</span>
      <span className="meta">
        {producto.categoria} · SKU {producto.sku} · versión {producto.version} ·{" "}
        {producto.activo ? "activo" : "inactivo"}
      </span>
      <p className="meta">{producto.descripcion || "Sin descripción."}</p>

      {error && <Aviso tipo="error" texto={error} />}

      {puedeSolicitar && (
        <form onSubmit={solicitar} className="fila" style={{ alignItems: "flex-end" }}>
          <div className="campo">
            <label htmlFor={`cant-${producto.id}`}>Cantidad</label>
            <input id={`cant-${producto.id}`} type="number" min="1" max="1000" value={cantidad}
                   onChange={(e) => setCantidad(Number(e.target.value))} required />
          </div>
          <div className="campo">
            <label htmlFor={`plazo-${producto.id}`}>Plazo (meses)</label>
            <input id={`plazo-${producto.id}`} type="number" min="1" max="60" value={plazo}
                   onChange={(e) => setPlazo(Number(e.target.value))} required />
          </div>
          <button type="submit" disabled={enviando || !producto.activo}>
            {clave ? "Reintentar solicitud" : "Solicitar financiación"}
          </button>
        </form>
      )}
      {puedeSolicitar && clave && (
        <span className="meta">
          Envío previo sin confirmar: al reintentar se conserva la misma clave de idempotencia
          para no duplicar la solicitud.
        </span>
      )}

      {esAdmin && (
        <>
          <form onSubmit={guardarPrecio} className="fila" style={{ alignItems: "flex-end" }}>
            <div className="campo">
              <label htmlFor={`precio-${producto.id}`}>Nuevo precio (COP)</label>
              <input id={`precio-${producto.id}`} type="number" min="1" value={precio}
                     onChange={(e) => setPrecio(e.target.value)} placeholder={String(producto.precio_cop)} />
            </div>
            <button type="submit" className="secundario" disabled={!precio}>Actualizar precio</button>
          </form>
          {producto.activo && (
            <button type="button" className="peligro mini" onClick={desactivar}>Desactivar producto</button>
          )}
        </>
      )}
    </article>
  );
}

function PanelProducto({ onCreado }) {
  const [abierto, setAbierto] = useState(false);
  const [datos, setDatos] = useState({ sku: "", nombre: "", categoria: "", descripcion: "", precio_cop: "" });
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const campo = (k) => ({ value: datos[k], onChange: (e) => setDatos({ ...datos, [k]: e.target.value }) });

  const crear = async (e) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await llamar("productos", "/productos", {
        metodo: "POST",
        cuerpo: { ...datos, precio_cop: Number(datos.precio_cop) },
      });
      setDatos({ sku: "", nombre: "", categoria: "", descripcion: "", precio_cop: "" });
      setAbierto(false);
      onCreado();
    } catch (exc) {
      setError(mensajeError(exc));
    } finally {
      setEnviando(false);
    }
  };

  if (!abierto) return <button className="secundario" onClick={() => setAbierto(true)}>＋ Nuevo producto</button>;
  return (
    <form className="panel" onSubmit={crear} style={{ marginTop: "1rem" }}>
      <h3 style={{ margin: 0 }}>Nuevo producto</h3>
      <Aviso tipo="error" texto={error} />
      <div className="fila">
        <div className="campo"><label>SKU *</label><input required {...campo("sku")} /></div>
        <div className="campo"><label>Nombre *</label><input required {...campo("nombre")} /></div>
        <div className="campo"><label>Categoría *</label><input required {...campo("categoria")} /></div>
      </div>
      <div className="fila">
        <div className="campo"><label>Precio (COP) *</label>
          <input type="number" min="1" required {...campo("precio_cop")} /></div>
        <div className="campo"><label>Descripción</label><input {...campo("descripcion")} /></div>
      </div>
      <div className="fila">
        <button type="submit" disabled={enviando}>{enviando ? "Creando…" : "Crear"}</button>
        <button type="button" className="secundario" onClick={() => setAbierto(false)}>Cancelar</button>
      </div>
    </form>
  );
}
