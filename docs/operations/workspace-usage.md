# Workspace Usage

## Como usar este workspace

1. Abrir [bodegaje.code-workspace](/C:/Users/HackBook/Documents/desarrollos/bodegaje/bodegaje.code-workspace) en VS Code.
2. Confiar en el workspace solo si reconoces el contenido.
3. Instalar las extensiones recomendadas por cada raiz.
4. Trabajar cada cambio en su carpeta natural:
   - `docs` para documentacion
   - `apps/api` para backend
   - `apps/web` para frontend
   - `db` para esquema y migraciones
   - `infra` para despliegue
5. Evitar editar `db` y `apps/api` si esos modulos estan asignados a otro agente.

## Criterio de trabajo por agentes

- un agente de documentacion trabaja en `docs`
- un agente backend trabaja en `apps/api`
- un agente frontend trabaja en `apps/web`
- un agente SQL trabaja en `db`
- un agente DevOps trabaja en `infra`

Esto reduce mezcla de contexto y mantiene el workspace ordenado.

## Notas operativas actuales

- `apps/web` ya tiene formularios, feedback global y build Docker validada
- `infra` ya tiene perfiles `local`, `staging` y `production`
- para desarrollo diario usar el perfil `local`
