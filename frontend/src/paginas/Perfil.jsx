import { useEffect, useState } from "react";
import { llamar } from "../api.js";
import { Aviso, Cargando, mensajeError } from "../componentes.jsx";
import { useSesion } from "../sesion.jsx";

const CAMPOS_DATOS = [
  ["nombre", "Nombre", "text"],
  ["email", "Correo electrónico", "email"],
  ["telefono", "Teléfono", "text"],
  ["ciudad", "Ciudad", "text"],
];

const CAMPOS_PERFIL = [
  ["ingresos_mensuales_cop", "Ingresos mensuales (COP)", "number"],
  ["obligaciones_mensuales_cop", "Obligaciones mensuales (COP)", "number"],
  ["tipo_empleo", "Tipo de empleo", "text"],
  ["antiguedad_laboral_meses", "Antigüedad laboral (meses)", "number"],
  ["meses_historial_crediticio", "Meses de historial crediticio", "number"],
  ["creditos_previos", "Créditos previos", "number"],
  ["atrasos_previos_30d", "Atrasos previos (30d)", "number"],
  ["porcentaje_pago_puntual", "Pago puntual (%)", "number"],
];

/** Mi perfil (§10: edición de datos permitidos, dueño o administrador). */
export default function Perfil() {
  const { clienteId, esAdmin } = useSesion();
  const [cliente, setCliente] = useState(null);
  const [datos, setDatos] = useState({});
  const [error, setError] = useState(null);
  const [ok, setOk] = useState(null);
  const [guardando, setGuardando] = useState(false);

  const cargar = async () => {
    // La cuenta administradora no tiene ficha de cliente (cliente_id=None en
    // el JWT): sin esta guarda, "Mi perfil" pediría /clientes/null y
    // mostraría un 404 rojo en pantalla.
    if (!clienteId) { setCliente(null); setError(null); return; }
    try {
      const respuesta = await llamar("clientes", `/clientes/${clienteId}`);
      setCliente(respuesta);
      setDatos(respuesta);
      setError(null);
    } catch (exc) {
      setError(mensajeError(exc));
    }
  };

  useEffect(() => { cargar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const guardar = async (e) => {
    e.preventDefault();
    setGuardando(true);
    setOk(null);
    setError(null);
    try {
      const cuerpo = {};
      CAMPOS_DATOS.forEach(([k]) => { if (datos[k] !== undefined && datos[k] !== cliente[k]) cuerpo[k] = datos[k]; });
      CAMPOS_PERFIL.forEach(([k, , tipo]) => {
        if (datos[k] === undefined || datos[k] === cliente[k]) return;
        cuerpo[k] = tipo === "number" && datos[k] !== "" ? Number(datos[k]) : datos[k];
      });
      if (Object.keys(cuerpo).length === 0) { setOk("Sin cambios por guardar."); setGuardando(false); return; }
      const respuesta = await llamar("clientes", `/clientes/${clienteId}`, { metodo: "PATCH", cuerpo });
      setCliente(respuesta);
      setDatos(respuesta);
      setOk("Datos actualizados.");
    } catch (exc) {
      setError(mensajeError(exc));
    } finally {
      setGuardando(false);
    }
  };

  const campo = (k) => ({
    value: datos[k] ?? "",
    onChange: (e) => setDatos({ ...datos, [k]: e.target.value }),
  });

  if (!clienteId) {
    return (
      <>
        <h1>Mi perfil</h1>
        <p className="subtitulo">
          Sus datos y su perfil financiero viven en el servicio Clientes (dueño de sus datos);
          Préstamos los consume por API para evaluar el riesgo.
        </p>
        <div className="aviso info">
          Su cuenta de administradora no tiene ficha de cliente asociada: el
          perfil financiero pertenece a los clientes. Abra <strong>Clientes</strong> para
          ver o editar sus fichas.
        </div>
      </>
    );
  }

  if (!cliente && !error) return <Cargando texto="Cargando perfil…" />;

  return (
    <>
      <h1>Mi perfil</h1>
      <p className="subtitulo">
        Sus datos y su perfil financiero viven en el servicio Clientes (dueño de sus datos);
        Préstamos los consume por API para evaluar el riesgo.
      </p>
      <Aviso tipo="ok" texto={ok} onCerrar={() => setOk(null)} />
      <Aviso tipo="error" texto={error} />
      {cliente && (
        <form className="panel" onSubmit={guardar}>
          <div className="fila">
            <div className="campo"><label>Documento</label><input value={cliente.documento_identidad} disabled /></div>
            <div className="campo"><label>Identificador</label><input value={cliente.id} disabled /></div>
            <div className="campo"><label>Estado</label><input value={cliente.activo ? "Activo" : "Inactivo"} disabled /></div>
          </div>
          <div className="fila">
            {CAMPOS_DATOS.map(([k, etiqueta, tipo]) => (
              <div className="campo" key={k}>
                <label>{etiqueta}</label>
                <input type={tipo} {...campo(k)} />
              </div>
            ))}
          </div>
          <h2 style={{ margin: "0.4rem 0 0" }}>Perfil financiero (para la evaluación de riesgo)</h2>
          <div className="fila">
            {CAMPOS_PERFIL.map(([k, etiqueta, tipo]) => (
              <div className="campo" key={k}>
                <label>{etiqueta}</label>
                <input type={tipo} step="any" min="0" {...campo(k)} />
              </div>
            ))}
          </div>
          <button disabled={guardando}>{guardando ? "Guardando…" : "Guardar cambios"}</button>
          {esAdmin && <span className="meta">Edita su ficha con credenciales de administrador.</span>}
        </form>
      )}
    </>
  );
}
