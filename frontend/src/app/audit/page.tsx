"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

interface AuditLog {
  id: number;
  user_id?: number | null;
  user_email?: string | null;
  action: string;
  resource?: string | null;
  details?: Record<string, unknown> | null;
  created_at: string;
}

export default function AuditLogPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const router = useRouter();

  const fetchAuditLogs = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }

    setLoading(true);
    setError(null);
    setForbidden(false);

    try {
      const res = await fetch(`${API_BASE}/api/audit/logs`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
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
        throw new Error(`Failed to load audit logs (HTTP ${res.status})`);
      }

      const data: AuditLog[] = await res.json();
      // Ensure newest-first sorting
      const sorted = [...data].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setLogs(sorted);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/");
  };

  const formatTimestamp = (iso: string) => {
    try {
      const date = new Date(iso);
      return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      }).format(date);
    } catch {
      return iso;
    }
  };

  const renderActionBadge = (action: string) => {
    switch (action) {
      case "login":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            login
          </span>
        );
      case "chat_message":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            chat_message
          </span>
        );
      case "document_upload":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            document_upload
          </span>
        );
      case "agent_run":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
            agent_run
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-700/40 text-gray-300 border border-gray-600/40">
            {action}
          </span>
        );
    }
  };

  const filteredLogs = logs.filter((log) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      log.action?.toLowerCase().includes(q) ||
      log.user_email?.toLowerCase().includes(q) ||
      log.resource?.toLowerCase().includes(q) ||
      JSON.stringify(log.details || {}).toLowerCase().includes(q)
    );
  });

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 font-sans flex flex-col">
      {/* Header */}
      <header className="flex-none flex items-center justify-between px-6 py-4 bg-gray-900 border-b border-gray-800 shadow-sm z-10">
        <div className="flex items-center space-x-3">
          <Link
            href="/chat"
            className="flex items-center gap-1.5 text-sm font-medium text-gray-400 hover:text-white transition-colors px-2.5 py-1 rounded-md hover:bg-gray-800"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back to Chat
          </Link>
          <div className="h-4 w-px bg-gray-700" />
          <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-500">
            Audit Logs
          </h1>
          <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-medium">
            Admin Compliance
          </span>
        </div>

        <div className="flex items-center space-x-3">
          {!forbidden && (
            <button
              onClick={fetchAuditLogs}
              disabled={loading}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700 disabled:opacity-50"
              title="Refresh logs"
            >
              <svg
                className={`w-3.5 h-3.5 ${loading ? "animate-spin text-blue-400" : "text-gray-400"}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Refresh
            </button>
          )}
          <button
            onClick={handleLogout}
            className="text-sm font-medium text-gray-400 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 p-4 sm:p-8 max-w-7xl w-full mx-auto">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 space-y-4">
            <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-gray-400 text-sm">Loading audit logs...</p>
          </div>
        ) : forbidden ? (
          /* Permission Denied UI */
          <div className="max-w-md mx-auto my-16 bg-gray-900 border border-red-500/20 rounded-2xl p-8 text-center shadow-xl">
            <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-100 mb-2">Access Restricted</h2>
            <p className="text-sm text-gray-400 mb-6 leading-relaxed">
              You don&apos;t have permission to view this page. Viewing the system audit log requires the{" "}
              <span className="text-red-400 font-mono text-xs font-semibold bg-red-950/50 px-1.5 py-0.5 rounded border border-red-800/40">
                audit.view
              </span>{" "}
              role permission.
            </p>
            <Link
              href="/chat"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors shadow-lg shadow-blue-600/20"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              Return to Chat
            </Link>
          </div>
        ) : error ? (
          /* Generic Error State */
          <div className="max-w-md mx-auto my-16 bg-gray-900 border border-gray-800 rounded-2xl p-8 text-center">
            <p className="text-red-400 mb-4">{error}</p>
            <button
              onClick={fetchAuditLogs}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
            >
              Retry
            </button>
          </div>
        ) : (
          /* Audit Logs Table */
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-200">System Activity Stream</h2>
                <p className="text-xs text-gray-400">
                  Displaying {filteredLogs.length} of {logs.length} most recent activities
                </p>
              </div>

              {/* Quick filter */}
              <div className="w-full sm:w-72">
                <input
                  type="text"
                  placeholder="Filter by action, user, or details..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </div>

            {filteredLogs.length === 0 ? (
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-12 text-center text-gray-500">
                <svg className="w-12 h-12 mx-auto mb-3 opacity-40 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-sm font-medium">No audit log entries found</p>
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="mt-2 text-xs text-blue-400 hover:underline"
                  >
                    Clear filter
                  </button>
                )}
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900 shadow-xl">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs sm:text-sm">
                    <thead className="bg-gray-950/60 text-gray-400 uppercase text-[11px] font-semibold tracking-wider border-b border-gray-800">
                      <tr>
                        <th scope="col" className="px-5 py-3.5 whitespace-nowrap">Timestamp</th>
                        <th scope="col" className="px-5 py-3.5 whitespace-nowrap">User</th>
                        <th scope="col" className="px-5 py-3.5 whitespace-nowrap">Action</th>
                        <th scope="col" className="px-5 py-3.5 whitespace-nowrap">Resource</th>
                        <th scope="col" className="px-5 py-3.5">Details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800/60 font-sans">
                      {filteredLogs.map((log) => (
                        <tr
                          key={log.id}
                          className="hover:bg-gray-800/40 transition-colors"
                        >
                          <td className="px-5 py-3.5 whitespace-nowrap text-gray-400 font-mono text-xs">
                            {formatTimestamp(log.created_at)}
                          </td>
                          <td className="px-5 py-3.5 whitespace-nowrap font-medium text-gray-200">
                            {log.user_email || (
                              <span className="text-gray-500 italic">Anonymous</span>
                            )}
                          </td>
                          <td className="px-5 py-3.5 whitespace-nowrap">
                            {renderActionBadge(log.action)}
                          </td>
                          <td className="px-5 py-3.5 whitespace-nowrap text-gray-300 font-mono text-xs">
                            {log.resource || "—"}
                          </td>
                          <td className="px-5 py-3.5">
                            {log.details ? (
                              <div className="max-w-xl">
                                <code className="block bg-gray-950/70 border border-gray-800 rounded px-2.5 py-1 text-xs font-mono text-gray-300 break-words whitespace-pre-wrap">
                                  {JSON.stringify(log.details)}
                                </code>
                              </div>
                            ) : (
                              <span className="text-gray-600">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
