import { useEffect, useState } from "react";
import { llamar } from "../api.js";
import { Aviso, Cargando, mensajeError } from "../componentes.jsx";
import { useSesion } from "../sesion.jsx";

// El 4.º elemento marca los campos obligatorios (NOT NULL en la base): nunca
// se envían vacíos, porque el backend los rechaza con 400.
const CAMPOS_DATOS = [
  ["nombre", "Nombre", "text", true],
  ["email", "Correo electrónico", "email", true],
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

/** Compara lo tecleado con lo guardado sin distinguir `""` de `null` ni
 *  número de su texto: un campo intacto no viaja en el PATCH. */
const mismo = (a, b) => String(a ?? "") === String(b ?? "");

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
      // Un campo vacío limpia el valor (null) en vez de mandar "": el backend
      // rechaza la cadena vacía con 400. Los obligatorios (nombre/email) no se
      // envían vacíos; además el formulario los exige con `required`.
      CAMPOS_DATOS.forEach(([k, , , obligatorio]) => {
        if (datos[k] === undefined || mismo(datos[k], cliente[k])) return;
        if (datos[k] === "" && obligatorio) return;
        cuerpo[k] = datos[k] === "" ? null : datos[k];
      });
      CAMPOS_PERFIL.forEach(([k, , tipo]) => {
        if (datos[k] === undefined || mismo(datos[k], cliente[k])) return;
        if (datos[k] === "") { cuerpo[k] = null; return; }
        cuerpo[k] = tipo === "number" ? Number(datos[k]) : datos[k];
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
            {CAMPOS_DATOS.map(([k, etiqueta, tipo, obligatorio]) => (
              <div className="campo" key={k}>
                <label>{etiqueta}</label>
                <input type={tipo} required={Boolean(obligatorio)} {...campo(k)} />
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
