"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

interface DocumentInfo {
  document_id: string;
  filename: string;
  file_type: string;
  status: string;
  workspace: string;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  is_restricted?: boolean;
}

interface WorkspaceInfo {
  id: number;
  name: string;
  created_at: string;
}

function DocumentsContent() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [userRole, setUserRole] = useState<string>("user");

  interface AclEntry {
    id: number;
    user_id: number | null;
    role: string | null;
  }

  // ACL Modal state
  const [aclModalDoc, setAclModalDoc] = useState<DocumentInfo | null>(null);
  const [aclEntries, setAclEntries] = useState<AclEntry[]>([]);
  const [aclLoading, setAclLoading] = useState(false);
  const [aclError, setAclError] = useState<string | null>(null);
  const [newAclType, setNewAclType] = useState<"role" | "user">("role");
  const [newAclValue, setNewAclValue] = useState("");

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [isDiagram, setIsDiagram] = useState(false);
  const [uploadWorkspace, setUploadWorkspace] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceFilter = searchParams.get("workspace");

  const fetchWorkspaces = useCallback(async (token: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/documents/workspaces`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: WorkspaceInfo[] = await res.json();
        setWorkspaces(data);
        if (data.length > 0) {
          setUploadWorkspace(workspaceFilter || data[0].name);
        }
      }
    } catch {
      // Non-fatal: workspace dropdown won't populate
    }
  }, [workspaceFilter]);

  const fetchDocuments = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }

    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      setUserRole(payload.role || "user");
    } catch (e) {
      console.error(e);
    }

    setForbidden(false);

    try {
      const res = await fetch(`${API_BASE}/api/documents`, {
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
        throw new Error(`Failed to load documents (HTTP ${res.status})`);
      }

      const data: DocumentInfo[] = await res.json();
      setDocuments(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) fetchWorkspaces(token);
    fetchDocuments();
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, [fetchDocuments, fetchWorkspaces]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setSelectedFileName(file.name);
    setIsDiagram(false);
  };

  const handleConfirmUpload = async () => {
    if (!selectedFile) return;

    const token = localStorage.getItem("access_token");
    if (!token) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("is_diagram", isDiagram.toString());
    if (uploadWorkspace) formData.append("workspace", uploadWorkspace);

    try {
      const response = await fetch(`${API_BASE}/api/documents/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (response.status === 401) {
        localStorage.removeItem("access_token");
        router.push("/");
        return;
      }

      if (response.status === 403) {
        setError("You do not have permission to upload documents.");
        return;
      }

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Upload error");
      }
      if (data.status === "duplicate") {
        setError("Duplicate, already uploaded");
      } else {
        setSelectedFile(null);
        setSelectedFileName(null);
        setIsDiagram(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }

      await fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleOpenAclModal = async (doc: DocumentInfo) => {
    setAclModalDoc(doc);
    setAclLoading(true);
    setAclError(null);
    setAclEntries([]);
    const token = localStorage.getItem("access_token");
    try {
      const res = await fetch(`${API_BASE}/api/documents/${doc.document_id}/acl`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        if (res.status === 403) throw new Error("Permission denied. You do not have 'documents.manage' permission to view or edit access.");
        throw new Error("Failed to load ACL");
      }
      setAclEntries(await res.json());
    } catch (err) {
      setAclError(err instanceof Error ? err.message : "Error loading ACL");
    } finally {
      setAclLoading(false);
    }
  };

  const handleAddAclEntry = async () => {
    if (!aclModalDoc || !newAclValue.trim()) return;
    const token = localStorage.getItem("access_token");
    setAclLoading(true);
    setAclError(null);
    
    const payload = newAclType === "role" 
      ? { role: newAclValue.trim().toLowerCase() }
      : { user_id: parseInt(newAclValue.trim()) };
    
    try {
      const res = await fetch(`${API_BASE}/api/documents/${aclModalDoc.document_id}/acl`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Failed to add ACL entry");
      const addedEntry = await res.json();
      setAclEntries([...aclEntries, addedEntry]);
      setNewAclValue("");
      fetchDocuments(); // Refresh badge in table
    } catch (err) {
      setAclError(err instanceof Error ? err.message : "Error adding ACL entry");
    } finally {
      setAclLoading(false);
    }
  };

  const handleRemoveAclEntry = async (acl_id: number) => {
    if (!aclModalDoc) return;
    const token = localStorage.getItem("access_token");
    setAclLoading(true);
    setAclError(null);
    try {
      const res = await fetch(`${API_BASE}/api/documents/${aclModalDoc.document_id}/acl/${acl_id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to remove ACL entry");
      setAclEntries(aclEntries.filter(e => e.id !== acl_id));
      fetchDocuments(); // Refresh badge in table
    } catch (err) {
      setAclError(err instanceof Error ? err.message : "Error removing ACL entry");
    } finally {
      setAclLoading(false);
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
          You do not have permission to view or manage documents.
        </p>
        <Link href="/chat" className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition-colors">
          Return to Chat
        </Link>
      </div>
    );
  }

  const filteredDocs = documents
    .filter((doc) => !workspaceFilter || doc.workspace === workspaceFilter)
    .filter((doc) => doc.filename.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="min-h-screen bg-gray-900 text-gray-200">
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link href={workspaceFilter ? "/knowledge-base" : "/chat"} className="text-gray-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </Link>
          <div>
            <h1 className="text-xl font-bold text-white">Documents</h1>
            {workspaceFilter && (
              <p className="text-xs text-indigo-400 mt-0.5">
                Filtered by workspace: <span className="font-semibold">{workspaceFilter}</span>
              </p>
            )}
          </div>
        </div>
      </header>

      <main className="p-6 max-w-7xl mx-auto">
        <div className="flex flex-col sm:flex-row gap-4 mb-6 justify-between items-start sm:items-center">
          <input
            type="text"
            placeholder="Search documents by name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full sm:w-96 px-4 py-2 bg-gray-800 border border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              className="hidden"
              accept=".pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg"
            />

            {selectedFileName && (
              <span className="text-sm text-gray-400 truncate max-w-[150px]" title={selectedFileName}>
                {selectedFileName}
              </span>
            )}

            {selectedFile && workspaces.length > 0 && (
              <select
                value={uploadWorkspace}
                onChange={(e) => setUploadWorkspace(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-md px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.name}>{ws.name}</option>
                ))}
              </select>
            )}

            {selectedFile && (
              <button
                type="button"
                onClick={() => setIsDiagram((v) => !v)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border transition-all ${
                  isDiagram
                    ? "bg-indigo-600/20 border-indigo-500/50 text-indigo-300"
                    : "bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200"
                }`}
              >
                {isDiagram ? "📐 Diagram" : "Diagram?"}
              </button>
            )}

            {selectedFile && !uploading && (
              <>
                <button
                  type="button"
                  onClick={handleConfirmUpload}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-md transition-colors"
                >
                  Upload
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedFile(null);
                    setSelectedFileName(null);
                    setIsDiagram(false);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  className="px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-red-400 rounded-md transition-colors"
                >
                  Cancel
                </button>
              </>
            )}

            {!selectedFile && (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || loading}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-md transition-colors flex items-center gap-2 disabled:opacity-50"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                Upload Document
              </button>
            )}

            {uploading && (
              <span className="text-sm text-gray-400 animate-pulse">Uploading…</span>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-md text-red-200">{error}</div>
        )}

        {loading ? (
          <div className="flex justify-center p-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
          </div>
        ) : (
          <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700">
            <table className="w-full text-left text-sm text-gray-300">
              <thead className="bg-gray-700/50 text-gray-400 uppercase text-xs">
                <tr>
                  <th className="px-6 py-3 font-medium">Name</th>
                  <th className="px-6 py-3 font-medium">Type</th>
                  <th className="px-6 py-3 font-medium">Workspace</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                  <th className="px-6 py-3 font-medium">Modified</th>
                  {(userRole === "admin" || userRole === "manager") && (
                    <th className="px-6 py-3 font-medium text-right">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {filteredDocs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                      No documents found.
                    </td>
                  </tr>
                ) : (
                  filteredDocs.map((doc) => (
                    <tr key={doc.document_id} className="hover:bg-gray-700/30 transition-colors">
                      <td className="px-6 py-4 font-medium text-white break-all flex items-center gap-2">
                        {doc.is_restricted && (
                          <svg className="w-4 h-4 text-amber-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <title>Access Restricted</title>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                          </svg>
                        )}
                        {doc.filename}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className="px-2 py-1 bg-gray-700 rounded text-xs font-mono text-gray-300">{doc.file_type}</span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">{doc.workspace}</td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {doc.status === "completed" && (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Completed
                          </span>
                        )}
                        {doc.status === "processing" && (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            <span className="w-3 h-3 border-2 border-amber-500/30 border-t-amber-500 rounded-full animate-spin"></span>Processing
                          </span>
                        )}
                        {doc.status === "failed" && (
                          <span
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 cursor-help"
                            title={doc.error_message || "Unknown error"}
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>Failed
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-gray-400">
                        {new Date(doc.updated_at).toLocaleString()}
                      </td>
                      {(userRole === "admin" || userRole === "manager") && (
                        <td className="px-6 py-4 whitespace-nowrap text-right">
                          <button
                            onClick={() => handleOpenAclModal(doc)}
                            className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                              doc.is_restricted 
                                ? "bg-amber-500/10 border-amber-500/30 text-amber-400 hover:bg-amber-500/20"
                                : "bg-gray-800 border-gray-600 text-gray-300 hover:text-white hover:border-gray-500"
                            }`}
                          >
                            Access
                          </button>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {/* ACL Modal */}
      {aclModalDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col max-h-[90vh]">
            <div className="px-6 py-4 border-b border-gray-700 flex justify-between items-center">
              <h2 className="text-lg font-bold text-white">Access Control</h2>
              <button onClick={() => setAclModalDoc(null)} className="text-gray-400 hover:text-white">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto">
              <p className="text-sm text-gray-400 mb-6">
                Manage access for <span className="text-white font-mono">{aclModalDoc.filename}</span>. 
                If no restrictions are set, the document is visible to everyone in the <span className="text-white">{aclModalDoc.workspace}</span> workspace.
              </p>

              {aclError && <div className="mb-4 p-3 bg-red-900/50 border border-red-500 text-red-200 text-sm rounded-md">{aclError}</div>}

              <div className="mb-6">
                <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Current Restrictions</h3>
                {aclLoading && aclEntries.length === 0 ? (
                  <div className="text-sm text-gray-400">Loading...</div>
                ) : aclEntries.length === 0 ? (
                  <div className="text-sm text-gray-400 p-3 bg-gray-900/50 rounded border border-gray-700 border-dashed">
                    No restrictions. Open to all workspace members.
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {aclEntries.map((e, i) => (
                      <li key={i} className="flex items-center justify-between p-2.5 bg-gray-900/50 border border-gray-700 rounded-md">
                        <div className="flex items-center gap-2">
                          <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4" /></svg>
                          <span className="text-sm text-gray-200">
                            {e.role ? `Role: ${e.role}` : `User ID: ${e.user_id}`}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-gray-500 uppercase">Read</span>
                          <button
                            onClick={() => handleRemoveAclEntry(e.id)}
                            disabled={aclLoading}
                            className="text-gray-400 hover:text-red-400 transition-colors"
                            title="Remove Access"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Add Restriction</h3>
                <div className="flex gap-2">
                  <select
                    value={newAclType}
                    onChange={(e) => setNewAclType(e.target.value as "role" | "user")}
                    className="bg-gray-950 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="role">Role</option>
                    <option value="user">User ID</option>
                  </select>
                  <input
                    type="text"
                    value={newAclValue}
                    onChange={(e) => setNewAclValue(e.target.value)}
                    placeholder={newAclType === "role" ? "e.g. manager" : "e.g. 1"}
                    className="flex-1 px-3 py-2 bg-gray-950 border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
                    onKeyDown={(e) => { if (e.key === "Enter") handleAddAclEntry(); }}
                  />
                  <button
                    onClick={handleAddAclEntry}
                    disabled={aclLoading || !newAclValue.trim()}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-md transition-colors disabled:opacity-50"
                  >
                    Add
                  </button>
                </div>
              </div>

            </div>
            
            <div className="px-6 py-4 border-t border-gray-700 bg-gray-800/50 flex justify-end">
              <button
                onClick={() => setAclModalDoc(null)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm font-medium rounded-md transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default function DocumentsPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>
    }>
      <DocumentsContent />
    </Suspense>
  );
}
