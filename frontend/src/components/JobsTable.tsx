import { useState } from "react";
import { api, ApiError, type JobView } from "../api";
import { Modal, StatusBadge, useToast } from "../ui";

export function JobsTable({ jobs, onRefresh }: { jobs: JobView[]; onRefresh: () => void }) {
  const toast = useToast();
  const [selected, setSelected] = useState<JobView | null>(null);

  const open = async (job: JobView) => {
    try {
      setSelected(await api.job(job.id)); // busca a versão completa (com result)
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Falha ao abrir job.");
    }
  };

  return (
    <div className="card">
      <div className="card-head">
        <h3>Jobs</h3>
        <button className="btn btn-ghost small" onClick={onRefresh}>
          Atualizar
        </button>
      </div>

      {jobs.length === 0 ? (
        <div className="empty">Nenhum job ainda. Envie um documento ao lado 👈</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th>Status</th>
                <th>Tent.</th>
                <th>Criado</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} onClick={() => void open(j)} className="clickable">
                  <td className="mono">{j.id.slice(0, 8)}…</td>
                  <td>
                    <StatusBadge status={j.status} />
                  </td>
                  <td>
                    {j.attempts}/{j.max_attempts}
                  </td>
                  <td className="muted small">{fmt(j.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <Modal title={`Job ${selected.id.slice(0, 8)}…`} onClose={() => setSelected(null)}>
          <div className="detail-row">
            <span>Status</span>
            <StatusBadge status={selected.status} />
          </div>
          <div className="detail-row">
            <span>Tentativas</span>
            <b>
              {selected.attempts}/{selected.max_attempts}
            </b>
          </div>
          {selected.error && (
            <div className="detail-row">
              <span>Erro</span>
              <code className="err">{selected.error}</code>
            </div>
          )}
          <span className="muted small">Resultado</span>
          <pre className="code block">
            {selected.result ? JSON.stringify(selected.result, null, 2) : "— ainda sem resultado —"}
          </pre>
        </Modal>
      )}
    </div>
  );
}

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}
