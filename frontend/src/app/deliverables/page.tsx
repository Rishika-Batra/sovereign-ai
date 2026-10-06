"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

interface DeliverableInfo {
  id: number;
  filename: string;
  file_type: string;
  generated_by: number | null;
  created_at: string;
  download_path: string;
}

function timeSince(dateString: string) {
  const date = new Date(dateString);
  const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000);
  
  let interval = seconds / 31536000;
  if (interval > 1) return Math.floor(interval) + " years ago";
  interval = seconds / 2592000;
  if (interval > 1) return Math.floor(interval) + " months ago";
  interval = seconds / 86400;
  if (interval > 1) {
    if (Math.floor(interval) === 1) return "yesterday";
    return Math.floor(interval) + " days ago";
  }
  interval = seconds / 3600;
  if (interval > 1) return Math.floor(interval) + " hours ago";
  interval = seconds / 60;
  if (interval > 1) return Math.floor(interval) + " min ago";
  return Math.floor(seconds) + " seconds ago";
}

function getIconForType(type: string) {
  switch (type.toLowerCase()) {
    case 'pdf': return '📄';
    case 'docx': return '📝';
    case 'xlsx': return '📊';
    case 'pptx': return '📽️';
    default: return '📁';
  }
}

function DeliverablesContent() {
  const [deliverables, setDeliverables] = useState<DeliverableInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const router = useRouter();

  const fetchDeliverables = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }

    setForbidden(false);

    try {
      const res = await fetch(`${API_BASE}/api/deliverables`, {
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
        throw new Error(`Failed to load deliverables (HTTP ${res.status})`);
      }

      const data: DeliverableInfo[] = await res.json();
      setDeliverables(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchDeliverables();
  }, [fetchDeliverables]);

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
          You do not have permission to view or manage deliverables.
        </p>
        <Link href="/chat" className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md transition-colors">
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
            <h1 className="text-xl font-bold text-white">Deliverables</h1>
          </div>
        </div>
      </header>

      <main className="p-6 max-w-7xl mx-auto">
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
                  <th className="px-6 py-3 font-medium">Type</th>
                  <th className="px-6 py-3 font-medium">Name</th>
                  <th className="px-6 py-3 font-medium">Created</th>
                  <th className="px-6 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {deliverables.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-8 text-center text-gray-500">
                      No deliverables generated yet.
                    </td>
                  </tr>
                ) : (
                  deliverables.map((doc) => {
                    const downloadUrl = `${API_BASE}${doc.download_path}?token=${localStorage.getItem("access_token") || ''}`;
                    return (
                      <tr key={doc.id} className="hover:bg-gray-700/30 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap text-xl" title={doc.file_type}>
                          {getIconForType(doc.file_type)}
                        </td>
                        <td className="px-6 py-4 font-medium text-white break-all">{doc.filename}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-gray-400">
                          {timeSince(doc.created_at)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right">
                          <div className="flex justify-end gap-3">
                            <a 
                              href={downloadUrl} 
                              target="_blank"
                              rel="noreferrer"
                              className="text-indigo-400 hover:text-indigo-300 font-medium text-sm transition-colors"
                            >
                              Preview
                            </a>
                            <a 
                              href={downloadUrl} 
                              download
                              className="px-3 py-1.5 bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-600 hover:text-white rounded text-sm transition-colors"
                            >
                              Download
                            </a>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}

export default function DeliverablesPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>
    }>
      <DeliverablesContent />
    </Suspense>
  );
}
