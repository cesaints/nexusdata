import { useEffect, useState } from "react";
import { api, ApiError, type ApiKeyView, type Scope } from "../api";
import { Modal, useToast, Spinner } from "../ui";

const ALL_SCOPES: Scope[] = ["documents:write", "documents:read", "jobs:read", "webhooks:write"];

export function ApiKeysPanel() {
  const toast = useToast();
  const [keys, setKeys] = useState<ApiKeyView[]>([]);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<Scope[]>(["documents:write", "jobs:read"]);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<string | null>(null);

  const load = async () => {
    try {
      setKeys(await api.apiKeys());
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Falha ao listar.");
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const toggle = (s: Scope) =>
    setScopes((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (scopes.length === 0) {
      toast.push("error", "Selecione ao menos um escopo.");
      return;
    }
    setBusy(true);
    try {
      const key = await api.createApiKey(name, scopes);
      setCreated(key.full_key);
      setName("");
      await load();
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Falha ao criar.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    try {
      await api.revokeApiKey(id);
      toast.push("success", "API key revogada.");
      await load();
    } catch (err) {
      toast.push("error", err instanceof ApiError ? err.message : "Falha ao revogar.");
    }
  };

  return (
    <div className="grid-2">
      <form className="card" onSubmit={create}>
        <h3>Nova API Key</h3>
        <p className="muted small">
          Autenticação máquina-a-máquina por escopos. O segredo é exibido <b>uma única vez</b>.
        </p>
        <label>
          Nome
          <input value={name} onChange={(e) => setName(e.target.value)} required placeholder="pipeline-ci" />
        </label>
        <label>Escopos</label>
        <div className="chip-row">
          {ALL_SCOPES.map((s) => (
            <button
              type="button"
              key={s}
              className={scopes.includes(s) ? "chip selectable active" : "chip selectable"}
              onClick={() => toggle(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <button className="btn btn-primary" disabled={busy} type="submit">
          {busy ? <Spinner /> : "Gerar chave"}
        </button>
      </form>

      <div className="card">
        <div className="card-head">
          <h3>Chaves ativas</h3>
          <button className="btn btn-ghost small" onClick={load}>
            Atualizar
          </button>
        </div>
        {keys.length === 0 ? (
          <div className="empty">Nenhuma chave criada.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Prefixo</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id}>
                    <td>{k.name}</td>
                    <td className="mono">{k.prefix}</td>
                    <td>
                      <span className={k.is_active ? "badge badge-completed" : "badge badge-failed"}>
                        {k.is_active ? "ativa" : "revogada"}
                      </span>
                    </td>
                    <td>
                      {k.is_active && (
                        <button className="link-btn danger" onClick={() => void revoke(k.id)}>
                          revogar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {created && (
        <Modal title="Copie sua API Key agora" onClose={() => setCreated(null)}>
          <p className="muted small">
            Por segurança, este segredo <b>não será exibido novamente</b>. Guarde-o com cuidado.
          </p>
          <pre className="code block secret">{created}</pre>
          <button
            className="btn btn-primary"
            onClick={() => {
              void navigator.clipboard?.writeText(created);
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
