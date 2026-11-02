import { useCallback, useEffect, useState } from "react";
import { fecha, llamar } from "../api.js";
import { Aviso, Cargando, Vacio, mensajeError } from "../componentes.jsx";
import { useSesion } from "../sesion.jsx";

const CAMPOS = [
  ["nombre", "Nombre", "text"], ["email", "Correo", "email"],
  ["telefono", "Teléfono", "text"], ["ciudad", "Ciudad", "text"],
  ["ingresos_mensuales_cop", "Ingresos (COP)", "number"],
  ["obligaciones_mensuales_cop", "Obligaciones (COP)", "number"],
  ["tipo_empleo", "Tipo de empleo", "text"],
  ["antiguedad_laboral_meses", "Antigüedad (meses)", "number"],
  ["meses_historial_crediticio", "Historial (meses)", "number"],
  ["creditos_previos", "Créditos previos", "number"],
  ["atrasos_previos_30d", "Atrasos (30d)", "number"],
  ["porcentaje_pago_puntual", "Pago puntual (%)", "number"],
];

/** Vista administrativa de clientes (§10): consultar, editar e importar el CSV. */
export default function Clientes() {
  const { esAdmin } = useSesion();
  const [clientes, setClientes] = useState(null);
  const [error, setError] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [seleccion, setSeleccion] = useState(null);

  const cargar = useCallback(async () => {
    try {
      const respuesta = await llamar("clientes", "/clientes");
      setClientes(respuesta.items);
      setError(null);
    } catch (exc) {
      setError(mensajeError(exc));
      setClientes([]);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  if (!esAdmin) return <Aviso tipo="error" texto="Sección reservada a administradores." />;

  return (
    <>
      <h1>Clientes</h1>
      <p className="subtitulo">
        Fichas de clientes con su perfil financiero. La importación usa el documento de identidad
        como clave única: importar dos veces el mismo archivo no duplica clientes (§12.12).
      </p>
      <Aviso tipo="ok" texto={aviso} onCerrar={() => setAviso(null)} />
      <Aviso tipo="error" texto={error} />

      <Importacion onListo={(resumen) => { setAviso(`Importación: ${resumen.procesadas} procesadas · ${resumen.insertados} insertadas · ${resumen.actualizados} actualizadas · ${resumen.sin_cambios} sin cambios · ${resumen.rechazadas} rechazadas.`); cargar(); }} />

      <h2>Editar ficha y perfil financiero</h2>
      <div className="fila" style={{ alignItems: "flex-end" }}>
        <div className="campo" style={{ maxWidth: 420 }}>
          <label htmlFor="cliente-sel">Cliente</label>
          <select id="cliente-sel" value={seleccion?.id || ""}
                  onChange={(e) => setSeleccion(clientes?.find((c) => c.id === e.target.value) || null)}>
            <option value="">— Seleccione —</option>
            {clientes?.map((c) => (
              <option key={c.id} value={c.id}>{c.nombre} · {c.documento_identidad}</option>
            ))}
          </select>
        </div>
      </div>
      {seleccion && (
        <FormularioCliente
          key={seleccion.id}
          cliente={seleccion}
          onGuardado={(mensaje) => { setAviso(mensaje); setSeleccion(null); cargar(); }}
        />
      )}

      <h2>Directorio</h2>
      {clientes === null && <Cargando texto="Cargando clientes…" />}
      {clientes?.length === 0 && <Vacio texto="No hay clientes registrados." />}
      {clientes?.length > 0 && (
        <table className="tabla">
          <thead>
            <tr><th>Nombre</th><th>Documento</th><th>Correo</th><th>Ciudad</th><th>Perfil financiero</th><th>Estado</th></tr>
          </thead>
          <tbody>
            {clientes.map((c) => (
              <tr key={c.id}>
                <td>{c.nombre}</td>
                <td>{c.documento_identidad}</td>
                <td>{c.email}</td>
                <td>{c.ciudad || "—"}</td>
                <td className="meta">
                  {c.ingresos_mensuales_cop
                    ? `ingresos ${Number(c.ingresos_mensuales_cop).toLocaleString("es-CO")} · ${c.tipo_empleo || "—"}`
                    : "sin perfil"}
                </td>
                <td><span className={`insignia ${c.activo ? "ok" : "error"}`}>{c.activo ? "Activo" : "Inactivo"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function FormularioCliente({ cliente, onGuardado }) {
  const [datos, setDatos] = useState(cliente);
  const [error, setError] = useState(null);
  const [guardando, setGuardando] = useState(false);
  const campo = (k) => ({
    value: datos[k] ?? "",
    onChange: (e) => setDatos({ ...datos, [k]: e.target.value }),
  });

  const guardar = async (e) => {
    e.preventDefault();
    setGuardando(true);
    setError(null);
    try {
      const cuerpo = {};
      CAMPOS.forEach(([k, , tipo]) => {
        const actual = datos[k];
        const original = cliente[k];
        if (actual === original || actual === "" || actual === undefined) return;
        cuerpo[k] = tipo === "number" ? Number(actual) : actual;
      });
      await llamar("clientes", `/clientes/${cliente.id}`, { metodo: "PATCH", cuerpo });
      onGuardado(`Ficha de ${cliente.nombre} actualizada.`);
    } catch (exc) {
      setError(mensajeError(exc));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <form className="panel" onSubmit={guardar}>
      <strong>{cliente.nombre} · {cliente.id}</strong>
      <span className="meta">Registrado {fecha(cliente.creado_en)} · última actualización {fecha(cliente.actualizado_en)}</span>
      <Aviso tipo="error" texto={error} />
      <div className="fila">
        {CAMPOS.map(([k, etiqueta, tipo]) => (
          <div className="campo" key={k}>
            <label>{etiqueta}</label>
            <input type={tipo} step="any" min="0" {...campo(k)} />
          </div>
        ))}
      </div>
      <button disabled={guardando}>{guardando ? "Guardando…" : "Guardar ficha"}</button>
    </form>
  );
}

function Importacion({ onListo }) {
  const [archivo, setArchivo] = useState(null);
  const [error, setError] = useState(null);
  const [resumen, setResumen] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e) => {
    e.preventDefault();
    if (!archivo) { setError("Seleccione el archivo CSV de clientes."); return; }
    setEnviando(true);
    setError(null);
    setResumen(null);
    try {
      const form = new FormData();
      form.append("file", archivo);
      const respuesta = await llamar("clientes", "/clientes/import", { metodo: "POST", formData: form });
      setResumen(respuesta);
      onListo(respuesta);
    } catch (exc) {
      setError(mensajeError(exc));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form className="panel" onSubmit={enviar}>
      <h2 style={{ margin: 0 }}>Importar clientes (CSV)</h2>
      <Aviso tipo="error" texto={error} />
      <div className="fila" style={{ alignItems: "flex-end" }}>
        <div className="campo" style={{ flex: 2 }}>
          <label htmlFor="csv">Archivo CSV (con encabezados del histórico)</label>
          <input id="csv" type="file" accept=".csv,text/csv"
                 onChange={(e) => setArchivo(e.target.files?.[0] || null)} />
        </div>
        <button type="submit" disabled={enviando}>{enviando ? "Importando…" : "Importar"}</button>
      </div>
      {resumen && (
        <>
          <div className="fila">
            <ResumenDato etiqueta="Procesadas" valor={resumen.procesadas} />
            <ResumenDato etiqueta="Insertadas" valor={resumen.insertados} />
            <ResumenDato etiqueta="Actualizadas" valor={resumen.actualizados} />
            <ResumenDato etiqueta="Sin cambios" valor={resumen.sin_cambios} />
            <ResumenDato etiqueta="Rechazadas" valor={resumen.rechazadas} />
          </div>
          {resumen.errores?.length > 0 && (
            <table className="tabla">
              <thead><tr><th>Fila</th><th>Motivo</th></tr></thead>
              <tbody>
                {resumen.errores.slice(0, 20).map((e) => (
                  <tr key={e.fila}><td>{e.fila}</td><td>{e.motivo}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </form>
  );
}

function ResumenDato({ etiqueta, valor }) {
  return (
    <div className="campo" style={{ minWidth: 110 }}>
      <span className="meta">{etiqueta}</span>
      <strong>{valor}</strong>
    </div>
  );
}
