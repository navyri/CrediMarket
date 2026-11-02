import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { llamar } from "../api.js";
import { Aviso, mensajeError } from "../componentes.jsx";
import { useSesion } from "../sesion.jsx";

const VACIO = { email: "", password: "", documento_identidad: "", nombre: "", telefono: "", ciudad: "" };

export default function InicioSesion() {
  const { iniciar } = useSesion();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const [modo, setModo] = useState("login");
  const [datos, setDatos] = useState(VACIO);
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const campo = (clave) => ({
    value: datos[clave],
    onChange: (e) => setDatos({ ...datos, [clave]: e.target.value }),
  });

  const enviar = async (e) => {
    e.preventDefault();
    setError(null);
    if (modo === "registro" && (!datos.email || datos.password.length < 8 || !datos.documento_identidad || !datos.nombre)) {
      setError("Complete los campos obligatorios (la contraseña requiere al menos 8 caracteres).");
      return;
    }
    setEnviando(true);
    try {
      const respuesta = modo === "login"
        ? await llamar("clientes", "/auth/token", { metodo: "POST", cuerpo: { email: datos.email, password: datos.password } })
        : await llamar("clientes", "/auth/registro", {
            metodo: "POST",
            cuerpo: {
              email: datos.email,
              password: datos.password,
              documento_identidad: datos.documento_identidad,
              nombre: datos.nombre,
              ...(datos.telefono && { telefono: datos.telefono }),
              ...(datos.ciudad && { ciudad: datos.ciudad }),
            },
          });
      iniciar(respuesta.access_token, respuesta.rol, respuesta.cliente_id);
      navegar(ubicacion.state?.desde || "/", { replace: true });
    } catch (exc) {
      setError(mensajeError(exc));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="login-caja">
      <p className="login-marca">Credi<span>Market</span></p>
      <p className="subtitulo" style={{ textAlign: "center" }}>
        Financiamiento de productos con decisión de riesgo y reserva de inventario real.
      </p>
      <div className="tabs">
        <button type="button" className={modo === "login" ? "activo" : ""} onClick={() => { setModo("login"); setError(null); }}>
          Iniciar sesión
        </button>
        <button type="button" className={modo === "registro" ? "activo" : ""} onClick={() => { setModo("registro"); setError(null); }}>
          Crear cuenta
        </button>
      </div>
      <form className="panel" onSubmit={enviar}>
        <Aviso tipo="error" texto={error} />
        {modo === "registro" && (
          <>
            <div className="campo">
              <label htmlFor="nombre">Nombre *</label>
              <input id="nombre" required {...campo("nombre")} />
            </div>
            <div className="campo">
              <label htmlFor="doc">Documento de identidad *</label>
              <input id="doc" required {...campo("documento_identidad")} />
              <span className="ayuda">Clave única de su ficha; no se duplica al importar datos.</span>
            </div>
          </>
        )}
        <div className="campo">
          <label htmlFor="email">Correo electrónico *</label>
          <input id="email" type="email" required autoComplete="username" {...campo("email")} />
        </div>
        <div className="campo">
          <label htmlFor="password">Contraseña *</label>
          <input id="password" type="password" required minLength={8} autoComplete={modo === "login" ? "current-password" : "new-password"} {...campo("password")} />
          {modo === "registro" && <span className="ayuda">Mínimo 8 caracteres.</span>}
        </div>
        {modo === "registro" && (
          <div className="fila">
            <div className="campo">
              <label htmlFor="tel">Teléfono</label>
              <input id="tel" {...campo("telefono")} />
            </div>
            <div className="campo">
              <label htmlFor="ciudad">Ciudad</label>
              <input id="ciudad" {...campo("ciudad")} />
            </div>
          </div>
        )}
        <button disabled={enviando}>{enviando ? "Enviando…" : modo === "login" ? "Entrar" : "Crear cuenta y entrar"}</button>
      </form>
    </div>
  );
}
