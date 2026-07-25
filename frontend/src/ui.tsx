import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import type { JobStatus } from "./api";

// ---------------- Toasts ----------------
type ToastKind = "success" | "error" | "info";
interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}
interface ToastApi {
  push: (kind: ToastKind, message: string) => void;
}
const ToastCtx = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  let seq = 0;
  const push = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + seq++;
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast fora do ToastProvider");
  return ctx;
}

// ---------------- Status badge ----------------
export function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

// ---------------- Spinner ----------------
export function Spinner() {
  return <span className="spinner" aria-label="carregando" />;
}

// ---------------- Modal ----------------
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="fechar">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
