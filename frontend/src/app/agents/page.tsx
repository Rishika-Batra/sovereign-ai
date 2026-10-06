"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

interface Agent {
  id: number;
  name: string;
  description: string;
  prompt_template: string;
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [userRole, setUserRole] = useState<string>("user");

  // Run modal state
  const [runAgent, setRunAgent] = useState<Agent | null>(null);
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [placeholders, setPlaceholders] = useState<string[]>([]);

  // Create modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newTemplate, setNewTemplate] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const router = useRouter();

  const fetchAgents = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/agents`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.status === 401) {
        localStorage.removeItem("access_token");
        router.push("/");
        return;
      }
      if (res.status === 403) {
        setForbidden(true);
        return;
      }
      if (!res.ok) throw new Error("Failed to load agents");

      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        setUserRole(payload.role || "user");
      } catch (e) {
        console.error(e);
      }

      const data = await res.json();
      setAgents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleOpenRunModal = (agent: Agent) => {
    const matches = Array.from(agent.prompt_template.matchAll(/\{([^}]+)\}/g));
    const extracted = matches.map((m) => m[1]);
    
    // Deduplicate
    const uniquePlaceholders = Array.from(new Set(extracted));
    
    setPlaceholders(uniquePlaceholders);
    setRunAgent(agent);
    
    const initialVars: Record<string, string> = {};
    uniquePlaceholders.forEach((p) => { initialVars[p] = ""; });
    setVariables(initialVars);
  };

  const handleConfirmRun = () => {
    if (!runAgent) return;
    
    // We pass variables as base64 encoded JSON in the URL to /chat
    const varsJson = JSON.stringify(variables);
    const encodedVars = btoa(encodeURIComponent(varsJson));
    
    router.push(`/chat?run_agent_id=${runAgent.id}&vars=${encodedVars}`);
  };

  const handleCreateAgent = async () => {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    if (!newName.trim() || !newDesc.trim() || !newTemplate.trim()) {
      setCreateError("All fields are required.");
      return;
    }

    setCreating(true);
    setCreateError(null);

    try {
      const res = await fetch(`${API_BASE}/api/agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: newName,
          description: newDesc,
          prompt_template: newTemplate,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to create agent");
      }

      setShowCreateModal(false);
      setNewName("");
      setNewDesc("");
      setNewTemplate("");
      await fetchAgents();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create agent");
    } finally {
      setCreating(false);
    }
  };

  if (forbidden) {
    return (
      <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center p-6 text-center">
        <h1 className="text-2xl font-bold text-white mb-2">Access Denied</h1>
        <p className="text-gray-400 mb-6">You do not have permission to view this page.</p>
        <Link href="/chat" className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md">
          Return to Chat
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-200">
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link href="/chat" className="text-gray-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </Link>
          <div>
            <h1 className="text-xl font-bold text-white">Agents</h1>
            <p className="text-xs text-gray-400 mt-0.5">Predefined AI workflows</p>
          </div>
        </div>
        {(userRole === "admin" || userRole === "manager") && (
          <button
            onClick={() => { setShowCreateModal(true); setCreateError(null); }}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-md transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Create Agent
          </button>
        )}
      </header>

      <main className="p-6 max-w-7xl mx-auto">
        {error && <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-md text-red-200">{error}</div>}

        {loading ? (
          <div className="flex justify-center p-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {agents.map((agent) => (
              <div key={agent.id} className="bg-gray-800 border border-gray-700 rounded-xl p-6 flex flex-col hover:border-gray-600 transition-colors shadow-sm">
                <div className="flex items-start justify-between mb-2">
                  <h2 className="text-lg font-bold text-white">{agent.name}</h2>
                  <div className="w-8 h-8 rounded bg-indigo-500/10 flex items-center justify-center text-indigo-400">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                </div>
                <p className="text-sm text-gray-400 mb-4 flex-grow">{agent.description}</p>
                
                <div className="mt-4 pt-4 border-t border-gray-700/50">
                  <button
                    onClick={() => handleOpenRunModal(agent)}
                    className="w-full py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm font-medium rounded-md transition-colors"
                  >
                    Run Agent
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Run Agent Modal */}
      {runAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl p-6 w-full max-w-lg">
            <h2 className="text-lg font-bold text-white mb-2">Run: {runAgent.name}</h2>
            <p className="text-sm text-gray-400 mb-6 border-b border-gray-700 pb-4">
              Fill in the parameters for this workflow.
            </p>

            {placeholders.length === 0 ? (
              <p className="text-sm text-gray-300 mb-6">This agent requires no additional parameters. Click confirm to run.</p>
            ) : (
              <div className="space-y-4 mb-6 max-h-[50vh] overflow-y-auto pr-2">
                {placeholders.map((p) => (
                  <div key={p}>
                    <label className="block text-xs font-medium text-gray-400 mb-1 capitalize">
                      {p.replace(/_/g, " ")}
                    </label>
                    <input
                      type="text"
                      value={variables[p] || ""}
                      onChange={(e) => setVariables({ ...variables, [p]: e.target.value })}
                      className="w-full px-3 py-2 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                      placeholder={`Enter ${p}...`}
                    />
                  </div>
                ))}
              </div>
            )}

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setRunAgent(null)}
                className="px-4 py-2 text-sm text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 rounded-md transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmRun}
                className="px-4 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition-colors shadow-sm"
              >
                Confirm & Run
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Agent Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl p-6 w-full max-w-xl">
            <h2 className="text-lg font-bold text-white mb-4">Create New Agent</h2>
            
            <div className="space-y-4 mb-6">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Code Reviewer"
                  className="w-full px-3 py-2 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Description</label>
                <input
                  type="text"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Briefly describe what this agent does..."
                  className="w-full px-3 py-2 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Prompt Template</label>
                <p className="text-[10px] text-gray-500 mb-2">Use curly braces for placeholders (e.g., <code className="text-gray-400 font-mono">Review the code for &#123;filename&#125;</code>)</p>
                <textarea
                  value={newTemplate}
                  onChange={(e) => setNewTemplate(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
                  placeholder="Analyze the findings for {target}..."
                />
              </div>
            </div>

            {createError && <p className="text-sm text-red-400 mb-4">{createError}</p>}

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 text-sm text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 rounded-md transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateAgent}
                disabled={creating}
                className="px-4 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition-colors disabled:opacity-50 shadow-sm"
              >
                {creating ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
