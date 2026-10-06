import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Folder,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  SquareTerminal,
  ExternalLink,
  X,
  GitBranch,
  FileCode,
  Layers,
  Activity,
  Cpu,
  Play,
  BookOpen,
  Save,
  Edit3,
  User,
  Paperclip,
  Mic,
  Zap,
  Globe,
  Sliders,
  ArrowUp
} from "lucide-react";
import { getIconForFile, getSVGStringFromFileType } from "@wesbos/code-icons";
import hljs from "highlight.js";
import "highlight.js/styles/github-dark.css";

// Map file extensions to highlight.js language names
const EXTENSION_TO_LANGUAGE: Record<string, string> = {
  js: "javascript",
  ts: "typescript",
  jsx: "javascript",
  tsx: "typescript",
  json: "json",
  html: "html",
  htm: "html",
  css: "css",
  scss: "css",
  less: "css",
  py: "python",
  php: "php",
  java: "java",
  go: "go",
  rs: "rust",
  c: "c",
  cpp: "cpp",
  h: "c",
  hpp: "cpp",
  swift: "swift",
  kt: "kotlin",
  dart: "dart",
  lua: "lua",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  ps1: "powershell",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  ini: "ini",
  conf: "ini",
  config: "ini",
  xml: "xml",
  sql: "sql",
  md: "markdown",
  markdown: "markdown",
  txt: "plaintext",
  log: "plaintext",
  vue: "javascript",
  svelte: "javascript",
  dockerfile: "dockerfile",
  rb: "ruby",
  ex: "elixir",
  exs: "elixir",
  erl: "erlang",
  scala: "scala",
  r: "r",
  m: "objectivec",
  mm: "objectivec",
  pl: "perl",
  pm: "perl",
  groovy: "groovy",
  gradle: "groovy",
  tf: "hcl",
  hcl: "hcl",
};

interface FileEntry {
  name: string;
  isDirectory: boolean;
}

interface WorkspaceProps {
  visible?: boolean;
}

function FileIcon({ filename }: { filename: string }): React.JSX.Element {
  const iconType = getIconForFile(filename);
  const iconData = iconType ? getSVGStringFromFileType(iconType) : null;
  const svgString =
    iconData && typeof iconData === "object" && "svg" in iconData
      ? iconData.svg
      : "";

  return (
    <div
      className="worktree-file-icon-wrapper"
      style={{
        width: 14,
        height: 14,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0
      }}
      dangerouslySetInnerHTML={{ __html: svgString }}
    />
  );
}

interface TreeItemProps {
  entry: FileEntry;
  parentPath: string;
  depth: number;
  onFileClick?: (filePath: string) => void;
}

