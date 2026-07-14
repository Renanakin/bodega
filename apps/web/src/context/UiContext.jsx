import { createContext, useContext, useMemo, useState } from "react";

const UiContext = createContext(null);
const PRESENTATION_MODE_KEY = "bodegaje_presentation_mode";
const PRESENTATION_TOUR_KEY = "bodegaje_presentation_tour";

export const presentationSteps = [
  {
    path: "/dashboard",
    title: "Inicio comercial",
    description: "Explica el problema: quiebres, pendientes y control general.",
    pitch: "Abre mostrando riesgo y backlog antes de entrar al detalle operativo.",
  },
  {
    path: "/inventory",
    title: "Visibilidad de stock",
    description: "Demuestra control por bodega, SKU y estado de disponibilidad.",
    pitch: "Aqui el cliente ve que el stock no esta disperso ni oculto.",
  },
  {
    path: "/transfers",
    title: "Movimiento controlado",
    description: "Muestra solicitud, aprobacion, despacho, recepcion parcial y cierre.",
    pitch: "Esta es la escena principal para vender trazabilidad y excepciones reales.",
  },
  {
    path: "/reports",
    title: "Salida util",
    description: "Exporta inventario, backlog o historial filtrado.",
    pitch: "Termina con un entregable concreto que el cliente se puede llevar.",
  },
  {
    path: "/settings",
    title: "Confianza final",
    description: "Cierra enseñando auditoria y control por perfil.",
    pitch: "Remata con gobernanza: quien hizo que y cuando.",
  },
];

let nextToastId = 1;

export function UiProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [pendingLabel, setPendingLabel] = useState("");
  const [presentationMode, setPresentationMode] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(PRESENTATION_MODE_KEY) === "true";
  });
  const [presentationStepIndex, setPresentationStepIndex] = useState(() => {
    if (typeof window === "undefined") return 0;
    const raw = window.localStorage.getItem(PRESENTATION_TOUR_KEY);
    return raw ? Number(raw) : 0;
  });

  const pushToast = (toast) => {
    const id = nextToastId++;
    setToasts((current) => [...current, { id, tone: "neutral", ...toast }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== id));
    }, 3200);
  };

  const togglePresentationMode = () => {
    setPresentationMode((current) => {
      const nextValue = !current;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(PRESENTATION_MODE_KEY, String(nextValue));
      }
      return nextValue;
    });
  };

  const setPresentationStep = (index) => {
    const safeIndex = Math.max(0, Math.min(index, presentationSteps.length - 1));
    setPresentationStepIndex(safeIndex);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PRESENTATION_TOUR_KEY, String(safeIndex));
    }
  };

  const nextPresentationStep = () => setPresentationStep(presentationStepIndex + 1);
  const previousPresentationStep = () => setPresentationStep(presentationStepIndex - 1);

  const value = useMemo(
    () => ({
      toasts,
      pendingLabel,
      presentationMode,
      presentationStepIndex,
      presentationSteps,
      setPendingLabel,
      clearPending: () => setPendingLabel(""),
      pushToast,
      togglePresentationMode,
      setPresentationStep,
      nextPresentationStep,
      previousPresentationStep,
    }),
    [pendingLabel, presentationMode, presentationStepIndex, toasts],
  );

  return <UiContext.Provider value={value}>{children}</UiContext.Provider>;
}

export function useUi() {
  const context = useContext(UiContext);
  if (!context) {
    throw new Error("useUi must be used inside UiProvider");
  }
  return context;
}
