import { useState } from "react";
import { api, ApiError, type DocType, type JobView } from "../api";
import { useToast, Spinner } from "../ui";

const DOC_TYPES: DocType[] = ["generic", "invoice", "contract", "support_ticket"];

const SAMPLES: Record<DocType, string> = {
  generic: '{\n  "text": "conteúdo livre"\n}',
  invoice: '{\n  "invoice_number": "NF-123",\n  "total_amount": 1990,\n  "currency": "BRL"\n}',
  contract: '{\n  "parties": ["Acme", "Globex"],\n  "effective_date": "2026-01-01"\n}',
  support_ticket: '{\n  "message": "estou com um problema no login",\n  "priority": "high"\n}',
};

export function UploadPanel({
  onIngested,
  onRefresh,
}: {
  onIngested: (job: JobView) => void;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const [docType, setDocType] = useState<DocType>("invoice");
  const [payload, setPayload] = useState(SAMPLES.invoice);
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [busy, setBusy] = useState(false);

  const pickType = (t: DocType) => {
    setDocType(t);
    setPayload(SAMPLES[t]);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    let parsed: unknown;
    try {
      parsed = payload.trim() ? JSON.parse(payload) : {};
    } catch {
      toast.push("error", "JSON inválido no payload.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.ingest(
        { doc_type: docType, raw_payload: parsed },
        idempotencyKey.trim() || undefined,
      );
      toast.push(
        result.idempotent_replay ? "info" : "success",
        result.idempotent_replay
          ? "Requisição idempotente: job já existente."
          : `Job aceito (202): ${result.job_id.slice(0, 8)}…`,
      );
      onIngested({
        id: result.job_id,
        document_id: result.document_id,
        status: result.status,
        attempts: 0,
        max_attempts: 3,
        result: null,
        error: null,
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: null,
      });
      onRefresh();
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Falha na ingestão.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={submit}>
      <h3>Ingerir documento</h3>
      <p className="muted small">
        Envie um payload estruturado. A API responde <b>202</b> e o worker processa em background.
      </p>

      <label>
        Tipo de documento
        <div className="chip-row">
          {DOC_TYPES.map((t) => (
            <button
              type="button"
              key={t}
              className={t === docType ? "chip selectable active" : "chip selectable"}
              onClick={() => pickType(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </label>

      <label>
        Payload (JSON)
        <textarea
          className="code"
          rows={8}
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          spellCheck={false}
        />
      </label>

      <label>
        Idempotency-Key <span className="muted small">(opcional)</span>
        <input
          value={idempotencyKey}
          onChange={(e) => setIdempotencyKey(e.target.value)}
          placeholder="ex.: pedido-42 (evita processamento duplicado)"
        />
      </label>

      <button className="btn btn-primary" disabled={busy} type="submit">
        {busy ? <Spinner /> : "Enviar para processamento"}
      </button>
    </form>
  );
}
