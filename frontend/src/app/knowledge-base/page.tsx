"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

interface KBSummary {
  workspace_name: string;
  document_count: number;
  last_updated: string | null;
}

const COLLECTION_COLORS = [
  "from-indigo-600/20 to-indigo-800/10 border-indigo-500/30",
  "from-violet-600/20 to-violet-800/10 border-violet-500/30",
  "from-sky-600/20 to-sky-800/10 border-sky-500/30",
  "from-emerald-600/20 to-emerald-800/10 border-emerald-500/30",
  "from-amber-600/20 to-amber-800/10 border-amber-500/30",
  "from-rose-600/20 to-rose-800/10 border-rose-500/30",
  "from-cyan-600/20 to-cyan-800/10 border-cyan-500/30",
  "from-fuchsia-600/20 to-fuchsia-800/10 border-fuchsia-500/30",
];

export default function KnowledgeBasePage() {
  const [collections, setCollections] = useState<KBSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  // New workspace modal state
  const [showModal, setShowModal] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const router = useRouter();

  const fetchCollections = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/api/documents/knowledge-base`, {
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

      if (!res.ok) {
        throw new Error(`Failed to load knowledge base (HTTP ${res.status})`);
      }

      const data: KBSummary[] = await res.json();
      setCollections(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchCollections();
  }, [fetchCollections]);

  const handleCreateWorkspace = async () => {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    const name = newWorkspaceName.trim();
    if (!name) {
      setCreateError("Workspace name cannot be empty.");
      return;
    }

    setCreating(true);
    setCreateError(null);

    try {
      const res = await fetch(`${API_BASE}/api/documents/workspaces`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Failed to create workspace (HTTP ${res.status})`);
      }

      setShowModal(false);
      setNewWorkspaceName("");
      await fetchCollections();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create workspace");
    } finally {
      setCreating(false);
    }
  };

  if (forbidden) {
    return (
      <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mb-4">
          <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-white mb-2">Access Denied</h1>
        <p className="text-gray-400 max-w-md mb-6">
          You do not have permission to view the Knowledge Base.
        </p>
        <Link href="/chat" className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition-colors">
          Return to Chat
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-200">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link href="/chat" className="text-gray-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </Link>
          <div>
            <h1 className="text-xl font-bold text-white">Knowledge Base</h1>
            <p className="text-xs text-gray-400 mt-0.5">Manage document collections by workspace</p>
          </div>
        </div>
        <button
          onClick={() => { setShowModal(true); setCreateError(null); setNewWorkspaceName(""); }}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-md transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Knowledge
        </button>
      </header>

      <main className="p-6 max-w-7xl mx-auto">
        {error && (
          <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-md text-red-200">{error}</div>
        )}

        {loading ? (
          <div className="flex justify-center p-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
          </div>
        ) : collections.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-20 h-20 bg-gray-800 rounded-full flex items-center justify-center mb-4">
              <svg className="w-10 h-10 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-gray-300 mb-2">No collections yet</h2>
            <p className="text-gray-500 mb-6">Create your first knowledge base workspace.</p>
            <button
              onClick={() => { setShowModal(true); setCreateError(null); setNewWorkspaceName(""); }}
              className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition-colors"
            >
              + New Knowledge
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {collections.map((col, idx) => (
              <Link
                key={col.workspace_name}
                href={`/documents?workspace=${encodeURIComponent(col.workspace_name)}`}
                className={`group relative bg-gradient-to-br ${COLLECTION_COLORS[idx % COLLECTION_COLORS.length]} border rounded-xl p-6 hover:scale-[1.02] transition-all duration-200 cursor-pointer`}
              >
                {/* Icon */}
                <div className="w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center mb-4">
                  <svg className="w-5 h-5 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                </div>

                {/* Name */}
                <h2 className="text-base font-semibold text-white capitalize mb-1 group-hover:text-indigo-200 transition-colors">
                  {col.workspace_name}
                </h2>

                {/* Doc count */}
                <p className="text-sm text-gray-400">
                  {col.document_count === 0
                    ? "No documents yet"
                    : `${col.document_count} doc${col.document_count !== 1 ? "s" : ""}`}
                </p>

                {/* Last updated */}
                {col.last_updated && (
                  <p className="text-xs text-gray-500 mt-2">
                    Updated {new Date(col.last_updated).toLocaleDateString()}
                  </p>
                )}

                {/* Chevron */}
                <svg className="w-4 h-4 text-gray-500 group-hover:text-gray-300 absolute top-4 right-4 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            ))}
          </div>
        )}
      </main>

      {/* New Workspace Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl p-6 w-full max-w-md mx-4">
            <h2 className="text-lg font-semibold text-white mb-1">New Knowledge Base</h2>
            <p className="text-sm text-gray-400 mb-4">
              Create a new workspace to organise documents. It will appear as a collection here and become selectable in the upload flow immediately.
            </p>

            <label className="block text-xs font-medium text-gray-400 mb-1">Workspace name</label>
            <input
              type="text"
              value={newWorkspaceName}
              onChange={(e) => setNewWorkspaceName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateWorkspace()}
              placeholder="e.g. safety, legal, engineering"
              autoFocus
              className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-md text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-3"
            />

            {createError && (
              <p className="text-sm text-red-400 mb-3">{createError}</p>
            )}

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => { setShowModal(false); setNewWorkspaceName(""); setCreateError(null); }}
                className="px-4 py-2 text-sm text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 rounded-md transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateWorkspace}
                disabled={creating || !newWorkspaceName.trim()}
                className="px-4 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition-colors disabled:opacity-50"
              >
                {creating ? "Creating…" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
