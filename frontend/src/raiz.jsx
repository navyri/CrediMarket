import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useSesion } from "./sesion.jsx";
import InicioSesion from "./paginas/InicioSesion.jsx";
import Catalogo from "./paginas/Catalogo.jsx";
import Solicitudes from "./paginas/Solicitudes.jsx";
import SolicitudDetalle from "./paginas/SolicitudDetalle.jsx";
import Perfil from "./paginas/Perfil.jsx";
import Clientes from "./paginas/Clientes.jsx";
import Inventario from "./paginas/Inventario.jsx";
import Modelo from "./paginas/Modelo.jsx";

function ExigirSesion({ admin, children }) {
  const { activa, esAdmin } = useSesion();
  const ubicacion = useLocation();
  if (!activa) return <Navigate to="/login" state={{ desde: ubicacion.pathname }} replace />;
  if (admin && !esAdmin) return <Navigate to="/" replace />;
  return children;
}

function Cabecera() {
  const { activa, esAdmin, rol, clienteId, salir } = useSesion();
  if (!activa) return null;
  return (
    <header className="cabecera">
      <NavLink to="/" className="marca">Credi<span>Market</span></NavLink>
      <nav className="nav">
        <NavLink to="/" end>Catálogo</NavLink>
        <NavLink to="/solicitudes">Mis solicitudes</NavLink>
        <NavLink to="/perfil">Mi perfil</NavLink>
        {esAdmin && <NavLink to="/clientes">Clientes</NavLink>}
        {esAdmin && <NavLink to="/inventario">Inventario</NavLink>}
        {esAdmin && <NavLink to="/modelo">Modelo</NavLink>}
      </nav>
      <div className="sesion-cab">
        <span className="rol">{rol}{clienteId ? ` · ${clienteId.slice(0, 8)}` : ""}</span>
        <button className="secundario mini" onClick={salir}>Cerrar sesión</button>
      </div>
    </header>
  );
}

export default function Raiz() {
  const { activa } = useSesion();
  return (
    <>
      <Cabecera />
      <main className="contenido">
        <Routes>
          <Route path="/login" element={activa ? <Navigate to="/" replace /> : <InicioSesion />} />
          <Route path="/" element={<ExigirSesion><Catalogo /></ExigirSesion>} />
          <Route path="/solicitudes" element={<ExigirSesion><Solicitudes /></ExigirSesion>} />
          <Route path="/solicitudes/:id" element={<ExigirSesion><SolicitudDetalle /></ExigirSesion>} />
          <Route path="/perfil" element={<ExigirSesion><Perfil /></ExigirSesion>} />
          <Route path="/clientes" element={<ExigirSesion admin><Clientes /></ExigirSesion>} />
          <Route path="/inventario" element={<ExigirSesion admin><Inventario /></ExigirSesion>} />
          <Route path="/modelo" element={<ExigirSesion admin><Modelo /></ExigirSesion>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
