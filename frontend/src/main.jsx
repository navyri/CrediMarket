import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ProveedorSesion } from "./sesion.jsx";
import Raiz from "./raiz.jsx";
import "./estilos.css";

createRoot(document.getElementById("raiz")).render(
  <StrictMode>
    <BrowserRouter>
      <ProveedorSesion>
        <Raiz />
      </ProveedorSesion>
    </BrowserRouter>
  </StrictMode>,
);
