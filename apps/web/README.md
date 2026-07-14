# Web

Frontend del sistema multi-bodega construido con React + Vite.

## Alcance actual

- shell principal con navegacion lateral
- dashboard operativo con KPIs y actividad reciente
- pantallas de inventario, productos, transferencias, reposicion y slotting
- chat operacional base
- reportes comerciales y configuracion
- capa de datos mock con punto de integracion hacia la API

## Estructura

- `src/components/`: piezas reutilizables
- `src/views/`: pantallas del sistema
- `src/shell/`: layout general
- `src/data/`: datos mock para desarrollo rapido
- `src/lib/`: utilidades y cliente HTTP
- `src/hooks/`: hooks de estado y consumo

## Scripts

```bash
npm install
npm run dev
npm run build
npm run preview
npm run lint
npm run format
```

## Variable principal

- `VITE_API_URL`: base de la API, por defecto `/api/v1`

## Calidad

- `eslint.config.js`: reglas base de lint
- `.prettierrc.json`: formato consistente del proyecto
- `.dockerignore`: evita subir dependencias y cache al contexto de build
