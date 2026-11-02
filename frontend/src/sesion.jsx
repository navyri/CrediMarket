import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { CLAVES, EVENTO_SESION_VENCIDA, cerrarSesionLocal, tokenVigente } from "./api.js";

const Sesion = createContext(null);

/** Estado de sesión persistido en localStorage (token, rol y cliente_id del JWT). */
export function ProveedorSesion({ children }) {
  const [sesion, setSesion] = useState(() => ({
    token: localStorage.getItem(CLAVES.token),
    rol: localStorage.getItem(CLAVES.rol),
    clienteId: localStorage.getItem(CLAVES.cliente),
  }));

  const iniciar = useCallback((token, rol, clienteId) => {
    localStorage.setItem(CLAVES.token, token);
    localStorage.setItem(CLAVES.rol, rol);
    if (clienteId) localStorage.setItem(CLAVES.cliente, clienteId);
    else localStorage.removeItem(CLAVES.cliente);
    setSesion({ token, rol, clienteId: clienteId ?? null });
  }, []);

  const salir = useCallback(() => {
    cerrarSesionLocal();
    setSesion({ token: null, rol: null, clienteId: null });
  }, []);

  // El cliente HTTP avisa cuando el backend responde 401 (sesión vencida, §10).
  useEffect(() => {
    const alVencer = () => setSesion({ token: null, rol: null, clienteId: null });
    window.addEventListener(EVENTO_SESION_VENCIDA, alVencer);
    return () => window.removeEventListener(EVENTO_SESION_VENCIDA, alVencer);
  }, []);

  const activa = Boolean(sesion.token && tokenVigente());
  return (
    <Sesion.Provider value={{ ...sesion, activa, esAdmin: sesion.rol === "administrador", iniciar, salir }}>
      {children}
    </Sesion.Provider>
  );
}

export function useSesion() {
  return useContext(Sesion);
}
