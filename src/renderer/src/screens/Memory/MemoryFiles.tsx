import { useState, useEffect, useCallback } from "react";
import { FileText, Plus, Trash2, Upload, Search, X, Check } from "lucide-react";

interface MemoryFileItem {
  id: string;
  name: string;
  size: number;
  lastModified: number;
  content?: string;
  type: string;
}

export function MemoryFiles({
  profile,
}: {
  profile?: string;
}): React.JSX.Element {
  const [files, setFiles] = useState<MemoryFileItem[]>([]);
  const [search, setSearch] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [newFileName, setNewFileName] = useState("");
  const [newFileContent, setNewFileContent] = useState("");
  const [selectedFile, setSelectedFile] = useState<MemoryFileItem | null>(null);
  const [copied, setCopied] = useState(false);

  const loadFiles = useCallback(async () => {
    try {
      // Load stored memory files or profile documents if available
      const storageKey = `hermes.memory.files.${profile || "default"}`;
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        setFiles(JSON.parse(saved));
      } else {
        // Initial sample files from memory
        setFiles([
          {
            id: "mem-1",
            name: "MEMORY.md",
            size: 1024,
            lastModified: Date.now(),
            content: "# Agent Long-Term Memory\n\nPersisted facts, system directives, and active contextual notes.",
            type: "markdown",
          },
          {
            id: "mem-2",
            name: "USER.md",
            size: 512,
            lastModified: Date.now(),
            content: "# User Profile & Preferences\n\nUser instructions and environment preferences.",
            type: "markdown",
          },
        ]);
      }
    } catch {
      // Fallback
    }
  }, [profile]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const saveFiles = (updatedFiles: MemoryFileItem[]) => {
    setFiles(updatedFiles);
    const storageKey = `hermes.memory.files.${profile || "default"}`;
    localStorage.setItem(storageKey, JSON.stringify(updatedFiles));
  };

  const handleAddFile = () => {
    if (!newFileName.trim()) return;
    const name = newFileName.trim();
    const content = newFileContent;
    const ext = name.includes(".") ? name.split(".").pop() || "txt" : "txt";
    const newFile: MemoryFileItem = {
      id: `file-${Date.now()}`,
      name,
      size: new Blob([content]).size,
      lastModified: Date.now(),
      content,
      type: ext,
    };
    saveFiles([newFile, ...files]);
    setNewFileName("");
    setNewFileContent("");
    setShowAddModal(false);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const uploaded = e.target.files;
    if (!uploaded || uploaded.length === 0) return;
    const fileList = Array.from(uploaded);

    fileList.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        const text = (event.target?.result as string) || "";
        const ext = file.name.includes(".") ? file.name.split(".").pop() || "file" : "file";
        const newFile: MemoryFileItem = {
          id: `file-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
          name: file.name,
          size: file.size,
          lastModified: file.lastModified || Date.now(),
          content: text,
          type: ext,
        };
        setFiles((prev) => {
          const next = [newFile, ...prev];
          const storageKey = `hermes.memory.files.${profile || "default"}`;
          localStorage.setItem(storageKey, JSON.stringify(next));
          return next;
        });
      };
      reader.readAsText(file);
    });
    e.target.value = "";
  };

  const handleDeleteFile = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const filtered = files.filter((f) => f.id !== id);
    saveFiles(filtered);
    if (selectedFile?.id === id) {
      setSelectedFile(null);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const filteredFiles = files.filter(
    (f) =>
      f.name.toLowerCase().includes(search.toLowerCase()) ||
      (f.content && f.content.toLowerCase().includes(search.toLowerCase())),
  );

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="memory-files-section" style={{ marginTop: 20 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
          gap: 12,
        }}
      >
        <div
          style={{
            position: "relative",
            flex: 1,
            maxWidth: 360,
            display: "flex",
            alignItems: "center",
          }}
        >
          <Search size={14} style={{ position: "absolute", left: 10, opacity: 0.5 }} />
          <input
            className="input"
            style={{ paddingLeft: 32 }}
            type="text"
            placeholder="Search memory files..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>
            <Upload size={14} />
            <span>Upload File</span>
            <input
              type="file"
              multiple
              onChange={handleFileUpload}
              style={{ display: "none" }}
            />
          </label>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setShowAddModal(true)}
          >
            <Plus size={14} />
            <span>New File</span>
          </button>
        </div>
      </div>

      {filteredFiles.length === 0 ? (
        <div className="memory-empty" style={{ padding: 40, textAlign: "center" }}>
          <FileText size={32} style={{ opacity: 0.3, marginBottom: 12 }} />
          <p className="models-empty-text">No files found in memory</p>
          <p className="models-empty-hint">
            Upload text files or create a new file to persist in memory context.
          </p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
          {filteredFiles.map((file) => (
            <div
              key={file.id}
              className="models-card"
              style={{ cursor: "pointer", display: "flex", flexDirection: "column" }}
              onClick={() => setSelectedFile(file)}
            >
              <div className="models-card-header" style={{ marginBottom: 8 }}>
                <div className="models-card-title">
                  <FileText size={18} style={{ color: "var(--accent-color, #4f46e5)" }} />
                  <div className="models-card-name" style={{ wordBreak: "break-all" }}>
                    {file.name}
                  </div>
                </div>
                <button
                  className="btn-ghost"
                  onClick={(e) => handleDeleteFile(file.id, e)}
                  title="Delete file"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 8, display: "flex", gap: 12 }}>
                <span>{formatSize(file.size)}</span>
                <span>{file.type.toUpperCase()}</span>
              </div>

              {file.content && (
                <div
                  style={{
                    fontSize: 12,
                    opacity: 0.6,
                    maxHeight: 60,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    lineHeight: "1.4",
                    background: "var(--bg-subtle, rgba(0,0,0,0.1))",
                    padding: 8,
                    borderRadius: 4,
                    fontFamily: "monospace",
                  }}
                >
                  {file.content.slice(0, 150)}...
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* File Preview Modal */}
      {selectedFile && (
        <div className="models-modal-overlay" onClick={() => setSelectedFile(null)}>
          <div className="models-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640, width: "90%" }}>
            <div className="models-modal-header">
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <FileText size={18} />
                <h2 className="models-modal-title">{selectedFile.name}</h2>
              </div>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setSelectedFile(null)}
              >
                <X size={18} />
              </button>
            </div>
            <div className="models-modal-body">
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12, fontSize: 13, opacity: 0.7 }}>
                <span>Size: {formatSize(selectedFile.size)}</span>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => copyToClipboard(selectedFile.content || "")}
                >
                  {copied ? <Check size={14} /> : null}
                  <span>{copied ? "Copied" : "Copy Content"}</span>
                </button>
              </div>
              <pre
                style={{
                  background: "var(--bg-subtle, rgba(0,0,0,0.2))",
                  padding: 14,
                  borderRadius: 6,
                  maxHeight: 360,
                  overflowY: "auto",
                  fontSize: 13,
                  fontFamily: "monospace",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {selectedFile.content || "(Empty file)"}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Add New File Modal */}
      {showAddModal && (
        <div className="models-modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="models-modal" onClick={(e) => e.stopPropagation()}>
            <div className="models-modal-header">
              <h2 className="models-modal-title">Create New Memory File</h2>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setShowAddModal(false)}
              >
                <X size={18} />
              </button>
            </div>
            <div className="models-modal-body">
              <div className="models-modal-field">
                <label className="models-modal-label">File Name</label>
                <input
                  className="input"
                  type="text"
                  placeholder="notes.txt, instructions.md, context.json"
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="models-modal-field">
                <label className="models-modal-label">File Content</label>
                <textarea
                  className="input"
                  rows={8}
                  placeholder="Type or paste memory content here..."
                  value={newFileContent}
                  onChange={(e) => setNewFileContent(e.target.value)}
                  style={{ resize: "vertical" }}
                />
              </div>
            </div>
            <div className="models-modal-footer" style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowAddModal(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary btn-sm"
                disabled={!newFileName.trim()}
                onClick={handleAddFile}
              >
                Save File
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
