// CategoriasPage: gestion del catalogo de categorias con vista en arbol (Fase 8).
//
// Ruta: /categorias
//
// Caracteristicas:
// - Carga la jerarquia completa en una sola llamada (GET /categories/arbol).
// - Renderiza un arbol colapsable (no flat): cada nodo muestra nombre,
//   descripcion, # subcategorias, # productos.
// - Acciones por nodo: Editar, Eliminar (soft), Nueva subcategoria.
// - Drawer lateral con form de crear/editar.
// - Busqueda por nombre (filtra en cliente, destaca coincidencias).
// - Disenada 100% con Tailwind v3 (sin CSS plano legacy, ADR-0006).
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  deleteJson,
  getErrorMessage,
  getJson,
  patchJson,
  postJson,
} from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

function Drawer({ open, onClose, children, title }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <button
        type="button"
        onClick={onClose}
        className="flex-1 bg-slate-900/50 backdrop-blur-sm"
        aria-label="Cerrar"
      />
      <div className="flex w-full max-w-md flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:bg-slate-100"
            aria-label="Cerrar"
          >
            <span aria-hidden="true">x</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  );
}

function CategoriaForm({ initial, parentId, onSubmit, onCancel, submitting, error }) {
  const [nombre, setNombre] = useState(initial?.nombre || "");
  const [descripcion, setDescripcion] = useState(initial?.descripcion || "");
  const esEdicion = Boolean(initial?.id);
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({
      nombre: nombre.trim(),
      descripcion: descripcion.trim() || null,
      parent_id: initial?.parent_id ?? parentId ?? null,
    });
  };
  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label htmlFor="cat-nombre" className="block text-sm font-medium text-slate-700">
          Nombre
        </label>
        <input
          id="cat-nombre"
          type="text"
          required
          minLength={1}
          maxLength={100}
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label htmlFor="cat-desc" className="block text-sm font-medium text-slate-700">
          Descripcion
        </label>
        <textarea
          id="cat-desc"
          maxLength={500}
          rows={3}
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      {parentId && !esEdicion ? (
        <p className="text-xs text-slate-500">
          Se creara como subcategoria del nodo seleccionado.
        </p>
      ) : null}
      {error ? (
        <p className="rounded-md border border-rose-200 bg-rose-50 p-2 text-sm text-rose-700">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Guardando..." : esEdicion ? "Guardar cambios" : "Crear categoria"}
        </button>
      </div>
    </form>
  );
}

/**
 * Nodo recursivo del arbol. Maneja su propio estado de colapso.
 */
