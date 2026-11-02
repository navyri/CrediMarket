// Cliente HTTP de CrediMarket (§10).
//
// El navegador se comunica SOLO con las APIs autorizadas de los 4 servicios:
// las URLs salen de variables de entorno del build (VITE_API_*) y aquí no hay
// secretos: el único credential es el JWT del usuario en `Authorization`.
const BASES = {
  productos: import.meta.env.VITE_API_PRODUCTOS || "http://localhost:8001",
  clientes: import.meta.env.VITE_API_CLIENTES || "http://localhost:8002",
  prestamos: import.meta.env.VITE_API_PRESTAMOS || "http://localhost:8003",
  inventario: import.meta.env.VITE_API_INVENTARIO || "http://localhost:8004",
};

export const MLFLOW_URL = import.meta.env.VITE_MLFLOW_URL || "http://localhost:5000";

export const CLAVES = {
  token: "credimarket.token",
  rol: "credimarket.rol",
  cliente: "credimarket.cliente_id",
};

export const EVENTO_SESION_VENCIDA = "credimarket:sesion-vencida";

/** Error de API: conserva status, detail y los errores por campo del problem+json. */
export class ErrorApi extends Error {
  constructor(status, titulo, detalle, errores) {
    super(detalle || titulo || `error ${status}`);
    this.status = status;
    this.titulo = titulo || "Error";
    this.errores = errores || [];
  }
}

function tokenActual() {
  return localStorage.getItem(CLAVES.token);
}

export function tokenVigente() {
  const token = tokenActual();
  if (!token) return false;
  try {
    const cuerpo = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return cuerpo.exp * 1000 > Date.now();
  } catch {
    return false; // token ilegible → se trata como vencido
  }
}

export function cerrarSesionLocal() {
  Object.values(CLAVES).forEach((clave) => localStorage.removeItem(clave));
}

/**
 * Llamada autenticada a un servicio.
 * - `cuerpo` se serializa como JSON; `formData` se envía tal cual (import CSV).
 * - `Idempotency-Key` se pasa en `cabeceras` para POST /prestamos (§9).
 * - 401 → sesión vencida: se limpia la sesión local y se avisa a la app.
 */
export async function llamar(servicio, ruta, opciones = {}) {
  const { metodo = "GET", cuerpo, formData, cabeceras = {} } = opciones;
  const cab = { ...cabeceras };
  const token = tokenActual();
  if (token) cab.Authorization = `Bearer ${token}`;

  let body;
  if (formData) {
    body = formData;
  } else if (cuerpo !== undefined) {
    cab["Content-Type"] = "application/json";
    body = JSON.stringify(cuerpo);
  }

  let respuesta;
  try {
    respuesta = await fetch(`${BASES[servicio]}${ruta}`, { method: metodo, headers: cab, body });
  } catch {
    throw new ErrorApi(0, "Servicio no disponible",
      `No se pudo contactar al servicio ${servicio}. Verifique que docker compose esté levantado.`);
  }

  if (respuesta.status === 401) {
    cerrarSesionLocal();
    window.dispatchEvent(new CustomEvent(EVENTO_SESION_VENCIDA));
    throw new ErrorApi(401, "Sesión vencida", "Su sesión expiró; vuelva a iniciar sesión.");
  }

  if (respuesta.status === 204) return null;

  const tipo = respuesta.headers.get("content-type") || "";
  const json = tipo.includes("application/json") ? await respuesta.json() : null;

  if (!respuesta.ok) {
    const detalle = tipo.includes("problem+json")
      ? (Array.isArray(json?.errors) && json.errors.length
          ? json.errors.map((e) => `${e.campo ?? ""} ${e.mensaje ?? e.detail ?? ""}`.trim()).join(" · ")
          : json?.detail)
      : json?.detail;
    throw new ErrorApi(respuesta.status, json?.title, detalle || respuesta.statusText,
      Array.isArray(json?.errors) ? json.errors : []);
  }
  return json;
}

/** Formatea pesos colombianos sin depender de librerías externas. */
export function cop(valor) {
  const numero = Number(valor);
  if (Number.isNaN(numero)) return valor;
  return new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 })
    .format(numero);
}

export function fecha(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
}
