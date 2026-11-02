import { useCallback, useEffect, useState } from "react";
import { MLFLOW_URL, fecha, llamar } from "../api.js";
import { Aviso, Cargando, mensajeError } from "../componentes.jsx";

/** Modelo (§10, solo administrador): versión activa, run ID, umbral y monitoreo. */
export default function Modelo() {
  const [info, setInfo] = useState(null);
  const [monitoreo, setMonitoreo] = useState(null);
  const [error, setError] = useState(null);

  const cargar = useCallback(async () => {
    try {
      const [i, m] = await Promise.all([
        llamar("prestamos", "/modelo/info"),
        llamar("prestamos", "/monitoreo/estado"),
      ]);
      setInfo(i);
      setMonitoreo(m);
      setError(null);
    } catch (exc) {
      setError(mensajeError(exc));
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  if (!info && !error) return <Cargando texto="Cargando información del modelo…" />;

  return (
    <>
      <h1>Modelo de riesgo</h1>
      <p className="subtitulo">
        El modelo vive dentro del servicio Préstamos (§8): el entrenamiento es un proceso fuera de
        línea; la promoción es explícita y reversible.
      </p>
      <Aviso tipo="error" texto={error} />

      {info && (
        <div className="panel">
          <div className="fila">
            <Dato etiqueta="Versión activa" valor={info.modelo_version} />
            <Dato etiqueta="Umbral" valor={`${(info.umbral * 100).toFixed(0)} %`} />
            <Dato etiqueta="Run ID" valor={info.run_id || "—"} />
            <Dato etiqueta="Promovido" valor={fecha(info.fecha_promocion)} />
          </div>
          <div className="fila">
            <Dato etiqueta="Algoritmo" valor={info.candidato || "—"} />
            <Dato etiqueta="ROC AUC (validación)" valor={info.roc_auc_validacion?.toFixed(4) || "—"} />
            <Dato etiqueta="Prueba (AUC / F1)" valor={
              info.metricas_prueba
                ? `${info.metricas_prueba.roc_auc?.toFixed(4) ?? "—"} / ${info.metricas_prueba.f1?.toFixed(4) ?? "—"}`
                : "—"} />
          </div>
          <p className="meta">
            <strong>Variables del modelo:</strong> {info.variables.join(", ")}
          </p>
          <p className="meta">
            Interfaz de MLflow:{" "}
            <a href={MLFLOW_URL} target="_blank" rel="noreferrer">{MLFLOW_URL}</a>{" "}
            (el servicio reporta <code>{info.mlflow_url}</code>; historial de entrenamientos y
            comparación, no se reconstruye aquí, §10).
          </p>
        </div>
      )}

      <h2>Monitoreo en producción (§15.2)</h2>
      {monitoreo && (
        <div className="panel">
          {monitoreo.total_inferencias === 0 ? (
            <p className="vacio">Aún no hay decisiones registradas en este despliegue.</p>
          ) : (
            <>
              <div className="fila">
                <Dato etiqueta="Inferencias" valor={monitoreo.total_inferencias} />
                <Dato etiqueta="Latencia p50" valor={`${monitoreo.latencia_ms.p50} ms`} />
                <Dato etiqueta="Latencia p95" valor={`${monitoreo.latencia_ms.p95} ms`} />
                <Dato etiqueta="Sobre umbral" valor={`${(monitoreo.tasa_sobre_umbral * 100).toFixed(1)} %`} />
              </div>
              <p>
                Deriva del lote reciente contra la línea base del histórico:{" "}
                <span className={`insignia ${
                  monitoreo.deriva.estado === "alerta" ? "error"
                  : monitoreo.deriva.estado === "revisar" ? "aviso" : "ok"}`}>
                  {monitoreo.deriva.estado}
                </span>
                {monitoreo.deriva.psi_maximo !== null && <> · PSI máximo {monitoreo.deriva.psi_maximo}</>}
              </p>
              <p className="meta">
                Línea base: {monitoreo.linea_base?.fuente} ({monitoreo.linea_base?.filas} filas, sha256{" "}
                {(monitoreo.linea_base?.sha256_fuente || "").slice(0, 12)}…).
              </p>
            </>
          )}
        </div>
      )}
    </>
  );
}

function Dato({ etiqueta, valor }) {
  return (
    <div className="campo" style={{ flex: 1, minWidth: 170 }}>
      <span className="meta">{etiqueta}</span>
      <strong>{valor}</strong>
    </div>
  );
}
