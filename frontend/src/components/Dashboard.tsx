import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type JobStatus, type JobView } from "../api";
import { useAuth } from "../auth";
import { useJobsSocket } from "../hooks/useJobsSocket";
import { useToast } from "../ui";
import { UploadPanel } from "./UploadPanel";
import { JobsTable } from "./JobsTable";
import { ApiKeysPanel } from "./ApiKeysPanel";
import { WebhooksPanel } from "./WebhooksPanel";

type Tab = "jobs" | "keys" | "webhooks";

export function Dashboard() {
  const { identity, logout } = useAuth();
  const toast = useToast();
  const [jobs, setJobs] = useState<JobView[]>([]);
  const [tab, setTab] = useState<Tab>("jobs");
  const isAdmin = identity?.role === "admin";

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await api.jobs());
    } catch {
      toast.push("error", "Não foi possível carregar os jobs.");
    }
  }, [toast]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const socketState = useJobsSocket(
    useCallback((update) => {
      setJobs((prev) => {
        const idx = prev.findIndex((j) => j.id === update.job_id);
        if (idx === -1) {
          void loadJobs();
          return prev;
        }
        const next = [...prev];
        next[idx] = {
          ...next[idx],
          status: update.status as JobStatus,
          attempts: update.attempts,
          error: update.error,
        };
        return next;
      });
    }, [loadJobs]),
  );

  const stats = useMemo(() => {
    const by = (s: JobStatus) => jobs.filter((j) => j.status === s).length;
    return {
      total: jobs.length,
      pending: by("pending") + by("processing") + by("retrying"),
      completed: by("completed"),
      failed: by("failed"),
    };
  }, [jobs]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand small">
          <span className="brand-mark">🛰️</span>
          <strong>NexusData</strong>
        </div>
        <div className="topbar-right">
          <span className={`ws-dot ws-${socketState}`} title={`WebSocket: ${socketState}`} />
          <span className="muted small">tempo real</span>
          <span className="chip">{identity?.role}</span>
          <span className="chip mono">tenant {identity?.tenant_id.slice(0, 8)}…</span>
          <button className="btn btn-ghost" onClick={logout}>
            Sair
          </button>
        </div>
      </header>

      <main className="content">
        <section className="stats">
          <StatCard label="Total de jobs" value={stats.total} tone="neutral" />
          <StatCard label="Em andamento" value={stats.pending} tone="pending" />
          <StatCard label="Concluídos" value={stats.completed} tone="completed" />
          <StatCard label="Falhados" value={stats.failed} tone="failed" />
        </section>

        <nav className="tabs">
          <button className={tab === "jobs" ? "tab active" : "tab"} onClick={() => setTab("jobs")}>
            Ingestão & Jobs
          </button>
          {isAdmin && (
            <>
              <button className={tab === "keys" ? "tab active" : "tab"} onClick={() => setTab("keys")}>
                API Keys
              </button>
              <button
                className={tab === "webhooks" ? "tab active" : "tab"}
                onClick={() => setTab("webhooks")}
              >
                Webhooks
              </button>
            </>
          )}
        </nav>

        {tab === "jobs" && (
          <div className="grid-2">
            <UploadPanel onIngested={(job) => setJobs((p) => [job, ...p])} onRefresh={loadJobs} />
            <JobsTable jobs={jobs} onRefresh={loadJobs} />
          </div>
        )}
        {tab === "keys" && isAdmin && <ApiKeysPanel />}
        {tab === "webhooks" && isAdmin && <WebhooksPanel />}
      </main>
    </div>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "neutral" | "pending" | "completed" | "failed";
}) {
  return (
    <div className={`stat-card tone-${tone}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
