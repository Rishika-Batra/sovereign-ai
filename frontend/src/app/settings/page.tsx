"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Tab = "models" | "knowledge" | "system";

interface ModelEntry {
  key: string;
  name: string;
  type: string;
  backend: string;
}

interface KBSummary {
  workspace_name: string;
  document_count: number;
  last_updated: string | null;
}

interface SystemStatus {
  ollama_status: string;
  database_status: string;
  server_time: string;
  uptime: string;
  architecture: string;
}

interface NetworkEndpoint {
  host: string;
  status: string;
}

interface NetworkStatus {
  isolation_verified: boolean;
  endpoints: Record<string, NetworkEndpoint>;
  note: string;
}

const MODEL_TYPE_COLOR: Record<string, string> = {
  general: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  coding: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  vision: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  embedding: "bg-amber-500/10 text-amber-400 border-amber-500/20",
};

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-block w-2 h-2 rounded-full mr-2 ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("models");
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [kb, setKb] = useState<KBSummary[]>([]);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [network, setNetwork] = useState<NetworkStatus | null>(null);
  const [networkLoading, setNetworkLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const router = useRouter();

  const load = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) { router.push("/"); return; }

    setLoading(true);
    setError(null);

    try {
      const headers = { Authorization: `Bearer ${token}` };

      const [modelsRes, kbRes, sysRes] = await Promise.all([
        fetch(`${API_BASE}/api/settings/models`, { headers }),
        fetch(`${API_BASE}/api/documents/knowledge-base`, { headers }),
        fetch(`${API_BASE}/api/settings/system`, { headers }),
      ]);

      if (modelsRes.status === 401 || kbRes.status === 401 || sysRes.status === 401) {
        localStorage.removeItem("access_token");
        router.push("/");
        return;
      }

      // Check admin gate via models endpoint (tightest)
      if (modelsRes.status === 403) {
        setForbidden(true);
        return;
      }

      if (!modelsRes.ok || !kbRes.ok || !sysRes.ok) {
        throw new Error(`Failed to load settings`);
      }

      setModels(await modelsRes.json());
      setKb(await kbRes.json());
      setSystem(await sysRes.json());

      // Fetch network status separately (heavier call, don't block main load)
      setNetworkLoading(true);
      try {
        const netRes = await fetch(`${API_BASE}/api/settings/network-status`, { headers });
        if (netRes.ok) setNetwork(await netRes.json());
      } catch { /* non-fatal */ } finally {
        setNetworkLoading(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => { load(); }, [load]);

  if (forbidden) {
    return (
      <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-white mb-2">Admin Only</h1>
        <p className="text-gray-400 max-w-md mb-6">The Settings page is restricted to administrators.</p>
        <Link href="/chat" className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition-colors">
          Return to Chat
        </Link>
      </div>
    );
  }

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: "models", label: "Models", icon: "M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" },
    { id: "knowledge", label: "Knowledge Bases", icon: "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" },
    { id: "system", label: "System", icon: "M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v10m0 0h10M9 13H5m4 0v6m0 0H5m4 0h4m4-13v19m0 0h-4m4 0h2" },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-gray-200">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center gap-4">
        <Link href="/chat" className="text-gray-400 hover:text-white transition-colors">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
        </Link>
        <div>
          <h1 className="text-xl font-bold text-white">Settings</h1>
          <p className="text-xs text-gray-400 mt-0.5">Admin configuration &amp; system status</p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6">
        {error && (
          <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-md text-red-200">{error}</div>
        )}

        {/* Tab bar */}
        <div className="flex gap-1 p-1 bg-gray-800 rounded-lg border border-gray-700 mb-8 w-fit">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                tab === t.id
                  ? "bg-indigo-600 text-white shadow"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-700"
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={t.icon} />
              </svg>
              {t.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex justify-center p-16">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500" />
          </div>
        ) : (
          <>
            {/* ── Models ── */}
            {tab === "models" && (
              <section>
                <h2 className="text-lg font-semibold text-white mb-1">Model Registry</h2>
                <p className="text-sm text-gray-400 mb-5">
                  All inference models are served locally via Ollama. No external AI API calls are made.
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  {models.map((m) => (
                    <div
                      key={m.key}
                      className="bg-gray-800 border border-gray-700 rounded-xl p-5 flex flex-col gap-3 hover:border-gray-600 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="text-xs text-gray-500 uppercase tracking-wider font-medium">{m.key}</p>
                          <p className="text-white font-semibold mt-0.5 font-mono text-sm">{m.name}</p>
                        </div>
                        <span
                          className={`px-2.5 py-1 rounded-full text-xs font-medium border ${
                            MODEL_TYPE_COLOR[m.type] ?? "bg-gray-700 text-gray-300 border-gray-600"
                          }`}
                        >
                          {m.type}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-gray-400">
                        <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                        Backend: <span className="text-emerald-400 font-medium">{m.backend}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <p className="mt-5 text-xs text-gray-600 italic">
                  To change models, edit <code className="bg-gray-800 px-1 py-0.5 rounded">backend/app/ai_gateway/registry.py</code> and rebuild the backend container.
                </p>
              </section>
            )}

            {/* ── Knowledge Bases ── */}
            {tab === "knowledge" && (
              <section>
                <div className="flex items-center justify-between mb-5">
                  <div>
                    <h2 className="text-lg font-semibold text-white mb-1">Knowledge Base Collections</h2>
                    <p className="text-sm text-gray-400">Workspaces that group uploaded documents for RAG retrieval.</p>
                  </div>
                  <Link
                    href="/knowledge-base"
                    className="text-sm text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1"
                  >
                    Manage →
                  </Link>
                </div>
                <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700">
                  <table className="w-full text-sm text-left text-gray-300">
                    <thead className="bg-gray-700/50 text-gray-400 uppercase text-xs">
                      <tr>
                        <th className="px-6 py-3">Workspace</th>
                        <th className="px-6 py-3">Documents</th>
                        <th className="px-6 py-3">Last Updated</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-700">
                      {kb.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="px-6 py-8 text-center text-gray-500">No workspaces created yet.</td>
                        </tr>
                      ) : (
                        kb.map((ws) => (
                          <tr key={ws.workspace_name} className="hover:bg-gray-700/30 transition-colors">
                            <td className="px-6 py-4 font-medium text-white capitalize">{ws.workspace_name}</td>
                            <td className="px-6 py-4">
                              <span className="px-2.5 py-1 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full text-xs font-medium">
                                {ws.document_count} doc{ws.document_count !== 1 ? "s" : ""}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-gray-400 text-xs">
                              {ws.last_updated
                                ? new Date(ws.last_updated + "Z").toLocaleString()
                                : "—"}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* ── System ── */}
            {tab === "system" && system && (
              <section className="space-y-6">
                <div>
                  <h2 className="text-lg font-semibold text-white mb-1">System Status</h2>
                  <p className="text-sm text-gray-400">
                    Air-gapped deployment — all AI inference and data stays on-premises.
                  </p>
                </div>

                {/* Network isolation card */}
                <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                        <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400">External Network Isolation</p>
                        {networkLoading ? (
                          <p className="text-sm text-gray-500 animate-pulse">Probing endpoints…</p>
                        ) : network ? (
                          <p className={`text-sm font-bold ${network.isolation_verified ? "text-emerald-400" : "text-red-400"}`}>
                            {network.isolation_verified ? "✓ All blocked" : "⚠ Leak detected"}
                          </p>
                        ) : (
                          <p className="text-sm text-gray-500">Not available</p>
                        )}
                      </div>
                    </div>
                  </div>

                  {network && !networkLoading && (
                    <div className="divide-y divide-gray-700/50 border border-gray-700 rounded-lg overflow-hidden">
                      {Object.entries(network.endpoints).map(([label, ep]) => (
                        <div key={label} className="flex items-center justify-between px-4 py-2.5">
                          <div>
                            <p className="text-xs text-gray-300">{label}</p>
                            <p className="text-[10px] text-gray-600 font-mono">{ep.host}</p>
                          </div>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${
                            ep.status === "blocked"
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                              : ep.status === "timeout"
                              ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                              : "bg-red-500/10 text-red-400 border-red-500/20"
                          }`}>
                            {ep.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {network && (
                    <p className="text-[10px] text-gray-600 mt-3 leading-relaxed">{network.note}</p>
                  )}
                </div>

                {/* Live checks */}
                <div className="bg-gray-800 border border-gray-700 rounded-xl divide-y divide-gray-700">
                  {[
                    { label: "Ollama (Local LLM)", status: system.ollama_status },
                    { label: "PostgreSQL (Database)", status: system.database_status },
                  ].map((item) => (
                    <div key={item.label} className="px-6 py-4 flex items-center justify-between">
                      <span className="text-sm text-gray-300">{item.label}</span>
                      <span
                        className={`flex items-center text-xs font-medium px-2.5 py-1 rounded-full border ${
                          item.status === "reachable"
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            : "bg-red-500/10 text-red-400 border-red-500/20"
                        }`}
                      >
                        <StatusDot ok={item.status === "reachable"} />
                        {item.status}
                      </span>
                    </div>
                  ))}
                  <div className="px-6 py-4 flex items-center justify-between">
                    <span className="text-sm text-gray-300">Architecture</span>
                    <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                      {system.architecture}
                    </span>
                  </div>
                  <div className="px-6 py-4 flex items-center justify-between">
                    <span className="text-sm text-gray-300">Server Time (UTC)</span>
                    <span className="text-xs text-gray-400 font-mono">{system.server_time}</span>
                  </div>
                  <div className="px-6 py-4 flex items-center justify-between">
                    <span className="text-sm text-gray-300">Backend Uptime</span>
                    <span className="text-xs text-gray-400 font-mono">{system.uptime}</span>
                  </div>
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