function TreeItem({
  entry,
  parentPath,
  depth,
  onFileClick,
}: TreeItemProps): React.JSX.Element {
  const [isExpanded, setIsExpanded] = useState(false);
  const [children, setChildren] = useState<FileEntry[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fullPath = `${parentPath}/${entry.name}`;

  const loadChildren = useCallback(async () => {
    if (!entry.isDirectory || children !== null) return;
    setIsLoading(true);
    const result = await window.hermesAPI.readDirectory(fullPath);
    if (result) {
      const sorted = result.sort((a, b) => {
        if (a.isDirectory === b.isDirectory) {
          return a.name.localeCompare(b.name);
        }
        return a.isDirectory ? -1 : 1;
      });
      setChildren(sorted);
    }
    setIsLoading(false);
  }, [entry.isDirectory, fullPath, children]);

  const handleClick = (): void => {
    if (entry.isDirectory) {
      if (!isExpanded) {
        void loadChildren();
      }
      setIsExpanded(!isExpanded);
    } else {
      onFileClick?.(fullPath);
    }
  };

  const paddingLeft = 8 + depth * 12;

  return (
    <div className="worktree-item">
      <div
        className={`worktree-row ${!entry.isDirectory ? "worktree-row-file" : ""}`}
        onClick={handleClick}
        style={{ paddingLeft }}
        title={fullPath}
      >
        {entry.isDirectory ? (
          <>
            <span className="worktree-chevron">
              {isExpanded ? (
                <ChevronDown size={12} />
              ) : (
                <ChevronRight size={12} />
              )}
            </span>
            <Folder size={13} className="worktree-icon worktree-folder-icon" />
          </>
        ) : (
          <>
            <span className="worktree-chevron-placeholder" />
            <FileIcon filename={entry.name} />
          </>
        )}
        <span className="worktree-name">{entry.name}</span>
      </div>
      {entry.isDirectory && isExpanded && (
        <div className="worktree-children">
          {isLoading ? (
            <div
              className="worktree-loading"
              style={{ paddingLeft: paddingLeft + 12 }}
            >
              Loading...
            </div>
          ) : children === null ? null : children.length === 0 ? (
            <div
              className="worktree-empty"
              style={{ paddingLeft: paddingLeft + 12 }}
            >
              Empty Folder
            </div>
          ) : (
            children.map((child) => (
              <TreeItem
                key={`${fullPath}/${child.name}`}
                entry={child}
                parentPath={fullPath}
                depth={depth + 1}
                onFileClick={onFileClick}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function Workspace({ visible }: WorkspaceProps): React.JSX.Element {
  const [folderPath, setFolderPath] = useState<string | null>(() => {
    return localStorage.getItem("hermes.workspace.folderPath");
  });

  const [rootEntries, setRootEntries] = useState<FileEntry[] | null>(null);
  const [isLoadingRoot, setIsLoadingRoot] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<string | null>(null);

  // Editor vs Dashboard mode toggles
  const [isEditorMode, setIsEditorMode] = useState(false);
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);

  // Editor content states
  const [editorContent, setEditorContent] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [fileTruncated, setFileTruncated] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);
  const codeRef = useRef<HTMLElement>(null);

  // Terminal state variables
  const [activeTerminalTab, setActiveTerminalTab] = useState<"problems" | "output" | "terminal" | "copilot">("terminal");
  const [terminalInput, setTerminalInput] = useState("");
  const [terminalHistory, setTerminalHistory] = useState<string[]>([]);
  const [terminalIsRunning, setTerminalIsRunning] = useState(false);
  const terminalBottomRef = useRef<HTMLDivElement>(null);
  const [terminalHeight, setTerminalHeight] = useState(220);

  // Copilot Chat states
  interface CopilotMessage {
    role: "user" | "assistant";
    content: string;
    runId?: string;
  }
  const [copilotMessages, setCopilotMessages] = useState<CopilotMessage[]>([
    { role: "assistant", content: "Hello! I am Moltress AI. Ask me questions about this workspace, write or explain code, or run instructions here." }
  ]);
  const [copilotInput, setCopilotInput] = useState("");
  const [isCopilotLoading, setIsCopilotLoading] = useState(false);
  const copilotEndRef = useRef<HTMLDivElement>(null);

  // File scanner state
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<{
    filesCount: number;
    imagesCount: number;
    dirsCount: number;
    extStats: Record<string, number>;
  } | null>(null);

  // Session model stats state
  const [modelStats, setModelStats] = useState<{
    totalSessions: number;
    totalMessages: number;
    modelCounts: Record<string, number>;
  } | null>(null);
  const [isLoadingModelStats, setIsLoadingModelStats] = useState(false);

  // Project configuration state
  const [packageJson, setPackageJson] = useState<{
    name?: string;
    version?: string;
    scripts?: Record<string, string>;
    dependenciesCount?: number;
    devDependenciesCount?: number;
  } | null>(null);
  const [readmeContent, setReadmeContent] = useState<string | null>(null);
  const [isGit, setIsGit] = useState(false);

  // Load root entries
  useEffect(() => {
    if (!folderPath) {
      setRootEntries(null);
      return;
    }

    let cancelled = false;
    setIsLoadingRoot(true);

    const loadRoot = async (): Promise<void> => {
      const result = await window.hermesAPI.readDirectory(folderPath);
      if (cancelled) return;
      if (result) {
        const sorted = result.sort((a, b) => {
          if (a.isDirectory === b.isDirectory) {
            return a.name.localeCompare(b.name);
          }
          return a.isDirectory ? -1 : 1;
        });
        setRootEntries(sorted);
      } else {
        setRootEntries([]);
      }
      setIsLoadingRoot(false);
    };

    void loadRoot();
    return () => {
      cancelled = true;
    };
  }, [folderPath]);

  // File tree scan crawler
  useEffect(() => {
    if (!folderPath) {
      setScanResult(null);
      return;
    }

    let cancelled = false;
    setIsScanning(true);

    const runScan = async (): Promise<void> => {
      const IMAGE_EXTS = new Set([
        "png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico"
      ]);
      const IGNORED_DIRS = new Set([
        "node_modules", ".git", "dist", "build", "out",
        "venv", ".next", "__pycache__", ".svelte-kit", ".nuxt", "bower_components"
      ]);

      let filesCount = 0;
      let imagesCount = 0;
      let dirsCount = 0;
      const extStats: Record<string, number> = {};

      const scan = async (dir: string, depth = 0): Promise<void> => {
        if (cancelled || depth > 4) return;
        const entries = await window.hermesAPI.readDirectory(dir);
        if (!entries) return;

        for (const entry of entries) {
          if (entry.isDirectory) {
            if (IGNORED_DIRS.has(entry.name)) continue;
            dirsCount++;
            await scan(`${dir}/${entry.name}`, depth + 1);
          } else {
            filesCount++;
            const parts = entry.name.split(".");
            const ext = parts.length > 1 ? parts[parts.length - 1].toLowerCase() : "none";
            if (IMAGE_EXTS.has(ext)) {
              imagesCount++;
            }
            extStats[ext] = (extStats[ext] || 0) + 1;
          }
        }
      };

      await scan(folderPath);
      if (cancelled) return;

      setScanResult({
        filesCount,
        imagesCount,
        dirsCount,
        extStats
      });
      setIsScanning(false);
    };

    void runScan();
    return () => {
      cancelled = true;
    };
  }, [folderPath]);

  // Load project configurations
  useEffect(() => {
    if (!folderPath) {
      setPackageJson(null);
      setReadmeContent(null);
      setIsGit(false);
      return;
    }

    let cancelled = false;

    const loadProjectMeta = async (): Promise<void> => {
      const entries = await window.hermesAPI.readDirectory(folderPath);
      if (cancelled || !entries) return;

      // Git folder check
      const hasGit = entries.some(e => e.isDirectory && e.name === ".git");
      setIsGit(hasGit);

      // README file check
      const readmeEntry = entries.find(e => !e.isDirectory && e.name.toLowerCase() === "readme.md");
      if (readmeEntry) {
        const fileContent = await window.hermesAPI.readFile(`${folderPath}/${readmeEntry.name}`, 3000);
        if (!cancelled && fileContent) {
          setReadmeContent(fileContent.content);
        }
      } else {
        setReadmeContent(null);
      }

      // package.json file check
      const pkgEntry = entries.find(e => !e.isDirectory && e.name === "package.json");
      if (pkgEntry) {
        const fileContent = await window.hermesAPI.readFile(`${folderPath}/${pkgEntry.name}`, 10000);
        if (!cancelled && fileContent) {
          try {
            const parsed = JSON.parse(fileContent.content);
            setPackageJson({
              name: parsed.name,
              version: parsed.version,
              scripts: parsed.scripts,
              dependenciesCount: parsed.dependencies ? Object.keys(parsed.dependencies).length : 0,
              devDependenciesCount: parsed.devDependencies ? Object.keys(parsed.devDependencies).length : 0,
            });
          } catch (e) {
            console.error("Failed to parse package.json", e);
          }
        }
      } else {
        setPackageJson(null);
      }
    };

    void loadProjectMeta();
    return () => {
      cancelled = true;
    };
  }, [folderPath]);

  // Load Model usage statistics
  useEffect(() => {
    let cancelled = false;
    setIsLoadingModelStats(true);

    const loadModelStats = async (): Promise<void> => {
      try {
        const sessions = await window.hermesAPI.listSessions(100, 0);
        if (cancelled) return;

        let totalMessages = 0;
        const modelCounts: Record<string, number> = {};

        sessions.forEach((s) => {
          totalMessages += s.messageCount;
          const modelName = s.model || "Unknown Model";
          modelCounts[modelName] = (modelCounts[modelName] || 0) + 1;
        });

        setModelStats({
          totalSessions: sessions.length,
          totalMessages,
          modelCounts
        });
      } catch (e) {
        console.error("Failed to load model stats", e);
      } finally {
        if (!cancelled) setIsLoadingModelStats(false);
      }
    };

    void loadModelStats();
    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch active tab file contents
  useEffect(() => {
    if (!activeTabPath) {
      setEditorContent("");
      setIsEditing(false);
      return;
    }

    let cancelled = false;
    setEditorError(null);

    window.hermesAPI.readFile(activeTabPath, 204800)
      .then((res) => {
        if (cancelled) return;
        if (res === null) {
          setEditorError("Failed to load file contents.");
        } else {
          setEditorContent(res.content);
          setFileTruncated(res.truncated);
          setIsEditing(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTabPath]);

  // Apply code highlighting when not in edit mode
  useEffect(() => {
    if (editorContent && codeRef.current && !isEditing && activeTabPath) {
      const fileName = activeTabPath.split(/[\\/]/).pop() || "";
      const parts = fileName.split(".");
      const ext = parts.length > 1 ? parts[parts.length - 1].toLowerCase() : "";
      const detectedLang = EXTENSION_TO_LANGUAGE[ext];
      if (detectedLang) {
        codeRef.current.className = `hljs language-${detectedLang}`;
        hljs.highlightElement(codeRef.current);
      } else {
        codeRef.current.className = "hljs language-plaintext";
        hljs.highlightElement(codeRef.current);
      }
    }
  }, [editorContent, isEditing, activeTabPath]);

  // Scroll terminal history to bottom
  useEffect(() => {
    if (terminalBottomRef.current) {
      terminalBottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [terminalHistory]);

  // Scroll copilot history to bottom
  useEffect(() => {
    if (copilotEndRef.current) {
      copilotEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [copilotMessages]);

  // Knowledge Base Ingest logic bridging to the FastAPI endpoint /api/rag/ingest
  const handleIngestKnowledgeBase = async () => {
    if (!folderPath || isIngesting) return;
    setIsIngesting(true);
    setIngestStatus("Ingesting knowledge...");
    try {
      // Connect to Moltress backend port (default 8765)
      const workspaceName = folderPath.split(/[/\\]/).pop() || "default";
      const res = await fetch("http://127.0.0.1:8765/api/rag/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: folderPath, workspace: workspaceName })
      });
      if (res.ok) {
        setIngestStatus("Knowledge Base Ready!");
        setTimeout(() => setIngestStatus(null), 3500);
      } else {
        const err = await res.json().catch(() => ({}));
        setIngestStatus(err?.error?.message || "Ingestion failed.");
      }
    } catch (e) {
      setIngestStatus("Connection error.");
    } finally {
      setIsIngesting(false);
    }
  };

  const handlePickFolder = async (): Promise<void> => {
    const path = await window.hermesAPI.selectFolder();
    if (path) {
      setFolderPath(path);
      localStorage.setItem("hermes.workspace.folderPath", path);
      setOpenTabs([]);
      setActiveTabPath(null);
      setIsEditorMode(false);
      setIngestStatus(null);
    }
  };

  const handleClearFolder = (): void => {
    setFolderPath(null);
    localStorage.removeItem("hermes.workspace.folderPath");
    setOpenTabs([]);
    setActiveTabPath(null);
    setIsEditorMode(false);
    setIngestStatus(null);
  };

  // Open a file in the editor (handles tabs)
  const handleOpenFile = (path: string) => {
    if (!openTabs.includes(path)) {
      setOpenTabs((prev) => [...prev, path]);
    }
    setActiveTabPath(path);
    setIsEditorMode(true);
  };

  // Close tab handler
  const handleCloseTab = (e: React.MouseEvent, path: string) => {
    e.stopPropagation();
    const remaining = openTabs.filter((t) => t !== path);
    setOpenTabs(remaining);
    
    if (activeTabPath === path) {
      if (remaining.length > 0) {
        setActiveTabPath(remaining[remaining.length - 1]);
      } else {
        setActiveTabPath(null);
        setIsEditorMode(false);
      }
    }
  };

  // Save changes to disk
  const handleSaveFile = async () => {
    if (!activeTabPath) return;
    setIsSaving(true);
    setEditorError(null);
    try {
      const ok = await window.hermesAPI.writeFile(activeTabPath, editorContent);
      if (ok) {
        setIsEditing(false);
      } else {
        setEditorError("Could not save changes to disk. Permission error.");
      }
    } catch (e) {
      setEditorError(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setIsSaving(false);
    }
  };

  // Terminal command executor
  const handleSendTerminalCommand = async (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = terminalInput.trim();
    if (!cmd || !folderPath) return;

    setTerminalHistory((prev) => [...prev, `PS ${folderPath}> ${cmd}`]);
    setTerminalInput("");
    setTerminalIsRunning(true);

    try {
      const res = await window.hermesAPI.runCommand(cmd, folderPath);
      const output: string[] = [];
      if (res.stdout) output.push(res.stdout);
      if (res.stderr) output.push(res.stderr);
      if (output.length === 0 && res.code !== 0) {
        output.push(`Command exited with status code ${res.code}`);
      }
      setTerminalHistory((prev) => [...prev, ...output.join("").split("\n")]);
    } catch (err) {
      setTerminalHistory((prev) => [...prev, `Error: ${err instanceof Error ? err.message : String(err)}`]);
    } finally {
      setTerminalIsRunning(false);
    }
  };

  // Send message to Copilot AI Agent
  const handleSendCopilotMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = copilotInput.trim();
    if (!text || isCopilotLoading) return;

    setCopilotInput("");
    setIsCopilotLoading(true);

    const userMsg: CopilotMessage = { role: "user", content: text };
    const runId = "copilot-" + Date.now();
    const assistantMsg: CopilotMessage = { role: "assistant", content: "", runId };

    setCopilotMessages((prev) => [...prev, userMsg, assistantMsg]);

    // Format chat history for the API
    const history = copilotMessages
      .filter((m) => m.role === "user" || (m.role === "assistant" && m.content))
      .map((m) => ({ role: m.role, content: m.content }));

    let cleanupChunk = () => {};
    let cleanupDone = () => {};
    let cleanupError = () => {};

    const cleanup = () => {
      cleanupChunk();
      cleanupDone();
      cleanupError();
    };

    cleanupChunk = window.hermesAPI.onChatChunk((incomingRunId, chunk) => {
      if (incomingRunId === runId) {
        setCopilotMessages((prev) =>
          prev.map((msg) =>
            msg.runId === runId ? { ...msg, content: msg.content + chunk } : msg
          )
        );
      }
    });

    cleanupDone = window.hermesAPI.onChatDone((incomingRunId) => {
      if (incomingRunId === runId) {
        setIsCopilotLoading(false);
        cleanup();
      }
    });

    cleanupError = window.hermesAPI.onChatError((incomingRunId, err) => {
      if (incomingRunId === runId) {
        setCopilotMessages((prev) =>
          prev.map((msg) =>
            msg.runId === runId
              ? { ...msg, content: msg.content + `\n[Error: ${err}]` }
              : msg
          )
        );
        setIsCopilotLoading(false);
        cleanup();
      }
    });

    try {
      // Find active profile
      const profiles = await window.hermesAPI.listProfiles();
      const active = profiles.find((p) => p.isActive)?.name || "default";

      await window.hermesAPI.sendMessage(
        text,
        active,
        undefined, // resumeSessionId
        history,
        undefined, // attachments
        folderPath || undefined, // contextFolder
        runId
      );
    } catch (err) {
      setCopilotMessages((prev) =>
        prev.map((msg) =>
          msg.runId === runId
            ? { ...msg, content: msg.content + `\n[Failed to send message: ${err instanceof Error ? err.message : String(err)}]` }
            : msg
        )
      );
      setIsCopilotLoading(false);
      cleanup();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const target = e.currentTarget.form;
      if (target) {
        target.requestSubmit();
      }
    }
  };

  // North-South mouse drag resize handler for the bottom terminal pane
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = terminalHeight;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY;
      const newHeight = Math.max(100, Math.min(600, startHeight - deltaY));
      setTerminalHeight(newHeight);
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  };

  // Get project folder name
  const folderName = useMemo(() => {
    if (!folderPath) return "";
    return folderPath.split(/[\\/]/).filter(Boolean).pop() || folderPath;
  }, [folderPath]);

  // Compute active tab directory structure path breadcrumbs
  const fileBreadcrumbs = useMemo(() => {
    if (!activeTabPath || !folderPath) return "";
    const rel = activeTabPath.replace(folderPath, "");
    return rel.split(/[\\/]/).filter(Boolean).join(" > ");
  }, [activeTabPath, folderPath]);

  const style = useMemo<React.CSSProperties>(
    () => ({
      display: visible ? "flex" : "none",
      flex: 1,
      flexDirection: "row",
      overflow: "hidden",
      height: "100%",
      width: "100%",
      background: "#131314"
    }),
    [visible],
  );

  return (
    <div style={style} className="workspace-screen">
      {/* Scope visual styles */}
      <style>{`
        .workspace-sidebar {
          width: 260px;
          min-width: 260px;
          border-right: 1px solid #444746;
          background: #1e1f20;
          display: flex;
          flex-direction: column;
          height: 100%;
          box-sizing: border-box;
        }
        .workspace-sidebar-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          height: 56px;
          border-bottom: 1px solid #444746;
          box-sizing: border-box;
        }
        .workspace-sidebar-title {
          font-size: 14px;
          font-weight: 500;
          color: #e3e3e3;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 140px;
        }
        .workspace-sidebar-actions {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .workspace-tree-container {
          flex: 1;
          overflow-y: auto;
          padding: 10px 0;
        }
        .workspace-tree-container::-webkit-scrollbar {
          width: 6px;
        }
        .workspace-tree-container::-webkit-scrollbar-track {
          background: transparent;
        }
        .workspace-tree-container::-webkit-scrollbar-thumb {
          background: #3c4043;
          border-radius: 3px;
        }
        .workspace-tree-container::-webkit-scrollbar-thumb:hover {
          background: #4f5357;
        }
        .workspace-main {
          flex: 1;
          display: flex;
          flex-direction: column;
          height: 100%;
          min-width: 0;
          background: #131314;
        }
        .workspace-main-scroll {
          flex: 1;
          overflow-y: auto;
          padding: 24px 32px;
        }
        .workspace-main-scroll::-webkit-scrollbar {
          width: 8px;
        }
        .workspace-main-scroll::-webkit-scrollbar-track {
          background: transparent;
        }
        .workspace-main-scroll::-webkit-scrollbar-thumb {
          background: #3c4043;
          border-radius: 4px;
        }
        .workspace-main-scroll::-webkit-scrollbar-thumb:hover {
          background: #4f5357;
        }
        .dashboard-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
          gap: 20px;
          margin-top: 24px;
        }
        .glass-card {
          background: #1e1f20;
          border: 1px solid #444746;
          border-radius: 12px;
          padding: 20px;
          box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
          transition: box-shadow 0.2s, border-color 0.2s;
        }
        .glass-card:hover {
          border-color: #a8c7fa;
          box-shadow: 0 0 15px rgba(168, 199, 250, 0.08);
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 16px;
          border-bottom: 1px solid #3c4043;
          padding-bottom: 10px;
        }
        .card-title {
          font-size: 14px;
          font-weight: 500;
          color: #e3e3e3;
        }
        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 16px;
        }
        .metric-item {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .metric-label {
          font-size: 11px;
          color: #8e918f;
        }
        .metric-value {
          font-size: 20px;
          font-weight: 600;
          color: #a8c7fa;
        }
        .script-pill {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 5px 12px;
          background: #131314;
          border: 1px solid #444746;
          border-radius: 100px;
          color: #c4c7c5;
          font-size: 12px;
          cursor: pointer;
          transition: border-color 0.2s, background 0.2s, color 0.2s;
          margin-right: 8px;
          margin-bottom: 8px;
        }
        .script-pill:hover {
          border-color: #a8c7fa;
          background: rgba(168, 199, 250, 0.08);
          color: #a8c7fa;
        }
        .workspace-lang-bar-container {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .workspace-lang-bar-item {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .workspace-lang-name {
          font-size: 12px;
          color: #e3e3e3;
          width: 70px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .workspace-lang-progress-bg {
          flex: 1;
          height: 6px;
          background: #444746;
          border-radius: 3px;
          overflow: hidden;
        }
        .workspace-lang-progress-fill {
          height: 100%;
          border-radius: 3px;
          transition: width 0.3s;
        }
        .workspace-lang-count {
          font-size: 11px;
          color: #8e918f;
          width: 30px;
          text-align: right;
        }
        .tag-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 3px 8px;
          border-radius: 4px;
          font-size: 11px;
          font-weight: 500;
          margin-right: 6px;
        }

        /* VS Code Theme custom styles */
        .vscode-tabs-bar {
          display: flex;
          background: #252526;
          overflow-x: auto;
          height: 35px;
          border-bottom: 1px solid #1e1e1e;
        }
        .vscode-tab {
          display: flex;
          align-items: center;
          padding: 0 16px;
          height: 100%;
          background: #2d2d2d;
          color: #858585;
          font-size: 13px;
          cursor: pointer;
          border-right: 1px solid #1e1e1e;
          user-select: none;
          gap: 8px;
        }
        .vscode-tab.active {
          background: #1e1e1e;
          color: #e3e3e3;
          border-top: 2px solid #007acc;
        }
        .vscode-tab:hover {
          background: #2b2b2b;
        }
        .vscode-tab-close {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 14px;
          height: 14px;
          border-radius: 3px;
          color: #858585;
        }
        .vscode-tab-close:hover {
          background: rgba(255, 255, 255, 0.08);
          color: #e3e3e3;
        }
        .vscode-breadcrumbs {
          background: #1c1c1c;
          padding: 6px 16px;
          font-size: 11px;
          color: #858585;
          display: flex;
          align-items: center;
          gap: 4px;
          border-bottom: 1px solid #2d2d2d;
        }
        .vscode-editor-container {
          flex: 1;
          display: flex;
          overflow: hidden;
          background: #1e1e1e;
        }
        .vscode-gutter {
          width: 44px;
          padding: 10px 0;
          text-align: right;
          color: #858585;
          font-family: Consolas, Monaco, monospace;
          font-size: 13px;
          line-height: 1.6;
          border-right: 1px solid #2d2d2d;
          background: #1e1e1e;
          user-select: none;
        }
        .vscode-textarea {
          flex: 1;
          height: 100%;
          background: #1e1e1e;
          color: #e3e3e3;
          border: none;
          outline: none;
          font-family: Consolas, Monaco, monospace;
          font-size: 13px;
          line-height: 1.6;
          padding: 10px 16px;
          resize: none;
          box-sizing: border-box;
          white-space: pre;
          overflow: auto;
        }
        .vscode-terminal-pane {
          background: #181818;
          border-top: 1px solid #444746;
          display: flex;
          flex-direction: column;
        }
        .vscode-terminal-header {
          display: flex;
          align-items: center;
          background: #1e1e1e;
          height: 32px;
          border-bottom: 1px solid #2d2d2d;
          padding: 0 16px;
        }
        .vscode-terminal-tab {
          font-size: 11px;
          font-weight: 500;
          color: #858585;
          padding: 0 12px;
          height: 100%;
          display: flex;
          align-items: center;
          cursor: pointer;
        }
        .vscode-terminal-tab.active {
          color: #e3e3e3;
          border-bottom: 2px solid #007acc;
        }
        .vscode-terminal-body {
          flex: 1;
          padding: 12px 16px;
          overflow-y: auto;
          font-family: Consolas, Monaco, monospace;
          font-size: 12px;
          color: #cccccc;
          line-height: 1.5;
        }
        .vscode-terminal-line {
          white-space: pre-wrap;
          margin-bottom: 4px;
        }
        .vscode-terminal-prompt-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 6px;
        }
        .vscode-terminal-input {
          flex: 1;
          background: transparent;
          border: none;
          outline: none;
          color: #e3e3e3;
          font-family: Consolas, Monaco, monospace;
          font-size: 12px;
        }

        /* Moltress AI Chat Section Aesthetics */
        @keyframes messageFadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .copilot-message-bubble {
          display: flex;
          gap: 12px;
          padding: 10px 14px;
          border-radius: 12px;
          max-width: 85%;
          animation: messageFadeIn 0.25s ease-out forwards;
          font-family: Inter, system-ui, -apple-system, sans-serif;
          line-height: 1.5;
          margin-bottom: 6px;
        }
        .copilot-message-assistant {
          align-self: flex-start;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-top-left-radius: 2px;
        }
        .copilot-message-user {
          align-self: flex-end;
          background: rgba(168, 199, 250, 0.06);
          border: 1px solid rgba(168, 199, 250, 0.15);
          border-top-right-radius: 2px;
        }
        .copilot-avatar-wrapper {
          width: 26px;
          height: 26px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }
        .copilot-avatar-assistant {
          background: rgba(82, 196, 26, 0.15);
          border: 1px solid rgba(82, 196, 26, 0.3);
          color: #52c41a;
        }
        .copilot-avatar-user {
          background: rgba(24, 144, 255, 0.15);
          border: 1px solid rgba(24, 144, 255, 0.3);
          color: #1890ff;
        }
        .moltress-chat-box {
          display: flex;
          flex-direction: column;
          background: #1e1f20;
          border: 1px solid #3c4043;
          border-radius: 12px;
          padding: 8px 12px;
          margin-top: 12px;
          transition: border-color 0.2s, box-shadow 0.2s;
        }
        .moltress-chat-box:focus-within {
          border-color: #a8c7fa;
          box-shadow: 0 0 10px rgba(168, 199, 250, 0.15);
        }
        .moltress-chat-textarea {
          width: 100%;
          background: transparent;
          border: none;
          outline: none;
          resize: none;
          color: #e3e3e3;
          font-family: Inter, system-ui, -apple-system, sans-serif;
          font-size: 13px;
          line-height: 1.5;
          padding: 4px 0 8px 0;
          min-height: 24px;
          max-height: 120px;
          box-sizing: border-box;
        }
        .moltress-chat-toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          padding-top: 8px;
        }
        .moltress-toolbar-left {
          display: flex;
          align-items: center;
          gap: 6px;
          flex-wrap: wrap;
        }
        .moltress-toolbar-icon-btn {
          background: transparent;
          border: none;
          color: #8e918f;
          padding: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          border-radius: 4px;
          transition: background 0.15s, color 0.15s;
        }
        .moltress-toolbar-icon-btn:hover {
          background: rgba(255, 255, 255, 0.08);
          color: #e3e3e3;
        }
        .moltress-toolbar-divider {
          width: 1px;
          height: 16px;
          background: rgba(255, 255, 255, 0.1);
          margin: 0 4px;
        }
        .moltress-toolbar-text-btn {
          background: transparent;
          border: none;
          color: #8e918f;
          padding: 3px 8px;
          display: inline-flex;
          align-items: center;
          gap: 4px;
          cursor: pointer;
          border-radius: 4px;
          font-size: 11px;
          font-family: Inter, system-ui, sans-serif;
          transition: background 0.15s, color 0.15s;
        }
        .moltress-toolbar-text-btn:hover {
          background: rgba(255, 255, 255, 0.08);
          color: #e3e3e3;
        }
        .moltress-send-square-btn {
          width: 32px;
          height: 32px;
          border-radius: 8px;
          background: #1b2e47;
          border: 1px solid rgba(168, 199, 250, 0.1);
          color: #a8c7fa;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: background 0.2s, transform 0.1s, box-shadow 0.2s;
        }
        .moltress-send-square-btn:hover:not(:disabled) {
          background: #2a4369;
          color: #ffffff;
          box-shadow: 0 0 8px rgba(168, 199, 250, 0.2);
        }
        .moltress-send-square-btn:active:not(:disabled) {
          transform: scale(0.95);
        }
      `}</style>

      {/* Left Column: File Explorer */}
      <div className="workspace-sidebar">
        <div className="workspace-sidebar-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <FolderOpen size={16} style={{ color: "#a8c7fa" }} />
            <span className="workspace-sidebar-title" title={folderPath || "No folder selected"}>
              {folderName || "No Workspace"}
            </span>
          </div>
          <div className="workspace-sidebar-actions">
            {ingestStatus && (
              <span style={{ fontSize: 10, color: "#a8c7fa", marginRight: 4, fontStyle: "italic", alignSelf: "center", whiteSpace: "nowrap" }}>
                {ingestStatus}
              </span>
            )}
            {folderPath && (
              <button
                type="button"
                className="btn-ghost"
                onClick={handleIngestKnowledgeBase}
                disabled={isIngesting}
                title="Ingest/Add Knowledge"
                style={{ padding: "4px 8px", borderRadius: 4, display: "flex", alignItems: "center", gap: 4, justifyContent: "center", background: "transparent", border: "1px solid #0e639c", color: "#a8c7fa", cursor: isIngesting ? "wait" : "pointer", fontSize: 11 }}
                onMouseEnter={(e) => { if (!isIngesting) e.currentTarget.style.background = "#0e639c"; e.currentTarget.style.color = "#fff"; }}
                onMouseLeave={(e) => { if (!isIngesting) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#a8c7fa"; } }}
              >
                <Layers size={13} />
                <span>{isIngesting ? "Indexing..." : "Ingest"}</span>
              </button>
            )}
            {folderPath && (
              <button
                type="button"
                className="btn-ghost"
                onClick={() => void window.hermesAPI.openTerminal(folderPath)}
                title="Open Terminal"
                style={{ padding: 4, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", background: "transparent", border: "none", color: "#c4c7c5", cursor: "pointer" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.06)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <SquareTerminal size={16} />
              </button>
            )}
            <button
              type="button"
              className="btn-ghost"
              onClick={handlePickFolder}
              title={folderPath ? "Change Workspace" : "Select Workspace"}
              style={{
                padding: "3px 8px",
                borderRadius: 4,
                display: "flex",
                alignItems: "center",
                gap: 4,
                background: "transparent",
                border: "1px solid #444746",
                color: "#a8c7fa",
                fontSize: 11,
                fontWeight: 500,
                cursor: "pointer"
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(168, 199, 250, 0.08)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              <span>{folderPath ? "Change" : "Open"}</span>
            </button>
          </div>
        </div>

        <div className="workspace-tree-container">
          {isLoadingRoot ? (
            <div style={{ padding: "0 16px", color: "#c4c7c5", fontSize: 12 }}>Loading explorer...</div>
          ) : !folderPath ? (
            <div style={{ padding: "0 16px", color: "#8e918f", fontSize: 12, fontStyle: "italic" }}>
              No folder selected.
            </div>
          ) : rootEntries === null || rootEntries.length === 0 ? (
            <div style={{ padding: "0 16px", color: "#8e918f", fontSize: 12 }}>Folder is empty.</div>
          ) : (
            rootEntries.map((entry) => (
              <TreeItem
                key={`${folderPath}/${entry.name}`}
                entry={entry}
                parentPath={folderPath}
                depth={0}
                onFileClick={handleOpenFile}
              />
            ))
          )}
        </div>
      </div>

      {/* Right Column: Main View (VS Code Editor or Dashboard) */}
      <div className="workspace-main">
        {isEditorMode && activeTabPath ? (
          /* =================== VS CODE CLONE INTERFACE =================== */
          <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
            {/* Tabs Bar */}
            <div className="vscode-tabs-bar">
              {openTabs.map((tabPath) => {
                const tabName = tabPath.split(/[\\/]/).pop() || "";
                const active = tabPath === activeTabPath;
                return (
                  <div
                    key={tabPath}
                    className={`vscode-tab ${active ? "active" : ""}`}
                    onClick={() => setActiveTabPath(tabPath)}
                  >
                    <FileCode size={13} style={{ color: "#a8c7fa" }} />
                    <span>{tabName}</span>
                    <button
                      type="button"
                      className="vscode-tab-close"
                      onClick={(e) => handleCloseTab(e, tabPath)}
                    >
                      <X size={10} />
                    </button>
                  </div>
                );
              })}
              {/* Back to Dashboard Button */}
              <button
                type="button"
                onClick={() => setIsEditorMode(false)}
                style={{
                  marginLeft: "auto",
                  background: "transparent",
                  border: "none",
                  borderLeft: "1px solid #1e1e1e",
                  color: "#a8c7fa",
                  fontSize: 12,
                  padding: "0 16px",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 6
                }}
              >
                <span>Back to Dashboard</span>
              </button>
            </div>

            {/* Breadcrumbs */}
            <div className="vscode-breadcrumbs">
              <span>{folderName}</span>
              <span>&gt;</span>
              <span>{fileBreadcrumbs}</span>
            </div>

            {/* Editor Action Header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 16px",
                background: "#1e1e1e",
                borderBottom: "1px solid #2d2d2d"
              }}
            >
              <div style={{ fontSize: 11, color: "#8e918f" }}>
                {fileTruncated && "Large file loaded (truncated preview)."}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {isEditing ? (
                  <>
                    <button
                      type="button"
                      onClick={handleSaveFile}
                      disabled={isSaving}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        background: "#0e639c",
                        color: "#ffffff",
                        border: "none",
                        padding: "4px 12px",
                        fontSize: 11,
                        borderRadius: 3,
                        cursor: "pointer",
                        fontWeight: 500
                      }}
                    >
                      <Save size={12} />
                      <span>{isSaving ? "Saving..." : "Save Changes"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsEditing(false)}
                      style={{
                        background: "transparent",
                        color: "#c4c7c5",
                        border: "1px solid #444746",
                        padding: "3px 12px",
                        fontSize: 11,
                        borderRadius: 3,
                        cursor: "pointer"
                      }}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => setIsEditing(true)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        background: "transparent",
                        color: "#a8c7fa",
                        border: "1px solid #444746",
                        padding: "4px 12px",
                        fontSize: 11,
                        borderRadius: 3,
                        cursor: "pointer"
                      }}
                    >
                      <Edit3 size={12} />
                      <span>Edit File</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => window.hermesAPI.openFileInEditor(activeTabPath)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        background: "transparent",
                        color: "#c4c7c5",
                        border: "1px solid #444746",
                        padding: "4px 12px",
                        fontSize: 11,
                        borderRadius: 3,
                        cursor: "pointer"
                      }}
                    >
                      <ExternalLink size={12} />
                      <span>Open in VS Code</span>
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Error banner */}
            {editorError && (
              <div style={{ background: "rgba(234, 67, 53, 0.1)", borderBottom: "1px solid rgba(234, 67, 53, 0.2)", color: "#ea4335", padding: "6px 16px", fontSize: 12 }}>
                {editorError}
              </div>
            )}

            {/* Code Gutter and Text Area */}
            <div className="vscode-editor-container">
              {/* Line Numbers Gutter */}
              <div className="vscode-gutter">
                {Array.from({ length: editorContent.split("\n").length || 1 }).map((_, i) => (
                  <div key={i} style={{ paddingRight: 8 }}>{i + 1}</div>
                ))}
              </div>

              {/* Editable/Preview Code viewport */}
              {isEditing ? (
                <textarea
                  className="vscode-textarea"
                  value={editorContent}
                  onChange={(e) => setEditorContent(e.target.value)}
                  spellCheck={false}
                />
              ) : (
                <div style={{ flex: 1, overflow: "auto", background: "#1e1e1e" }}>
                  <pre
                    style={{
                      margin: 0,
                      fontFamily: "Consolas, Monaco, monospace",
                      fontSize: 13,
                      lineHeight: "1.6",
                      padding: "10px 16px"
                    }}
                  >
                    <code ref={codeRef}>
                      {editorContent}
                    </code>
                  </pre>
                </div>
              )}
            </div>

            {/* Bottom Terminal Pane */}
            <div
              className="vscode-terminal-pane"
              style={{
                height: terminalHeight,
                position: "relative"
              }}
            >
              {/* Top resize border handle */}
              <div
                onMouseDown={handleMouseDown}
                style={{
                  position: "absolute",
                  top: -3,
                  left: 0,
                  right: 0,
                  height: 6,
                  cursor: "ns-resize",
                  zIndex: 100,
                  background: "transparent",
                  transition: "background 0.2s"
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#007acc")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              />
              <div className="vscode-terminal-header">
                <div
                  className={`vscode-terminal-tab ${activeTerminalTab === "terminal" ? "active" : ""}`}
                  onClick={() => setActiveTerminalTab("terminal")}
                >
                  Terminal
                </div>
                <div
                  className={`vscode-terminal-tab ${activeTerminalTab === "problems" ? "active" : ""}`}
                  onClick={() => setActiveTerminalTab("problems")}
                >
                  Problems (0)
                </div>
                <div
                  className={`vscode-terminal-tab ${activeTerminalTab === "output" ? "active" : ""}`}
                  onClick={() => setActiveTerminalTab("output")}
                >
                  Output
                </div>
                <div
                  className={`vscode-terminal-tab ${activeTerminalTab === "copilot" ? "active" : ""}`}
                  onClick={() => setActiveTerminalTab("copilot")}
                >
                  Moltress AI
                </div>
              </div>

              <div
                className="vscode-terminal-body"
                style={activeTerminalTab === "copilot" ? { display: "flex", flexDirection: "column", padding: "10px 16px", height: "100%", boxSizing: "border-box" } : undefined}
              >
                {activeTerminalTab === "terminal" && (
                  <>
                    {terminalHistory.map((line, index) => (
                      <div key={index} className="vscode-terminal-line">
                        {line}
                      </div>
                    ))}
                    {terminalIsRunning && (
                      <div className="vscode-terminal-line" style={{ color: "#8e918f" }}>
                        Running command in shell...
                      </div>
                    )}
                    <form onSubmit={handleSendTerminalCommand} className="vscode-terminal-prompt-row">
                      <span style={{ color: "#a8c7fa" }}>PS {folderPath}&gt;</span>
                      <input
                        type="text"
                        className="vscode-terminal-input"
                        value={terminalInput}
                        onChange={(e) => setTerminalInput(e.target.value)}
                        disabled={terminalIsRunning}
                        autoFocus
                      />
                    </form>
                    <div ref={terminalBottomRef} />
                  </>
                )}
                {activeTerminalTab === "problems" && (
                  <div style={{ color: "#8e918f", fontSize: 12 }}>No problems detected in workspace files.</div>
                )}
                {activeTerminalTab === "output" && (
                  <div style={{ color: "#8e918f", fontSize: 12 }}>Workspace output log is clean.</div>
                )}
                {activeTerminalTab === "copilot" && (
                  <>
                    <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10, paddingBottom: 10 }}>
                      {copilotMessages.map((msg, index) => (
                        <div
                          key={index}
                          className={`copilot-message-bubble ${
                            msg.role === "user" ? "copilot-message-user" : "copilot-message-assistant"
                          }`}
                        >
                          <div
                            className={`copilot-avatar-wrapper ${
                              msg.role === "user" ? "copilot-avatar-user" : "copilot-avatar-assistant"
                            }`}
                          >
                            {msg.role === "user" ? <User size={13} /> : <Cpu size={13} />}
                          </div>
                          <div style={{ flex: 1 }}>
                            {msg.content}
                          </div>
                        </div>
                      ))}
                      {isCopilotLoading && (
                        <div className="copilot-message-bubble copilot-message-assistant" style={{ opacity: 0.7 }}>
                          <div className="copilot-avatar-wrapper copilot-avatar-assistant" style={{ animation: "pulse 1.5s infinite" }}>
                            <Cpu size={13} />
                          </div>
                          <div style={{ flex: 1, fontStyle: "italic", color: "#8e918f" }}>
                            Thinking...
                          </div>
                        </div>
                      )}
                      <div ref={copilotEndRef} />
                    </div>
                    <form onSubmit={handleSendCopilotMessage} className="moltress-chat-box">
                      {/* Text Input Row */}
                      <textarea
                        className="moltress-chat-textarea"
                        placeholder="Type a message... (Shift+Enter for new line)"
                        value={copilotInput}
                        onChange={(e) => setCopilotInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        disabled={isCopilotLoading}
                        rows={1}
                      />
                      
                      {/* Actions Toolbar Row */}
                      <div className="moltress-chat-toolbar">
                        {/* Left items */}
                        <div className="moltress-toolbar-left">
                          <button type="button" className="moltress-toolbar-icon-btn" title="Add Attachment">
                            <Paperclip size={14} />
                          </button>
                          <button type="button" className="moltress-toolbar-icon-btn" title="Voice Input">
                            <Mic size={14} />
                          </button>
                          
                          <div className="moltress-toolbar-divider" />
                          
                          <button type="button" className="moltress-toolbar-text-btn" title="Select Model">
                            <span>Default Model</span>
                            <ChevronDown size={10} />
                          </button>
                          
                          <button type="button" className="moltress-toolbar-text-btn" title="Reasoning Mode">
                            <Cpu size={12} />
                            <span>Standard</span>
                            <ChevronDown size={10} />
                          </button>
                          
                          <button type="button" className="moltress-toolbar-icon-btn" title="Fast Mode">
                            <Zap size={14} />
                          </button>
                          
                          <button type="button" className="moltress-toolbar-text-btn" title="Choose Workspace Folder">
                            <Folder size={12} />
                            <span>{folderName || "Choose Folder"}</span>
                          </button>
                          
                          <button type="button" className="moltress-toolbar-icon-btn" title="Web Search">
                            <Globe size={14} />
                          </button>
                          
                          <button type="button" className="moltress-toolbar-icon-btn" title="Settings">
                            <Sliders size={14} />
                          </button>
                        </div>
                        
                        {/* Right items: Send button */}
                        <button
                          type="submit"
                          disabled={isCopilotLoading || !copilotInput.trim()}
                          className="moltress-send-square-btn"
                          style={(!copilotInput.trim() || isCopilotLoading) ? { opacity: 0.4, cursor: "default" } : undefined}
                        >
                          <ArrowUp size={16} />
                        </button>
                      </div>
                    </form>
                  </>
                )}
              </div>
            </div>
          </div>
        ) : (
          /* =================== DASHBOARD INTERFACE =================== */
          <div className="workspace-main-scroll">
            {/* Header Title */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid #444746", paddingBottom: 16 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 20, fontWeight: 500, color: "#e3e3e3" }}>Workspace Overview</h2>
                <p style={{ margin: "4px 0 0 0", fontSize: 12, color: "#8e918f", fontFamily: "monospace" }}>
                  {folderPath || "No active directory path bound to this screen."}
                </p>
              </div>
              {folderPath && (
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <button
                    type="button"
                    onClick={() => {
                      // Enter editor mode directly for the first file or a default
                      if (rootEntries && rootEntries.length > 0) {
                        const firstFile = rootEntries.find(e => !e.isDirectory);
                        if (firstFile) {
                          handleOpenFile(`${folderPath}/${firstFile.name}`);
                          return;
                        }
                      }
                      setIsEditorMode(true);
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "5px 16px",
                      background: "transparent",
                      border: "1px solid #444746",
                      borderRadius: "100px",
                      color: "#a8c7fa",
                      fontSize: 12,
                      fontWeight: 500,
                      cursor: "pointer",
                      transition: "background 0.2s"
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(168, 199, 250, 0.08)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <span style={{ fontSize: 13, fontWeight: 700 }}>&lt;&gt;</span>
                    <span>Open Code Editor</span>
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={handleClearFolder}
                    style={{
                      padding: "5px 16px",
                      borderRadius: "100px",
                      background: "transparent",
                      border: "1px solid #ea4335",
                      color: "#ea4335",
                      fontSize: 12,
                      fontWeight: 500,
                      cursor: "pointer",
                      transition: "background 0.2s"
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(234, 67, 53, 0.08)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    Close Workspace
                  </button>
                </div>
              )}
            </div>

            {/* Dashboard Content */}
            {!folderPath ? (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  height: "70%",
                  textAlign: "center",
                  color: "#c4c7c5"
                }}
              >
                <FolderOpen size={48} style={{ color: "#444746", marginBottom: 16 }} />
                <h3 style={{ margin: "0 0 8px 0", fontSize: 16, fontWeight: 500, color: "#e3e3e3" }}>Get Started with Workspace</h3>
                <p style={{ margin: "0 0 20px 0", fontSize: 13, color: "#8e918f", maxWidth: 360, lineHeight: 1.5 }}>
                  Select a local folder to read project stats, run build scripts, see model usage logs, and browse code files.
                </p>
                <button
                  type="button"
                  onClick={handlePickFolder}
                  style={{
                    padding: "8px 20px",
                    background: "#a8c7fa",
                    color: "#042b4d",
                    border: "none",
                    borderRadius: "100px",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                    boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
                    transition: "transform 0.1s"
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.transform = "scale(1.02)")}
                  onMouseLeave={(e) => (e.currentTarget.style.transform = "scale(1)")}
                >
                  Select Workspace Folder
                </button>
              </div>
            ) : (
              <div>
                {/* Badges and Tags row */}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 16 }}>
                  {isGit && (
                    <div className="tag-badge" style={{ background: "rgba(168, 199, 250, 0.1)", color: "#a8c7fa", border: "1px solid rgba(168, 199, 250, 0.2)" }}>
                      <GitBranch size={11} style={{ marginRight: 4 }} />
                      <span>Git Repository</span>
                    </div>
                  )}
                  {packageJson && (
                    <div className="tag-badge" style={{ background: "rgba(52, 168, 83, 0.1)", color: "#5cdb5c", border: "1px solid rgba(52, 168, 83, 0.2)" }}>
                      <span>NPM Project</span>
                    </div>
                  )}
                  {readmeContent && (
                    <div className="tag-badge" style={{ background: "rgba(242, 153, 74, 0.1)", color: "#f2994a", border: "1px solid rgba(242, 153, 74, 0.2)" }}>
                      <span>Has README.md</span>
                    </div>
                  )}
                  {packageJson?.version && (
                    <div className="tag-badge" style={{ background: "rgba(255, 255, 255, 0.05)", color: "#c4c7c5", border: "1px solid #444746" }}>
                      <span>v{packageJson.version}</span>
                    </div>
                  )}
                </div>

                <div className="dashboard-grid">
                  {/* Card 1: Workspace Stats */}
                  <div className="glass-card">
                    <div className="card-header">
                      <Layers size={15} style={{ color: "#a8c7fa" }} />
                      <span className="card-title">File System Metrics</span>
                    </div>
                    {isScanning ? (
                      <div style={{ color: "#8e918f", fontSize: 12 }}>Scanning workspace files...</div>
                    ) : scanResult ? (
                      <div className="metrics-grid">
                        <div className="metric-item">
                          <span className="metric-label">Total Files</span>
                          <span className="metric-value">{scanResult.filesCount}</span>
                        </div>
                        <div className="metric-item">
                          <span className="metric-label">Total Images</span>
                          <span className="metric-value" style={{ color: "#f2994a" }}>{scanResult.imagesCount}</span>
                        </div>
                        <div className="metric-item">
                          <span className="metric-label">Subdirectories</span>
                          <span className="metric-value" style={{ color: "#e3e3e3", fontSize: 16 }}>{scanResult.dirsCount}</span>
                        </div>
                        <div className="metric-item">
                          <span className="metric-label">Scan Depth Limit</span>
                          <span className="metric-value" style={{ color: "#e3e3e3", fontSize: 16 }}>5 levels</span>
                        </div>
                      </div>
                    ) : (
                      <div style={{ color: "#8e918f", fontSize: 12 }}>Failed to scan files.</div>
                    )}
                  </div>

                  {/* Card 2: Model Usage Statistics */}
                  <div className="glass-card">
                    <div className="card-header">
                      <Activity size={15} style={{ color: "#a8c7fa" }} />
                      <span className="card-title">Model Usage & Conversations</span>
                    </div>
                    {isLoadingModelStats ? (
                      <div style={{ color: "#8e918f", fontSize: 12 }}>Loading model usage stats...</div>
                    ) : modelStats ? (
                      <div className="metrics-grid">
                        <div className="metric-item">
                          <span className="metric-label">Chat Sessions</span>
                          <span className="metric-value">{modelStats.totalSessions}</span>
                        </div>
                        <div className="metric-item">
                          <span className="metric-label">Messages Swapped</span>
                          <span className="metric-value" style={{ color: "#34a853" }}>{modelStats.totalMessages}</span>
                        </div>
                        <div className="metric-item" style={{ gridColumn: "span 2" }}>
                          <span className="metric-label">Active Profiles</span>
                          <span style={{ fontSize: 13, color: "#e3e3e3", marginTop: 4, display: "block" }}>
                            Default Profile
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div style={{ color: "#8e918f", fontSize: 12 }}>No session history loaded.</div>
                    )}
                  </div>

                  {/* Card 3: Codebase Language Distribution */}
                  <div className="glass-card" style={{ gridRow: "span 2" }}>
                    <div className="card-header">
                      <FileCode size={15} style={{ color: "#a8c7fa" }} />
                      <span className="card-title">Codebase Languages</span>
                    </div>
                    {isScanning ? (
                      <div style={{ color: "#8e918f", fontSize: 12 }}>Scanning file extensions...</div>
                    ) : scanResult ? (
                      <div className="workspace-lang-bar-container">
                        {Object.entries(scanResult.extStats)
                          .sort((a, b) => b[1] - a[1])
                          .slice(0, 6)
                          .map(([ext, count]) => {
                            const percentage = Math.round((count / scanResult.filesCount) * 100);
                            let color = "#a8c7fa"; // default TS blue
                            if (ext === "js" || ext === "jsx") color = "#f2c94c"; // JS yellow
                            if (ext === "json") color = "#27ae60"; // JSON green
                            if (ext === "py") color = "#56ccf2"; // Python light blue
                            if (ext === "css" || ext === "scss") color = "#eb5757"; // CSS red
                            if (ext === "md" || ext === "markdown") color = "#9b51e0"; // MD purple
                            if (ext === "png" || ext === "jpg" || ext === "jpeg" || ext === "gif") color = "#f2994a"; // Image orange

                            return (
                              <div className="workspace-lang-bar-item" key={ext}>
                                <span className="workspace-lang-name">.{ext.toUpperCase()}</span>
                                <div className="workspace-lang-progress-bg">
                                  <div
                                    className="workspace-lang-progress-fill"
                                    style={{
                                      width: `${percentage || 1}%`,
                                      backgroundColor: color
                                    }}
                                  />
                                </div>
                                <span className="workspace-lang-count">{count}</span>
                              </div>
                            );
                          })}
                      </div>
                    ) : (
                      <div style={{ color: "#8e918f", fontSize: 12 }}>No languages scanned yet.</div>
                    )}
                  </div>

                  {/* Card 4: Model Session Distribution */}
                  <div className="glass-card">
                    <div className="card-header">
                      <Cpu size={15} style={{ color: "#a8c7fa" }} />
                      <span className="card-title">Model Usage Distribution</span>
                    </div>
                    {isLoadingModelStats ? (
                      <div style={{ color: "#8e918f", fontSize: 12 }}>Loading model usage...</div>
                    ) : modelStats && Object.keys(modelStats.modelCounts).length > 0 ? (
                      <div className="workspace-lang-bar-container">
                        {Object.entries(modelStats.modelCounts)
                          .sort((a, b) => b[1] - a[1])
                          .slice(0, 3)
                          .map(([model, count]) => {
                            const percentage = Math.round((count / modelStats.totalSessions) * 100);
                            return (
                              <div className="workspace-lang-bar-item" key={model}>
                                <span className="workspace-lang-name" style={{ width: 140 }} title={model}>
                                  {model.split(/[\\/]/).pop() || model}
                                </span>
                                <div className="workspace-lang-progress-bg">
                                  <div
                                    className="workspace-lang-progress-fill"
                                    style={{
                                      width: `${percentage || 1}%`,
                                      backgroundColor: "#a8c7fa"
                                    }}
                                  />
                                </div>
                                <span className="workspace-lang-count">{count}</span>
                              </div>
                            );
                          })}
                      </div>
                    ) : (
                      <div style={{ color: "#8e918f", fontSize: 12 }}>No model usage stats loaded.</div>
                    )}
                  </div>

                  {/* Card 5: Project Scripts (npm run scripts) */}
                  {packageJson?.scripts && (
                    <div className="glass-card" style={{ gridColumn: "span 2" }}>
                      <div className="card-header">
                        <SquareTerminal size={15} style={{ color: "#a8c7fa" }} />
                        <span className="card-title">Project Scripts (npm)</span>
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap" }}>
                        {Object.keys(packageJson.scripts).map((scriptName) => (
                          <button
                            key={scriptName}
                            type="button"
                            className="script-pill"
                            onClick={() => void window.hermesAPI.openTerminal(folderPath)}
                            title={`npm run ${scriptName}`}
                          >
                            <Play size={10} />
                            <span>{scriptName}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Card 6: Project README preview */}
                  {readmeContent && (
                    <div className="glass-card" style={{ gridColumn: "span 2", maxHeight: 300, overflow: "hidden", display: "flex", flexDirection: "column" }}>
                      <div className="card-header">
                        <BookOpen size={15} style={{ color: "#a8c7fa" }} />
                        <span className="card-title">README.md Preview</span>
                      </div>
                      <div
                        style={{
                          flex: 1,
                          overflowY: "auto",
                          fontSize: 12,
                          color: "#c4c7c5",
                          lineHeight: "1.6",
                          whiteSpace: "pre-wrap",
                          fontFamily: "monospace",
                          padding: "10px",
                          background: "#131314",
                          borderRadius: 6,
                          border: "1px solid #3c4043"
                        }}
                      >
                        {readmeContent}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