function TreeNode({ node, depth, onEdit, onDelete, onAddChild, expanded, onToggle }) {
  const hasChildren = node.children && node.children.length > 0;
  const isOpen = expanded.has(node.id);
  return (
    <li role="treeitem" aria-expanded={hasChildren ? isOpen : undefined}>
      <div
        className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-slate-50"
        style={{ paddingLeft: `${depth * 1.25 + 0.5}rem` }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => onToggle(node.id)}
            className="flex h-5 w-5 items-center justify-center rounded text-slate-500 hover:bg-slate-200"
            aria-label={isOpen ? "Colapsar" : "Expandir"}
          >
            <span aria-hidden="true" className="text-xs">
              {isOpen ? "▾" : "▸"}
            </span>
          </button>
        ) : (
          <span className="flex h-5 w-5 items-center justify-center text-slate-300" aria-hidden="true">
            ·
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className={`truncate text-sm ${node.is_active ? "text-slate-800" : "text-slate-400 line-through"}`}>
            <span className="font-medium">{node.nombre}</span>
            {node.descripcion ? (
              <span className="ml-2 text-xs text-slate-500">— {node.descripcion}</span>
            ) : null}
          </p>
          <p className="text-xs text-slate-500">
            {node.subcategorias_count} subcat. · {node.productos_count} producto(s)
          </p>
        </div>
        <div className="flex shrink-0 gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
          <button
            type="button"
            onClick={() => onAddChild(node)}
            className="rounded border border-slate-300 px-2 py-0.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
            title="Nueva subcategoria"
          >
            + Sub
          </button>
          <button
            type="button"
            onClick={() => onEdit(node)}
            className="rounded border border-indigo-300 px-2 py-0.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
            title="Editar"
          >
            Editar
          </button>
          <button
            type="button"
            onClick={() => onDelete(node)}
            className="rounded border border-rose-300 px-2 py-0.5 text-xs font-medium text-rose-700 hover:bg-rose-50"
            title="Eliminar (soft)"
          >
            Eliminar
          </button>
        </div>
      </div>
      {hasChildren && isOpen ? (
        <ul role="group" className="list-none">
          {node.children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              onEdit={onEdit}
              onDelete={onDelete}
              onAddChild={onAddChild}
              expanded={expanded}
              onToggle={onToggle}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function CategoriasPage() {
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();

  const [tree, setTree] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busqueda, setBusqueda] = useState("");
  const [expanded, setExpanded] = useState(new Set());
  const [drawerMode, setDrawerMode] = useState(null);
  const [editingCategoria, setEditingCategoria] = useState(null);
  const [parentForNew, setParentForNew] = useState(null);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const esAdmin = user?.role === "admin" || user?.role === "supervisor";

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJson("/categories/arbol");
      setTree(Array.isArray(data) ? data : []);
      // Auto-expandir el primer nivel para que el usuario vea la jerarquia.
      if (Array.isArray(data) && data.length > 0) {
        setExpanded((prev) => {
          const next = new Set(prev);
          data.forEach((n) => next.add(n.id));
          return next;
        });
      }
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar el catalogo de categorias."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Filtrado recursivo: si un nodo matchea, se muestra + sus descendientes.
  // Si no, pero un descendiente matchea, se muestra el nodo contenedor.
  const treeFiltrado = useMemo(() => {
    if (!busqueda.trim()) return tree;
    const q = busqueda.toLowerCase();
    const filtraNodo = (n) => {
      const matchSelf = n.nombre.toLowerCase().includes(q) ||
        (n.descripcion || "").toLowerCase().includes(q);
      const childrenMatch = (n.children || []).map(filtraNodo).filter(Boolean);
      if (matchSelf || childrenMatch.length > 0) {
        return { ...n, children: childrenMatch.length > 0 ? childrenMatch : (n.children || []) };
      }
      return null;
    };
    return tree.map(filtraNodo).filter(Boolean);
  }, [tree, busqueda]);

  const toggle = useCallback((id) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const abrirCrearRaiz = () => {
    setEditingCategoria(null);
    setParentForNew(null);
    setFormError(null);
    setDrawerMode("create");
  };
  const abrirCrearHijo = (parent) => {
    setEditingCategoria(null);
    setParentForNew(parent);
    setFormError(null);
    setDrawerMode("create");
  };
  const abrirEditar = (cat) => {
    setEditingCategoria(cat);
    setParentForNew(null);
    setFormError(null);
    setDrawerMode("edit");
  };
  const cerrarDrawer = () => {
    setDrawerMode(null);
    setEditingCategoria(null);
    setParentForNew(null);
    setFormError(null);
  };

  const onSubmit = async (payload) => {
    setSubmitting(true);
    setFormError(null);
    setPendingLabel(drawerMode === "create" ? "Creando..." : "Guardando...");
    try {
      if (drawerMode === "create") {
        await postJson("/categories", payload);
        pushToast({
          tone: "success",
          title: "Categoria creada",
          description: payload.nombre,
        });
      } else if (drawerMode === "edit" && editingCategoria) {
        await patchJson(`/categories/${editingCategoria.id}`, payload);
        pushToast({
          tone: "success",
          title: "Categoria actualizada",
          description: payload.nombre,
        });
      }
      cerrarDrawer();
      await cargar();
    } catch (err) {
      const code = err instanceof ApiError ? err.detail?.detail?.code : null;
      if (code === "duplicate_category_name") {
        setFormError("Ya existe una categoria con ese nombre.");
      } else if (code === "category_not_found") {
        setFormError("La categoria padre seleccionada ya no existe.");
      } else if (code === "category_circular_reference") {
        setFormError("Esta operacion crearia una referencia circular.");
      } else {
        setFormError(getErrorMessage(err, "No se pudo guardar la categoria."));
      }
    } finally {
      clearPending();
      setSubmitting(false);
    }
  };

  const eliminar = async (cat) => {
    setConfirmDelete(null);
    setPendingLabel("Desactivando categoria...");
    try {
      await deleteJson(`/categories/${cat.id}`);
      pushToast({
        tone: "info",
        title: "Categoria desactivada",
        description: cat.nombre,
      });
      await cargar();
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al desactivar",
        description: getErrorMessage(err),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Catalogo
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Categorias de Productos
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Jerarquia de categorias para agrupar productos. Soporta hasta N
            niveles de subcategorias; el arbol se carga en una sola llamada.
          </p>
        </div>
        {esAdmin ? (
          <button
            type="button"
            onClick={abrirCrearRaiz}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
          >
            Nueva categoria raiz
          </button>
        ) : null}
      </header>

      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <input
          type="search"
          placeholder="Buscar por nombre o descripcion..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 sm:max-w-xs"
          aria-label="Buscar categoria"
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setExpanded(new Set())}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Colapsar todo
          </button>
          <button
            type="button"
            onClick={() => {
              const all = new Set();
              const walk = (nodes) => {
                for (const n of nodes) {
                  all.add(n.id);
                  if (n.children) walk(n.children);
                }
              };
              walk(tree);
              setExpanded(all);
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Expandir todo
          </button>
          <button
            type="button"
            onClick={cargar}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Refrescar
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">Cargando categorias...</p>
        ) : error ? (
          <p className="p-6 text-sm text-rose-600">Error: {error}</p>
        ) : treeFiltrado.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-base font-semibold text-slate-700">
              {busqueda.trim()
                ? "Sin resultados para la busqueda"
                : "Sin categorias para mostrar"}
            </p>
            <p className="mt-1 text-sm text-slate-500">
              {busqueda.trim()
                ? "Pruebe con otro termino."
                : "Cree la primera categoria raiz para empezar."}
            </p>
          </div>
        ) : (
          <ul role="tree" className="list-none p-2">
            {treeFiltrado.map((node) => (
              <TreeNode
                key={node.id}
                node={node}
                depth={0}
                onEdit={abrirEditar}
                onDelete={setConfirmDelete}
                onAddChild={abrirCrearHijo}
                expanded={expanded}
                onToggle={toggle}
              />
            ))}
          </ul>
        )}
      </div>

      <p className="text-xs text-slate-500">
        Soft delete: las categorias desactivadas se conservan para no romper
        referencias en productos historicos. La UI las muestra tachadas para
        que se distingan claramente.
      </p>

      <Drawer
        open={drawerMode !== null}
        onClose={cerrarDrawer}
        title={
          drawerMode === "create"
            ? parentForNew
              ? `Nueva subcategoria de "${parentForNew.nombre}"`
              : "Nueva categoria raiz"
            : "Editar categoria"
        }
      >
        <CategoriaForm
          initial={editingCategoria}
          parentId={parentForNew?.id}
          onSubmit={onSubmit}
          onCancel={cerrarDrawer}
          submitting={submitting}
          error={formError}
        />
      </Drawer>

      {confirmDelete ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
            <h2 className="text-base font-semibold text-slate-900">
              Confirmar desactivacion
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              La categoria{" "}
              <span className="font-semibold">{confirmDelete.nombre}</span>{" "}
              quedara inactiva. Las subcategorias existentes (si las hay)
              se mantienen pero apareceran como raiz hasta que se les asigne
              un nuevo padre.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDelete(null)}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => eliminar(confirmDelete)}
                className="rounded-md bg-rose-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-rose-500"
              >
                Desactivar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
