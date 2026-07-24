import { useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { useToast, Spinner } from "../ui";

type Mode = "login" | "register";

export function Login() {
  const { login } = useAuth();
  const toast = useToast();
  const [mode, setMode] = useState<Mode>("login");
  const [busy, setBusy] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [slug, setSlug] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "register") {
        await api.register({
          tenant_name: tenantName,
          tenant_slug: slug,
          admin_email: email,
          admin_password: password,
        });
        toast.push("success", "Conta criada! Faça login.");
        setMode("login");
      } else {
        await login(email, password);
        toast.push("success", "Bem-vindo de volta 👋");
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Falha inesperada";
      toast.push("error", msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-aside">
        <div className="brand">
          <span className="brand-mark">🛰️</span>
          <h1>NexusData</h1>
        </div>
        <p className="tagline">
          Processamento assíncrono e inteligente de documentos, em escala.
        </p>
        <ul className="feature-list">
          <li>⚡ Ingestão em milissegundos (202 Accepted)</li>
          <li>🔒 Multi-tenant com isolamento por design</li>
          <li>🔁 Workers resilientes (retry + circuit breaker)</li>
          <li>📡 Status em tempo real via WebSocket</li>
        </ul>
      </div>

      <div className="auth-panel">
        <form className="auth-card" onSubmit={submit}>
          <h2>{mode === "login" ? "Entrar" : "Criar conta"}</h2>
          <p className="muted">
            {mode === "login"
              ? "Acesse o painel do seu tenant."
              : "Registre um novo tenant e seu administrador."}
          </p>

          {mode === "register" && (
            <>
              <label>
                Nome do tenant
                <input
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                  placeholder="Acme Corp"
                  required
                  minLength={2}
                />
              </label>
              <label>
                Slug
                <input
                  value={slug}
                  onChange={(e) => setSlug(e.target.value.toLowerCase())}
                  placeholder="acme"
                  pattern="[a-z0-9-]+"
                  required
                  minLength={2}
                />
              </label>
            </>
          )}

          <label>
            E-mail
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@acme.com"
              required
              autoComplete="username"
            />
          </label>
          <label>
            Senha
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              required
              minLength={mode === "register" ? 12 : 1}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {mode === "register" && (
            <small className="hint">Mínimo 12 caracteres, com letras e números.</small>
          )}

          <button className="btn btn-primary" disabled={busy} type="submit">
            {busy ? <Spinner /> : mode === "login" ? "Entrar" : "Criar conta"}
          </button>

          <button
            type="button"
            className="link-btn"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login"
              ? "Não tem conta? Criar tenant"
              : "Já tem conta? Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
