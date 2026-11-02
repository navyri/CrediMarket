# CrediMarket · frontend (§10, §13.2)
# Build de producción con Vite + servicio estático con nginx (SPA de React
# Router). Las URLs de las APIs se inyectan en el BUILD y las consume el
# navegador del usuario (por eso apuntan a localhost:800X); el contenedor
# solo sirve archivos estáticos.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

ARG VITE_API_PRODUCTOS=http://localhost:8001
ARG VITE_API_CLIENTES=http://localhost:8002
ARG VITE_API_PRESTAMOS=http://localhost:8003
ARG VITE_API_INVENTARIO=http://localhost:8004
ARG VITE_MLFLOW_URL=http://localhost:5000
ENV VITE_API_PRODUCTOS=${VITE_API_PRODUCTOS} \
    VITE_API_CLIENTES=${VITE_API_CLIENTES} \
    VITE_API_PRESTAMOS=${VITE_API_PRESTAMOS} \
    VITE_API_INVENTARIO=${VITE_API_INVENTARIO} \
    VITE_MLFLOW_URL=${VITE_MLFLOW_URL}

RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
