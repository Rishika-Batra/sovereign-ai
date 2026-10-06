"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

interface User {
  id: number;
  email: string;
  role: string;
  workspace: string;
  created_at: string;
}

export default function ManageUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // New user form state
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("employee");
  const [newWorkspace, setNewWorkspace] = useState("general");
  const [creating, setCreating] = useState(false);

  const router = useRouter();

  const fetchUsers = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }

    setLoading(true);
    setError(null);
    setForbidden(false);

    try {
      const res = await fetch(`${API_BASE}/api/users/`, {
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
        throw new Error(`Failed to load users (HTTP ${res.status})`);
      }

      const data: User[] = await res.json();
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = localStorage.getItem("access_token");
    if (!token) return;

    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/users/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          email: newEmail,
          password: newPassword,
          role: newRole,
          workspace: newWorkspace,
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const detail = errorData.detail;
        const message = typeof detail === "string" ? detail
          : Array.isArray(detail) ? detail.map((d: {msg?: string}) => d.msg).join(", ")
          : `Failed to create user (HTTP ${res.status})`;
        throw new Error(message);
      }

      setNewEmail("");
      setNewPassword("");
      setNewRole("employee");
      setNewWorkspace("general");
      await fetchUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setCreating(false);
    }
  };

  const handleRoleChange = async (userId: number, newRoleValue: string) => {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    try {
      const res = await fetch(`${API_BASE}/api/users/${userId}/role`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ role: newRoleValue }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to update role (HTTP ${res.status})`);
      }

      // Update local state to reflect change without full refetch
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, role: newRoleValue } : u))
      );
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update role");
    }
  };

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
      }).format(date);
    } catch {
      return iso;
    }
  };

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
            Manage Users
          </h1>
          <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-medium">
            Admin Portal
          </span>
        </div>

        <div className="flex items-center space-x-3">
          {!forbidden && (
            <button
              onClick={fetchUsers}
              disabled={loading}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700 disabled:opacity-50"
              title="Refresh users"
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
      <main className="flex-1 p-4 sm:p-8 max-w-7xl w-full mx-auto space-y-8">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 space-y-4">
            <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-gray-400 text-sm">Loading users...</p>
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
              You don&apos;t have permission to view this page. Managing users requires the{" "}
              <span className="text-red-400 font-mono text-xs font-semibold bg-red-950/50 px-1.5 py-0.5 rounded border border-red-800/40">
                users.manage
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
        ) : (
          <>
            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 text-sm">
                {error}
              </div>
            )}
            
            {/* Create User Form */}
            <section className="bg-gray-900 border border-gray-800 rounded-xl p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-200 mb-4">Create New User</h2>
              <form onSubmit={handleCreateUser} className="flex flex-wrap items-end gap-4">
                <div className="flex-1 min-w-[200px]">
                  <label className="block text-xs font-medium text-gray-400 mb-1">Email</label>
                  <input
                    type="email"
                    required
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    placeholder="user@sovereign.local"
                  />
                </div>
                <div className="flex-1 min-w-[200px]">
                  <label className="block text-xs font-medium text-gray-400 mb-1">Password</label>
                  <input
                    type="password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    placeholder="••••••••"
                  />
                </div>
                <div className="w-40">
                  <label className="block text-xs font-medium text-gray-400 mb-1">Role</label>
                  <select
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value)}
                    className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  >
                    <option value="employee">employee</option>
                    <option value="engineer">engineer</option>
                    <option value="manager">manager</option>
                    <option value="admin">admin</option>
                  </select>
                </div>
                <div className="w-48">
                  <label className="block text-xs font-medium text-gray-400 mb-1">Workspace</label>
                  <input
                    type="text"
                    required
                    value={newWorkspace}
                    onChange={(e) => setNewWorkspace(e.target.value)}
                    className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    placeholder="general"
                  />
                </div>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors shadow-sm disabled:opacity-50"
                >
                  {creating ? "Creating..." : "Create User"}
                </button>
              </form>
            </section>

            {/* Users Table */}
            <section className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900 shadow-xl">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-950/60 text-gray-400 uppercase text-[11px] font-semibold tracking-wider border-b border-gray-800">
                    <tr>
                      <th scope="col" className="px-5 py-3.5 whitespace-nowrap">ID</th>
                      <th scope="col" className="px-5 py-3.5 whitespace-nowrap">Email</th>
                      <th scope="col" className="px-5 py-3.5 whitespace-nowrap">Role</th>
                      <th scope="col" className="px-5 py-3.5 whitespace-nowrap">Workspace</th>
                      <th scope="col" className="px-5 py-3.5 whitespace-nowrap">Created At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-sans">
                    {users.map((user) => (
                      <tr
                        key={user.id}
                        className="hover:bg-gray-800/40 transition-colors"
                      >
                        <td className="px-5 py-3.5 whitespace-nowrap text-gray-400 font-mono text-xs">
                          #{user.id}
                        </td>
                        <td className="px-5 py-3.5 whitespace-nowrap font-medium text-gray-200">
                          {user.email}
                        </td>
                        <td className="px-5 py-3.5 whitespace-nowrap">
                          <select
                            value={user.role}
                            onChange={(e) => handleRoleChange(user.id, e.target.value)}
                            className="bg-gray-950 border border-gray-700 rounded-md px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 cursor-pointer hover:border-gray-600"
                          >
                            <option value="employee">employee</option>
                            <option value="engineer">engineer</option>
                            <option value="manager">manager</option>
                            <option value="admin">admin</option>
                          </select>
                        </td>
                        <td className="px-5 py-3.5 whitespace-nowrap text-gray-300 text-xs">
                          <span className="bg-gray-800 px-2 py-1 rounded-md">{user.workspace}</span>
                        </td>
                        <td className="px-5 py-3.5 whitespace-nowrap text-gray-400 font-mono text-xs">
                          {formatTimestamp(user.created_at)}
                        </td>
                      </tr>
                    ))}
                    {users.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-5 py-8 text-center text-gray-500">
                          No users found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
