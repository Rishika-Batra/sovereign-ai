"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

interface Source {
  filename: string;
  page?: number | null;
}

interface Message {
  id?: number;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: Source[];
  model_used?: string;
  steps?: { tool: string; args: Record<string, unknown>; result: string }[];
  awaiting_approval?: boolean;
  pending_action_id?: number | null;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [chatMode, setChatMode] = useState<"chat" | "agent">("chat");
  const [userRole, setUserRole] = useState<string | null>(null);
  const [isDiagram, setIsDiagram] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const router = useRouter();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasRunAgent = useRef(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
    } else {
      setUserRole(localStorage.getItem("user_role"));
    }
  }, [router]);

  useEffect(() => {
    // Only run on client-side
    if (typeof window === "undefined") return;
    
    const params = new URLSearchParams(window.location.search);
    const runAgentId = params.get("run_agent_id");
    const varsStr = params.get("vars");
    const token = localStorage.getItem("access_token");

    if (runAgentId && varsStr && token && !hasRunAgent.current) {
      hasRunAgent.current = true;
      setChatMode("agent");
      setLoading(true);
      
      let vars = {};
      try {
        vars = JSON.parse(decodeURIComponent(atob(varsStr)));
      } catch (e) {
        console.error("Failed to parse agent variables", e);
      }

      setMessages((prev) => [...prev, { role: "system", content: "🚀 Running predefined agent..." }]);

      fetch(`${API_BASE}/api/agents/${runAgentId}/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ variables: vars }),
      })
        .then(async (res) => {
          if (!res.ok) throw new Error("Failed to run agent");
          const data = await res.json();
          
          setMessages((prev) => [
            // Replace the "Running predefined agent..." message with the actual formatted prompt
            ...prev.slice(0, -1), 
            { role: "user", content: data.formatted_task },
            {
              role: "assistant",
              content: data.final_answer || "",
              steps: data.steps || [],
              awaiting_approval: data.awaiting_approval || false,
              pending_action_id: data.pending_action_id ?? null,
            }
          ]);
        })
        .catch((err) => {
          console.error(err);
          setMessages((prev) => [
            ...prev,
            { role: "system", content: "❌ Failed to execute the predefined agent." },
          ]);
        })
        .finally(() => {
          setLoading(false);
          // Remove the query parameters so we don't run it again on refresh
          router.replace("/chat");
        });
    }
  }, [router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);


  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSelectedFile(file);
    setSelectedFileName(file.name);
    setIsDiagram(false);
  };

  const handleConfirmUpload = async () => {
    if (!selectedFile) return;

    const file = selectedFile;
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    if (isDiagram) {
      formData.append("is_diagram", "true");
    }

    // Clear file state immediately so the user can queue another upload
    setSelectedFile(null);
    setSelectedFileName(null);
    setIsDiagram(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    try {
      const response = await fetch(`${API_BASE}/api/documents/upload`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (response.status === 401) {
        localStorage.removeItem("access_token");
        router.push("/");
        return;
      }
      if (response.status === 403) {
        setMessages((prev) => [
          ...prev,
          {
            role: "system",
            content: "❌ You do not have permission to upload documents.",
          },
        ]);
        return;
      }

      const data = await response.json();

      if (!response.ok) {
        setMessages((prev) => [
          ...prev,
          {
            role: "system",
            content: `❌ Failed to upload ${file.name}: ${data.detail || "Upload error"}`,
          },
        ]);
        return;
      }

      const { document_id, filename, status } = data;

      if (status === "duplicate") {
        setMessages((prev) => [
          ...prev,
          {
            role: "system",
            content: `⚠️ Duplicate, already uploaded: "${filename}"`,
          },
        ]);
        return;
      }

      // Show immediate "processing" feedback
      setMessages((prev) => [
        ...prev,
        {
          role: "system",
          content: `⏳ Uploaded "${filename}" — processing in background (extracting text, OCR, embeddings)…`,
        },
      ]);

      // Poll status endpoint until completed or failed
      const pollStatus = async () => {
        try {
          const statusRes = await fetch(
            `${API_BASE}/api/documents/${document_id}/status`,
            { headers: { Authorization: `Bearer ${token}` } }
          );
          if (!statusRes.ok) return;
          const statusData = await statusRes.json();

          if (statusData.status === "completed") {
            setMessages((prev) => [
              ...prev,
              {
                role: "system",
                content: `📄 "${statusData.filename}" processed successfully — ready to query!`,
              },
            ]);
          } else if (statusData.status === "failed") {
            setMessages((prev) => [
              ...prev,
              {
                role: "system",
                content: `❌ Processing failed for "${statusData.filename}": ${statusData.error_message || "Unknown error"}`,
              },
            ]);
          } else {
            // Still processing — poll again in 2 s
            setTimeout(pollStatus, 2000);
          }
        } catch {
          // Network error during poll — retry
          setTimeout(pollStatus, 2000);
        }
      };

      setTimeout(pollStatus, 2000);
    } catch (err) {
      console.error("Upload error:", err);
      setMessages((prev) => [
        ...prev,
        {
          role: "system",
          content: `❌ Error uploading file ${file.name}`,
        },
      ]);
    } finally {
      setUploading(false);
    }
  };


  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading || uploading) return;

    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/");
      return;
    }

    const userMsg = input.trim();
    setInput("");

    // Optimistic UI update
    const tempUserMessage: Message = { role: "user", content: userMsg };
    setMessages((prev) => [...prev, tempUserMessage]);
    setLoading(true);

    try {
      if (chatMode === "agent") {
        const response = await fetch(`${API_BASE}/api/agent/run`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ task: userMsg, session_id: sessionId }),
        });

        if (response.status === 401) {
          localStorage.removeItem("access_token");
          router.push("/");
          return;
        }
        if (response.status === 403) {
          setMessages((prev) => [
            ...prev,
            { role: "system", content: "❌ You do not have permission to run the agent." },
          ]);
          return;
        }

        if (!response.ok) {
          throw new Error("Failed to run agent");
        }

        const data = await response.json();

        if (data.session_id && !sessionId) {
          setSessionId(data.session_id);
          // Only update URL if we created a new session
          window.history.replaceState({}, "", `/chat?session_id=${data.session_id}`);
        }

        const assistantMessage: Message = {
          role: "assistant",
          content: data.final_answer || "",
          steps: data.steps || [],
          awaiting_approval: data.awaiting_approval || false,
          pending_action_id: data.pending_action_id ?? null,
        };
        setMessages((prev) => [...prev, assistantMessage]);
      } else {
        const formData = new FormData();
        formData.append("message", userMsg);
        if (sessionId) {
          formData.append("session_id", sessionId.toString());
        }

        const response = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        });

        if (response.status === 401) {
          localStorage.removeItem("access_token");
          router.push("/");
          return;
        }
        if (response.status === 403) {
          setMessages((prev) => [
            ...prev,
            { role: "system", content: "❌ You do not have permission to use the chat." },
          ]);
          return;
        }

        if (!response.ok) {
          throw new Error("Failed to send message");
        }

        const data = await response.json();

        if (!sessionId) {
          setSessionId(data.session_id);
        }

        const assistantMessage: Message = {
          role: "assistant",
          content: data.reply,
          sources: data.sources || [],
          model_used: data.model_used || "general",
        };
        setMessages((prev) => [...prev, assistantMessage]);
      }
    } catch (error) {
      console.error("Chat error:", error);
      // Remove optimistic user message on failure
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/");
  };

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 font-sans">
      <header className="flex-none flex items-center justify-between px-6 py-4 bg-gray-900 border-b border-gray-800 shadow-sm z-10">
        <div className="flex items-center space-x-3">
          <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-500">
            Sovereign AI Chat
          </h1>
          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 font-medium">
            Multi-Model RAG
          </span>
        </div>
        <div className="flex items-center space-x-2 sm:space-x-3">
          <Link
            href="/agents"
            className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700/60"
          >
            <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            Agents
          </Link>
          <Link
            href="/knowledge-base"
            className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700/60"
          >
            <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            Knowledge Base
          </Link>
          <Link
            href="/documents"
            className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700/60"
          >
            <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Documents
          </Link>
          <Link
            href="/deliverables"
            className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700/60"
          >
            <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
            </svg>
            Deliverables
          </Link>
          <Link
            href="/approvals"
            className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700/60"
          >
            <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            Approvals
          </Link>
          <Link
            href="/admin/users"
            className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700/60"
          >
            <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            Manage Users
          </Link>
          {(userRole === "admin" || userRole === "manager") && (
            <Link
              href="/audit"
              className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700/60"
            >
              <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Audit Log
            </Link>
          )}
          {userRole === "admin" && (
            <Link
              href="/settings"
              className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-gray-300 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800 border border-gray-700/60"
            >
              <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Settings
            </Link>
          )}
          <button
            onClick={handleLogout}
            className="text-sm font-medium text-gray-400 hover:text-white transition-colors px-3 py-1.5 rounded-md hover:bg-gray-800"
          >
            Logout
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 scroll-smooth">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-gray-500 space-y-4">
            <div className="w-16 h-16 rounded-full bg-gray-900 flex items-center justify-center border border-gray-800 shadow-inner">
              <svg className="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <p className="text-lg font-medium tracking-wide">How can I assist you today?</p>
            <p className="text-sm text-gray-600 max-w-sm text-center">
              Ask questions or upload documents. Queries automatically route to General (Llama 3.1) or Coding (Qwen 2.5) models.
            </p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex w-full ${
                msg.role === "user"
                  ? "justify-end"
                  : msg.role === "system"
                  ? "justify-center"
                  : "justify-start"
              }`}
            >
              {msg.role === "system" ? (
                <div className="px-4 py-2 rounded-xl bg-gray-900/90 border border-gray-800 text-xs text-gray-300 shadow-sm flex items-center space-x-2 my-1">
                  <span>{msg.content}</span>
                </div>
              ) : (
                <div className="flex flex-col max-w-[85%] md:max-w-[75%]">
                  <div
                    className={`px-5 py-3.5 rounded-2xl shadow-sm text-sm sm:text-base leading-relaxed break-words whitespace-pre-wrap ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white rounded-tr-sm self-end"
                        : "bg-gray-800 text-gray-100 rounded-tl-sm border border-gray-700/50"
                    }`}
                  >
                    {msg.awaiting_approval ? (() => {
                      // Find the tool that was blocked: last step whose tool starts with "generate_"
                      const blockedTool = msg.steps?.slice().reverse().find(s => s.tool?.startsWith("generate_"))?.tool
                        ?? msg.steps?.[msg.steps.length - 1]?.tool
                        ?? "a high-risk action";
                      return (
                        <div className="bg-yellow-900/20 border border-yellow-600/50 rounded-xl p-4 w-full shadow-md">
                          <div className="flex items-start gap-3 mb-3">
                            <span className="text-2xl mt-0.5">⏳</span>
                            <div>
                              <h3 className="text-yellow-300 font-bold text-sm uppercase tracking-wide">Awaiting Approval</h3>
                              <p className="text-yellow-200/70 text-xs mt-0.5">A manager must approve before this can proceed.</p>
                            </div>
                          </div>
                          <div className="bg-yellow-950/50 rounded-lg px-3 py-2 mb-3 font-mono text-xs text-yellow-300 border border-yellow-800/50">
                            <span className="text-yellow-500 uppercase tracking-wider text-[10px]">Blocked tool</span>
                            <div className="mt-0.5">{blockedTool}</div>
                            {msg.pending_action_id && (
                              <div className="mt-1 text-yellow-600 text-[10px]">Action #{msg.pending_action_id}</div>
                            )}
                          </div>
                          <Link
                            href="/approvals"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-yellow-600 hover:bg-yellow-500 text-yellow-950 font-semibold rounded-lg shadow transition-colors text-sm"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Review in Approvals
                          </Link>
                        </div>
                      );
                    })() : (
                      msg.content || null
                    )}
                  </div>
                  {msg.role === "assistant" && (
                    <div className="mt-2 flex flex-col gap-2 pl-1">
                      {msg.steps && msg.steps.some(s => typeof s.result === "string" && s.result.includes("/api/documents/download/")) && (() => {
                        const docStep = msg.steps!.find(s => typeof s.result === "string" && s.result.includes("/api/documents/download/"))!;
                        const match = (docStep.result as string).match(/(\/api\/documents\/download\/([^\s'"]+))/);
                        const downloadPath = match ? match[1] : null;
                        const filename = match ? match[2] : "document.docx";
                        const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
                        const href = downloadPath && token
                          ? `${API_BASE}${downloadPath}?token=${encodeURIComponent(token)}`
                          : null;
                        return href ? (
                          <a
                            href={href}
                            download={filename}
                            className="inline-flex self-start items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600/30 transition-colors text-sm font-medium"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            Download Document
                          </a>
                        ) : null;
                      })()}

                      {msg.steps && msg.steps.length > 0 && (
                        <details className="text-xs text-gray-400 mt-1">
                          <summary className="cursor-pointer font-medium hover:text-gray-300">Show steps ({msg.steps.length})</summary>
                          <ol className="mt-2 space-y-2 pl-1 list-none">
                            {msg.steps.map((step, sIdx) => {
                              const raw = typeof step.result === "string" ? step.result : JSON.stringify(step.result);
                              const truncated = raw.length > 300 ? raw.slice(0, 300) + "…" : raw;
                              return (
                                <li key={sIdx} className="border border-gray-700/50 rounded-lg p-2.5 bg-gray-900/60">
                                  <div className="flex items-center gap-1.5 mb-1">
                                    <span className="text-[10px] text-gray-500 font-mono">{sIdx + 1}.</span>
                                    <strong className="text-gray-300 font-mono text-[11px]">{step.tool}</strong>
                                  </div>
                                  <div className="opacity-70 break-words whitespace-pre-wrap text-[11px] leading-relaxed">
                                    {truncated}
                                  </div>
                                </li>
                              );
                            })}
                          </ol>
                        </details>
                      )}
                      
                      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400 mt-1">
                      {msg.steps && msg.steps.length > 0 && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase border bg-purple-500/10 text-purple-400 border-purple-500/20">
                          🤖 Agent
                        </span>
                      )}
                      {msg.model_used && (
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase border ${
                            msg.model_used === "coding"
                              ? "bg-purple-500/10 text-purple-400 border-purple-500/20"
                              : msg.model_used === "vision"
                                ? "bg-orange-500/10 text-orange-400 border-orange-500/20"
                                : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                          }`}
                        >
                          ⚡ {msg.model_used === "coding" ? "Coding" : msg.model_used === "vision" ? "Vision" : "General"}
                        </span>
                      )}
                      {msg.sources && msg.sources.length > 0 && (
                        <>
                          <span className="font-semibold text-gray-500 text-[11px] uppercase tracking-wider">Sources:</span>
                          {msg.sources.map((src, sIdx) => (
                            <span
                              key={sIdx}
                              className="inline-flex items-center px-2 py-0.5 rounded-md bg-gray-900 border border-gray-800 text-gray-300 text-[11px]"
                            >
                              📄 {src.filename} {src.page ? `(Page ${src.page})` : ""}
                            </span>
                          ))}
                        </>
                      )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="flex w-full justify-start">
            <div className="bg-gray-800 border border-gray-700/50 text-gray-300 px-5 py-3.5 rounded-2xl rounded-tl-sm flex items-center space-x-2">
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
              <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
            </div>
          </div>
        )}
        {uploading && (
          <div className="flex w-full justify-center">
            <div className="bg-gray-900 border border-blue-500/30 text-blue-400 px-4 py-2 rounded-xl text-xs flex items-center space-x-2 animate-pulse shadow-sm">
              <svg className="w-4 h-4 animate-spin text-blue-400" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>Processing document & generating embeddings...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      <footer className="flex-none p-4 bg-gray-900 border-t border-gray-800">
        <div className="max-w-4xl mx-auto flex items-center justify-end mb-2">
          <div className="flex bg-gray-950 p-1 rounded-lg border border-gray-800 text-xs font-medium">
            <button
              type="button"
              onClick={() => setChatMode("chat")}
              className={`px-3 py-1 rounded-md transition-colors ${chatMode === "chat" ? "bg-gray-800 text-white shadow-sm" : "text-gray-500 hover:text-gray-300"}`}
            >
              Chat
            </button>
            {(userRole === "admin" || userRole === "manager" || userRole === "engineer") && (
              <button
                type="button"
                onClick={() => setChatMode("agent")}
                className={`px-3 py-1 rounded-md transition-colors ${chatMode === "agent" ? "bg-purple-600/20 text-purple-400 border border-purple-500/30 shadow-sm" : "text-gray-500 hover:text-gray-300"}`}
              >
                Agent
              </button>
            )}
          </div>
        </div>
        <form onSubmit={handleSend} className="max-w-4xl mx-auto relative flex items-center gap-2">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            accept=".pdf,.docx,.xlsx,.xls,.jpg,.jpeg,.png"
            className="hidden"
          />

          {/* Diagram mode toggle — only visible when an image file is selected */}
          {selectedFileName && /\.(jpe?g|png|pdf)$/i.test(selectedFileName) && !uploading && (
            <button
              id="diagram-mode-toggle"
              type="button"
              onClick={() => setIsDiagram((v) => !v)}
              title="Toggle diagram/drawing mode for vision-assisted analysis"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all flex-none ${
                isDiagram
                  ? "bg-indigo-600/20 border-indigo-500/50 text-indigo-300 shadow-sm shadow-indigo-500/10"
                  : "bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-600"
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
              </svg>
              {isDiagram ? "📐 Diagram" : "Diagram?"}
            </button>
          )}

          {/* Upload and Cancel buttons when a file is selected */}
          {selectedFile && !uploading && (
            <div className="flex items-center gap-1.5 flex-none">
              <button
                type="button"
                onClick={handleConfirmUpload}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-full transition-colors flex items-center gap-1"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
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
                className="p-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-red-400 rounded-full transition-colors"
                title="Cancel upload"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )}

          {/* Attachment button - only show when no file is selected */}
          {!selectedFile && (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || loading}
              title="Upload PDF, DOCX, XLSX, XLS, or Image document"
              className="p-3 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-full border border-gray-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/50 disabled:opacity-50 flex-none"
            >
              <svg className="w-5 h-5 text-gray-400 hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
            </button>
          )}

          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading || uploading}
            placeholder={uploading ? "Uploading document..." : "Ask a question or request code..."}
            className="flex-1 bg-gray-950 border border-gray-700 rounded-full pl-6 pr-14 py-3.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading || uploading}
            className="absolute right-2 p-2 bg-blue-600 text-white rounded-full hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900"
          >
            <svg className="w-5 h-5 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </form>
        <div className="text-center mt-2">
          <span className="text-[10px] text-gray-500 uppercase tracking-widest font-semibold">Sovereign AI generates responses. Check for accuracy.</span>
        </div>
      </footer>
    </div>
  );
}
