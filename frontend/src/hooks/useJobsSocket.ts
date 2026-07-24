import { useEffect, useRef, useState } from "react";
import { jobsSocketUrl, tokenStore } from "../api";

export interface JobUpdate {
  type: string;
  job_id: string;
  document_id: string;
  status: string;
  attempts: number;
  error: string | null;
  has_result: boolean;
}

export type SocketState = "connecting" | "open" | "closed";

/** Assina o canal de status em tempo real; reconecta com backoff. */
export function useJobsSocket(onUpdate: (u: JobUpdate) => void): SocketState {
  const [state, setState] = useState<SocketState>("connecting");
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout>;

    const connect = () => {
      const tokens = tokenStore.get();
      if (!tokens) return;
      setState("connecting");
      ws = new WebSocket(jobsSocketUrl(tokens.access_token));

      ws.onopen = () => {
        attempt = 0;
        setState("open");
      };
      ws.onmessage = (ev) => {
        try {
          onUpdateRef.current(JSON.parse(ev.data as string) as JobUpdate);
        } catch {
          /* ignora frames malformados */
        }
      };
      ws.onclose = () => {
        setState("closed");
        if (closed) return;
        attempt += 1;
        const delay = Math.min(1000 * 2 ** attempt, 15000);
        timer = setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return state;
}
