/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Tokens del proyecto, prefijo `bodega-` (ADR-0006 IMP-006).
        // Las vistas nuevas los consumen como `bg-bodega-bg`, `text-bodega-ink`, etc.
        'bodega-bg': 'var(--bg)',
        'bodega-surface': 'var(--surface)',
        'bodega-line': 'var(--line)',
        'bodega-ink': 'var(--ink)',
        'bodega-muted': 'var(--muted)',
        'bodega-accent': 'var(--accent)',
        'bodega-accent-strong': 'var(--accent-strong)',
        'bodega-danger': 'var(--danger)',
        'bodega-danger-soft': 'var(--danger-soft)',
        'bodega-warning': 'var(--warning)',
        'bodega-warning-soft': 'var(--warning-soft)',
        'bodega-success': 'var(--success)',
        'bodega-success-soft': 'var(--success-soft)',
        // Alias histórico (legacy) que algunas vistas usan en hex.
        'bodega-primary': 'var(--accent)',
        'bodega-primary-dark': 'var(--accent-strong)',
      },
      fontFamily: {
        sans: ['"Segoe UI"', 'Tahoma', 'Geneva', 'Verdana', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
