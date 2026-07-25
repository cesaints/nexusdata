import { useEffect, useState } from "react";
import { api, ApiError, type WebhookEvent, type WebhookView } from "../api";
import { Modal, useToast, Spinner } from "../ui";

const EVENTS: WebhookEvent[] = ["job.completed", "job.failed"];

export function WebhooksPanel() {
  const toast = useToast();
  const [hooks, setHooks] = useState<WebhookView[]>([]);
  const [url, setUrl] = useState("https://");
  const [events, setEvents] = useState<WebhookEvent[]>(["job.completed"]);
  const [busy, setBusy] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);

  const load = async () => {
    try {
      setHooks(await api.webhooks());
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Falha ao listar.");
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const toggle = (e: WebhookEvent) =>
    setEvents((cur) => (cur.includes(e) ? cur.filter((x) => x !== e) : [...cur, e]));

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (events.length === 0) {
      toast.push("error", "Selecione ao menos um evento.");
      return;
    }
    setBusy(true);
    try {
      const hook = await api.createWebhook(url, events);
      setSecret(hook.secret);
      setUrl("https://");
      await load();
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Falha ao criar webhook.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteWebhook(id);
      toast.push("success", "Webhook removido.");
      await load();
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Falha ao remover.");
    }
  };

  return (
    <div className="grid-2">
      <form className="card" onSubmit={create}>
        <h3>Novo Webhook</h3>
        <p className="muted small">
          Notificações push assinadas com <b>HMAC-SHA256</b>. Apenas <b>HTTPS</b>.
        </p>
        <label>
          URL de callback
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder="https://seu-sistema.com/webhooks/nexus"
          />
        </label>
        <label>Eventos</label>
        <div className="chip-row">
          {EVENTS.map((e) => (
            <button
              type="button"
              key={e}
              className={events.includes(e) ? "chip selectable active" : "chip selectable"}
              onClick={() => toggle(e)}
            >
              {e}
            </button>
          ))}
        </div>
        <button className="btn btn-primary" disabled={busy} type="submit">
          {busy ? <Spinner /> : "Registrar webhook"}
        </button>
      </form>

      <div className="card">
        <div className="card-head">
          <h3>Webhooks registrados</h3>
          <button className="btn btn-ghost small" onClick={load}>
            Atualizar
          </button>
        </div>
        {hooks.length === 0 ? (
          <div className="empty">Nenhum webhook registrado.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Eventos</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {hooks.map((h) => (
                  <tr key={h.id}>
                    <td className="mono small">{h.url}</td>
                    <td className="small">{h.events.join(", ")}</td>
                    <td>
                      <button className="link-btn danger" onClick={() => void remove(h.id)}>
                        remover
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {secret && (
        <Modal title="Secret do webhook (exibido uma vez)" onClose={() => setSecret(null)}>
          <p className="muted small">
            Use este segredo para verificar a assinatura <code>X-Nexus-Signature</code> das entregas.
          </p>
          <pre className="code block secret">{secret}</pre>
          <button
            className="btn btn-primary"
            onClick={() => {
              void navigator.clipboard?.writeText(secret);
              toast.push("success", "Copiado!");
            }}
          >
            Copiar
          </button>
        </Modal>
      )}
    </div>
  );
}
