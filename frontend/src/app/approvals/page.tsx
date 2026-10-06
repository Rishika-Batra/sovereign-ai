"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/api";
import Link from "next/link";

interface PendingAction {
  id: number;
  user_id: number;
  session_id: number | null;
  tool: string;
  arguments: Record<string, unknown>;
  status: string;
  created_at: string;
}

export default function ApprovalsPage() {
  const [actions, setActions] = useState<PendingAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [userRole, setUserRole] = useState<string | null>(null);
  
  const [editingActionId, setEditingActionId] = useState<number | null>(null);
  const [editedArgs, setEditedArgs] = useState<string>("");

  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }
    setUserRole(localStorage.getItem("user_role"));
    fetchApprovals();
  }, [router]);

  const fetchApprovals = async () => {
    const token = localStorage.getItem("access_token");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/approvals`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to load approvals");
      const data = await res.json();
      setActions(data);
    } catch (err: unknown) {
      setError((err instanceof Error ? err.message : "Request failed"));
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (id: number) => {
    const token = localStorage.getItem("access_token");
    try {
      const res = await fetch(`${API_BASE}/api/approvals/${id}/approve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const d = await res.json();
        alert(`Error: ${d.detail || "Failed to approve"}`);
        return;
      }
      alert("Action approved!");
      fetchApprovals();
    } catch (err: unknown) {
      alert("Error: " + (err instanceof Error ? err.message : "Request failed"));
    }
  };

  const handleReject = async (id: number) => {
    const reason = prompt("Enter a reason for rejection (optional):");
    if (reason === null) return; // User cancelled

    const token = localStorage.getItem("access_token");
    try {
      const res = await fetch(`${API_BASE}/api/approvals/${id}/reject`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({ reason }),
      });
      if (!res.ok) {
        const d = await res.json();
        alert(`Error: ${d.detail || "Failed to reject"}`);
        return;
      }
      alert("Action rejected.");
      fetchApprovals();
    } catch (err: unknown) {
      alert("Error: " + (err instanceof Error ? err.message : "Request failed"));
    }
  };

  const handleModify = async (id: number) => {
    try {
      const parsedArgs = JSON.parse(editedArgs);
      const token = localStorage.getItem("access_token");
      const res = await fetch(`${API_BASE}/api/approvals/${id}/modify`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({ arguments: parsedArgs }),
      });
      if (!res.ok) {
        const d = await res.json();
        alert(`Error: ${d.detail || "Failed to modify"}`);
        return;
      }
      alert("Action modified and approved!");
      setEditingActionId(null);
      fetchApprovals();
    } catch (err: unknown) {
      alert("Invalid JSON arguments or network error: " + (err instanceof Error ? err.message : "Request failed"));
    }
  };

  const startEdit = (action: PendingAction) => {
    setEditingActionId(action.id);
    setEditedArgs(JSON.stringify(action.arguments, null, 2));
  };

  const cancelEdit = () => {
    setEditingActionId(null);
    setEditedArgs("");
  };

  const canApprove = userRole === "admin" || userRole === "manager";

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 font-sans">
      <main className="flex-1 flex flex-col items-center pt-10 px-4 overflow-y-auto">
        <div className="w-full max-w-4xl flex items-center justify-between mb-8">
          <h1 className="text-3xl font-light text-blue-400">Approvals Dashboard</h1>
          <Link href="/chat">
            <button className="px-4 py-2 bg-gray-800 text-sm rounded hover:bg-gray-700 transition">
              Back to Chat
            </button>
          </Link>
        </div>

        <div className="w-full max-w-4xl">
          {loading && <p>Loading...</p>}
          {error && <p className="text-red-400">{error}</p>}
          
          {!loading && actions.length === 0 && (
            <div className="p-8 bg-gray-800/50 rounded text-center border border-gray-700 text-gray-400">
              No pending actions.
            </div>
          )}

          {!loading && actions.length > 0 && (
            <div className="space-y-4">
              {actions.map((action) => (
                <div key={action.id} className="p-6 bg-gray-800 rounded-lg shadow-md border border-gray-700">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h2 className="text-xl font-medium text-blue-300 mb-1">
                        Tool: <span className="font-mono text-gray-200">{action.tool}</span>
                      </h2>
                      <p className="text-sm text-gray-400">
                        Requested by User {action.user_id} on {new Date(action.created_at).toLocaleString()}
                        {action.session_id && ` | Session ${action.session_id}`}
                      </p>
                    </div>
                    <div>
                      <span className="px-3 py-1 bg-yellow-900/50 text-yellow-400 text-xs rounded-full border border-yellow-700/50 uppercase tracking-wider">
                        {action.status}
                      </span>
                    </div>
                  </div>

                  <div className="bg-gray-900 p-4 rounded-md mb-4 overflow-x-auto border border-gray-800">
                    {editingActionId === action.id ? (
                      <textarea
                        className="w-full h-40 bg-gray-900 text-gray-100 font-mono text-sm p-2 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 border border-gray-700"
                        value={editedArgs}
                        onChange={(e) => setEditedArgs(e.target.value)}
                      />
                    ) : (
                      <pre className="text-sm font-mono text-gray-300">
                        {JSON.stringify(action.arguments, null, 2)}
                      </pre>
                    )}
                  </div>

                  {canApprove && (
                    <div className="flex gap-3 justify-end mt-4 pt-4 border-t border-gray-700">
                      {editingActionId === action.id ? (
                        <>
                          <button
                            onClick={cancelEdit}
                            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleModify(action.id)}
                            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-500 transition shadow-[0_0_10px_rgba(37,99,235,0.4)]"
                          >
                            Save & Approve
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => startEdit(action)}
                            className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 hover:text-white transition"
                          >
                            Modify
                          </button>
                          <button
                            onClick={() => handleReject(action.id)}
                            className="px-4 py-2 bg-red-900/50 text-red-300 border border-red-700/50 rounded hover:bg-red-800 transition"
                          >
                            Reject
                          </button>
                          <button
                            onClick={() => handleApprove(action.id)}
                            className="px-4 py-2 bg-green-700 text-white rounded hover:bg-green-600 transition shadow-[0_0_10px_rgba(21,128,61,0.4)]"
                          >
                            Approve
                          </button>
                        </>
                      )}
                    </div>
                  )}
                  {!canApprove && (
                    <p className="text-xs text-gray-500 italic text-right mt-2">
                      Only managers and admins can approve this action.
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
