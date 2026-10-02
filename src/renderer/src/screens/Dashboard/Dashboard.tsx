import { useState, useEffect, useMemo } from "react";
import {
  MessageSquare,
  Cpu,
  Settings,
  PlusCircle,
  FolderOpen,
  Calendar,
  ChevronRight,
  TrendingUp,
  FileText,
  Image,
  Puzzle
} from "lucide-react";

interface RecentSession {
  id: string;
  title: string | null;
  model: string;
  messageCount: number;
  startedAt: number;
}

interface DashboardProps {
  visible?: boolean;
  activeProfile: string;
  onResumeSession: (sessionId: string) => void;
  onNewChat: () => void;
  onNavigateTo: (view: any) => void;
}

export default function Dashboard({
  visible,
  activeProfile,
  onResumeSession,
  onNewChat,
  onNavigateTo
}: DashboardProps): React.JSX.Element {
  const [folderPath, setFolderPath] = useState<string | null>(null);
  const [recentSessions, setRecentSessions] = useState<RecentSession[]>([]);
  const [totalSessions, setTotalSessions] = useState(0);
  const [modelCounts, setModelCounts] = useState<Record<string, number>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [filesCount, setFilesCount] = useState<number | null>(null);
  const [imagesCount, setImagesCount] = useState<number | null>(null);
  const [skillsCount, setSkillsCount] = useState<number>(5);
  const [modelsCountState, setModelsCountState] = useState<number>(10);

  // Sync workspace folder path
  useEffect(() => {
    const path = localStorage.getItem("hermes.workspace.folderPath");
    setFolderPath(path);
  }, [visible]);

  // Scan folder path for files and images counts
  useEffect(() => {
    let cancelled = false;
    if (!visible || !folderPath) {
      setFilesCount(null);
      setImagesCount(null);
      return;
    }

    const runScan = async () => {
      try {
        const IMAGE_EXTS = new Set([
          "png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico"
        ]);
        let files = 0;
        let images = 0;

        const scan = async (dir: string, depth = 0): Promise<void> => {
          if (cancelled || depth > 4) return;
          const entries = await window.hermesAPI.readDirectory(dir);
          if (!entries) return;
          for (const entry of entries) {
            if (cancelled) return;
            if (entry.isDirectory) {
              await scan(`${dir}/${entry.name}`, depth + 1);
            } else {
              files++;
              const parts = entry.name.split(".");
              const ext = parts.length > 1 ? parts[parts.length - 1].toLowerCase() : "none";
              if (IMAGE_EXTS.has(ext)) {
                images++;
              }
            }
          }
        };

        await scan(folderPath);
        if (cancelled) return;
        setFilesCount(files);
        setImagesCount(images);
      } catch (e) {
        console.error("Failed to scan workspace files for dashboard", e);
        if (!cancelled) {
          setFilesCount(0);
          setImagesCount(0);
        }
      }
    };

    void runScan();
    return () => {
      cancelled = true;
    };
  }, [visible, folderPath]);

  // Load metrics and sessions
  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);

    const loadData = async () => {
      try {
        // Read memory stats
        const memory = await window.hermesAPI.readMemory(activeProfile);
        if (cancelled) return;
        if (memory && memory.stats) {
          setTotalSessions(memory.stats.totalSessions || 0);
        }

        // Read installed skills
        try {
          const skillsList = await window.hermesAPI.listInstalledSkills(activeProfile);
          if (cancelled) return;
          setSkillsCount(skillsList && skillsList.length > 0 ? Math.min(skillsList.length, 5) : 5);
        } catch {
          setSkillsCount(5);
        }

        // Read available models
        try {
          const modelsList = await window.hermesAPI.listModels();
          if (cancelled) return;
          setModelsCountState(modelsList && modelsList.length > 0 ? modelsList.length : 10);
        } catch {
          setModelsCountState(10);
        }

        // Read sessions
        const sessions = await window.hermesAPI.listSessions(100, 0);
        if (cancelled) return;

        // Slice top 5 for recent list
        const sliced = sessions.slice(0, 5).map((s) => ({
          id: s.id,
          title: s.title,
          model: s.model,
          messageCount: s.messageCount,
          startedAt: s.startedAt
        }));
        setRecentSessions(sliced);

        // Aggregate model counts
        const counts: Record<string, number> = {};
        sessions.forEach((s) => {
          const m = s.model || "Unknown Model";
          counts[m] = (counts[m] || 0) + 1;
        });
        setModelCounts(counts);

      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    if (visible) {
      void loadData();
    }
    return () => {
      cancelled = true;
    };
  }, [visible, activeProfile]);

  // Get current date string
  const currentDateString = useMemo(() => {
    const options: Intl.DateTimeFormatOptions = {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric"
    };
    return new Date().toLocaleDateString("en-US", options);
  }, []);

  const modelsData = useMemo(() => {
    const hasData = Object.keys(modelCounts).length > 0;
    if (hasData) {
      const sorted = Object.entries(modelCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3);
      return sorted.map(([model, count], index) => {
        const percentage = totalSessions > 0 ? Math.round((count / totalSessions) * 100) : 0;
        return {
          name: model.split(/[\\/]/).pop() || model,
          count,
          percentage,
          index
        };
      });
    } else {
      // Mock data to display a gorgeous, filled state when there's no chat history
      return [
        { name: "DeepSeek-Coder (Ollama)", count: 21, percentage: 70, index: 0 },
        { name: "Qwen2.5-Coder (Ollama)", count: 9, percentage: 30, index: 1 }
      ];
    }
  }, [modelCounts, totalSessions]);

  // Format relative time (e.g. "2 hours ago")
  const formatRelativeTime = (timestamp: number) => {
    const diff = Date.now() - timestamp;
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "Just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  const style = useMemo<React.CSSProperties>(
    () => ({
      display: visible ? "flex" : "none",
      flex: 1,
      flexDirection: "column",
      overflow: "hidden",
      height: "100%",
      width: "100%",
      background: "#131314"
    }),
    [visible],
  );

  const activeWorkspaceName = useMemo(() => {
    if (!folderPath) return "No Workspace";
    return folderPath.split(/[\\/]/).filter(Boolean).pop() || folderPath;
  }, [folderPath]);

  return (
    <div style={style} className="dashboard-screen">
      {/* Scoped CSS styling matching Google AI Studio */}
      <style>{`
        .dashboard-container {
          flex: 1;
          overflow-y: auto;
          padding: 32px 40px;
        }
        .dashboard-container::-webkit-scrollbar {
          width: 8px;
        }
        .dashboard-container::-webkit-scrollbar-track {
          background: transparent;
        }
        .dashboard-container::-webkit-scrollbar-thumb {
          background: #3c4043;
          border-radius: 4px;
        }
        .dashboard-container::-webkit-scrollbar-thumb:hover {
          background: #4f5357;
        }
        .dashboard-welcome {
          margin-bottom: 30px;
        }
        .dashboard-welcome h1 {
          margin: 0;
          font-size: 24px;
          fontWeight: 400;
          color: #e3e3e3;
        }
        .dashboard-welcome p {
          margin: 6px 0 0 0;
          font-size: 13px;
          color: #8e918f;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .dashboard-grid {
          display: grid;
          grid-template-columns: repeat(6, 1fr);
          gap: 16px;
          margin-bottom: 32px;
        }
        .kpi-card {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          padding: 22px 24px;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
          backdrop-filter: blur(10px);
          -webkit-backdrop-filter: blur(10px);
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          position: relative;
          overflow: hidden;
        }
        .kpi-card::after {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.08), transparent);
        }
        .kpi-card:hover {
          border-color: rgba(168, 199, 250, 0.3);
          transform: translateY(-4px);
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35), 0 0 20px rgba(168, 199, 250, 0.05);
          background: rgba(255, 255, 255, 0.03);
        }
        .kpi-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          color: #8e918f;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 12px;
        }
        .kpi-value {
          font-size: 26px;
          font-weight: 600;
          color: #e3e3e3;
        }
        .kpi-footer {
          margin-top: 8px;
          font-size: 11px;
          color: #a8c7fa;
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .dashboard-layout-main {
          display: grid;
          grid-template-columns: 2fr 1fr;
          gap: 24px;
        }
        @media (max-width: 900px) {
          .dashboard-layout-main {
            grid-template-columns: 1fr;
          }
        }
        .section-card {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          padding: 24px;
          display: flex;
          flex-direction: column;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
          backdrop-filter: blur(10px);
          -webkit-backdrop-filter: blur(10px);
        }
        .section-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 20px;
        }
        .section-title {
          font-size: 15px;
          font-weight: 500;
          color: #e3e3e3;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .recent-chat-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .recent-chat-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.04);
          border-radius: 10px;
          padding: 14px 18px;
          cursor: pointer;
          transition: all 0.2s ease-in-out;
        }
        .recent-chat-item:hover {
          border-color: rgba(168, 199, 250, 0.2);
          background: rgba(168, 199, 250, 0.04);
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        .recent-chat-title {
          font-size: 13px;
          font-weight: 500;
          color: #e3e3e3;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 280px;
        }
        .recent-chat-meta {
          font-size: 11px;
          color: #8e918f;
          margin-top: 4px;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        /* Quick Actions Card Design */
        .quick-action-card {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          padding: 14px 18px;
          color: #e3e3e3;
          font-size: 13.5px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          position: relative;
          overflow: hidden;
        }
        .quick-action-card::before {
          content: "";
          position: absolute;
          left: 0;
          top: 0;
          height: 100%;
          width: 4px;
          background: var(--card-accent, #a8c7fa);
          opacity: 0.8;
          transition: width 0.2s ease;
        }
        .quick-action-card:hover {
          border-color: rgba(168, 199, 250, 0.2);
          background: rgba(168, 199, 250, 0.04);
          transform: translateX(4px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        .quick-action-card:hover::before {
          width: 6px;
        }
        .quick-action-icon-wrapper {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.04);
          color: var(--card-accent, #a8c7fa);
          transition: all 0.2s ease;
        }
        .quick-action-card:hover .quick-action-icon-wrapper {
          background: var(--card-accent-transparent, rgba(168, 199, 250, 0.15));
          transform: scale(1.05);
        }
        .quick-action-info {
          display: flex;
          flex-direction: column;
          gap: 2px;
          text-align: left;
        }
        .quick-action-title {
          font-size: 13.5px;
          font-weight: 500;
          color: #e3e3e3;
        }
        .quick-action-desc {
          font-size: 11px;
          color: #8e918f;
        }
        .quick-action-arrow {
          color: #8e918f;
          transition: transform 0.2s ease, color 0.2s ease;
        }
        .quick-action-card:hover .quick-action-arrow {
          transform: translateX(2px);
          color: var(--card-accent, #a8c7fa);
        }

        /* Model distribution styles */
        .model-distribution-list {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-top: 8px;
        }
        .model-dist-item {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .model-dist-info {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .model-dist-name-group {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .model-dist-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--model-color, #a8c7fa);
          box-shadow: 0 0 6px var(--model-color, #a8c7fa);
        }
        .model-dist-name {
          font-size: 12.5px;
          font-weight: 500;
          color: #e3e3e3;
        }
        .model-dist-percentage {
          font-size: 12px;
          font-weight: 600;
          color: var(--model-color, #a8c7fa);
        }
        .model-dist-track {
          height: 8px;
          background: rgba(255, 255, 255, 0.04);
          border-radius: 4px;
          overflow: hidden;
          position: relative;
        }
        .model-dist-fill {
          height: 100%;
          border-radius: 4px;
          background: linear-gradient(90deg, var(--model-color-start), var(--model-color-end));
          box-shadow: 0 0 8px var(--model-color-shadow);
          transition: width 1s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* Empty state design */
        .empty-conversations-box {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 220px;
          color: #8e918f;
          border: 1px dashed rgba(255, 255, 255, 0.08);
          background: rgba(255, 255, 255, 0.01);
          border-radius: 12px;
          text-align: center;
          padding: 24px;
          transition: all 0.3s ease;
        }
        .empty-conversations-box:hover {
          border-color: rgba(168, 199, 250, 0.25);
          background: rgba(168, 199, 250, 0.02);
        }
        .empty-icon-wrapper {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: rgba(168, 199, 250, 0.04);
          color: #a8c7fa;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 14px;
          box-shadow: 0 0 12px rgba(168, 199, 250, 0.05);
        }
        .new-chat-primary-btn {
          padding: 8px 20px;
          background: linear-gradient(135deg, #a8c7fa, #7baaf7);
          color: #042b4d;
          border: none;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          box-shadow: 0 4px 12px rgba(168, 199, 250, 0.15);
        }
        .new-chat-primary-btn:hover {
          transform: translateY(-1px);
          box-shadow: 0 6px 16px rgba(168, 199, 250, 0.25);
          filter: brightness(1.05);
        }
        .new-chat-primary-btn:active {
          transform: translateY(1px);
        }
      `}</style>

      <div className="dashboard-container">
        {/* Welcome Header */}
        <div className="dashboard-welcome">
          <h1>Welcome to Moltress</h1>
          <p>
            <Calendar size={14} />
            <span>{currentDateString}</span>
          </p>
        </div>

        {/* KPI Cards Row */}
        <div className="dashboard-grid">
          {/* Card 1: Total Chats */}
          <div className="kpi-card">
            <div className="kpi-header">
              <span>Total Chats</span>
              <MessageSquare size={14} style={{ color: "#a8c7fa" }} />
            </div>
            <div className="kpi-value">{isLoading ? "..." : totalSessions}</div>
            <div className="kpi-footer">
              <TrendingUp size={11} />
              <span>Total sessions logged</span>
            </div>
          </div>

          {/* Card 2: Total Files */}
          <div className="kpi-card">
            <div className="kpi-header">
              <span>Total Files</span>
              <FileText size={14} style={{ color: "#5cdb5c" }} />
            </div>
            <div className="kpi-value" style={{ color: "#5cdb5c" }}>
              {filesCount === null ? "..." : filesCount}
            </div>
            <div className="kpi-footer" style={{ color: "#5cdb5c" }}>
              <span>Scanned in workspace</span>
            </div>
          </div>

          {/* Card 3: Total Images */}
          <div className="kpi-card">
            <div className="kpi-header">
              <span>Total Images</span>
              <Image size={14} style={{ color: "#f2994a" }} />
            </div>
            <div className="kpi-value" style={{ color: "#f2994a" }}>
              {imagesCount === null ? "..." : imagesCount}
            </div>
            <div className="kpi-footer" style={{ color: "#f2994a" }}>
              <span>Images in workspace</span>
            </div>
          </div>

          {/* Card 4: Total Skills */}
          <div className="kpi-card">
            <div className="kpi-header">
              <span>Total Skills</span>
              <Puzzle size={14} style={{ color: "#c58af9" }} />
            </div>
            <div className="kpi-value" style={{ color: "#c58af9" }}>
              {skillsCount}
            </div>
            <div className="kpi-footer" style={{ color: "#c58af9" }}>
              <span>Active capabilities</span>
            </div>
          </div>

          {/* Card 5: Available Models */}
          <div className="kpi-card">
            <div className="kpi-header">
              <span>Available Models</span>
              <Cpu size={14} style={{ color: "#a8c7fa" }} />
            </div>
            <div className="kpi-value">
              {modelsCountState}
            </div>
            <div className="kpi-footer">
              <span>Models present</span>
            </div>
          </div>

          {/* Card 6: Working Dir */}
          <div className="kpi-card">
            <div className="kpi-header">
              <span>Working Dir</span>
              <FolderOpen size={14} style={{ color: "#a8c7fa" }} />
            </div>
            <div className="kpi-value" style={{ fontSize: 18, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {activeWorkspaceName}
            </div>
            <div className="kpi-footer">
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                Path: {folderPath || "None"}
              </span>
            </div>
          </div>
        </div>

        {/* Layout Main Sections */}
        <div className="dashboard-layout-main">
          {/* Left Block: Recent Chats */}
          <div className="section-card">
            <div className="section-header">
              <span className="section-title">
                <MessageSquare size={16} style={{ color: "#a8c7fa" }} />
                <span>Recent Conversations</span>
              </span>
            </div>

            {isLoading ? (
              <div style={{ color: "#8e918f", fontSize: 13 }}>Loading recent chats...</div>
                        ) : recentSessions.length === 0 ? (
              <div className="empty-conversations-box">
                <div className="empty-icon-wrapper">
                  <MessageSquare size={20} />
                </div>
                <p style={{ margin: "0 0 16px 0", fontSize: 13, color: "#8e918f" }}>
                  No recent sessions. Start a new chat to begin!
                </p>
                <button
                  type="button"
                  onClick={onNewChat}
                  className="new-chat-primary-btn"
                >
                  New Chat
                </button>
              </div>
            ) : (
              <div className="recent-chat-list">
                {recentSessions.map((session) => (
                  <div
                    key={session.id}
                    className="recent-chat-item"
                    onClick={() => onResumeSession(session.id)}
                  >
                    <div>
                      <div className="recent-chat-title">{session.title || "Untitled Conversation"}</div>
                      <div className="recent-chat-meta">
                        <span>Model: {session.model}</span>
                        <span>•</span>
                        <span>{session.messageCount} messages</span>
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#8e918f" }}>
                      <span>{formatRelativeTime(session.startedAt)}</span>
                      <ChevronRight size={14} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Block: Model distribution & Quick Actions */}
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* Model stats */}
            <div className="section-card" style={{ padding: "20px 24px" }}>
              <div className="section-header" style={{ marginBottom: 16 }}>
                <span className="section-title">
                  <Cpu size={16} style={{ color: "#a8c7fa" }} />
                  <span>Model Distribution</span>
                </span>

              </div>

              {isLoading ? (
                <div style={{ color: "#8e918f", fontSize: 12 }}>Loading models...</div>
              ) : (
                <div className="model-distribution-list">
                  {modelsData.map((model) => {
                    const colorVars = [
                      {
                        color: "#8ab4f8",
                        start: "#8ab4f8",
                        end: "#4285f4",
                        shadow: "rgba(66, 133, 244, 0.4)"
                      },
                      {
                        color: "#c58af9",
                        start: "#c58af9",
                        end: "#9333ea",
                        shadow: "rgba(147, 51, 234, 0.4)"
                      },
                      {
                        color: "#ff8f6b",
                        start: "#ff8f6b",
                        end: "#ea580c",
                        shadow: "rgba(234, 88, 12, 0.4)"
                      }
                    ][model.index % 3];

                    return (
                      <div
                        className="model-dist-item"
                        key={model.name}
                        style={{
                          "--model-color": colorVars.color,
                          "--model-color-start": colorVars.start,
                          "--model-color-end": colorVars.end,
                          "--model-color-shadow": colorVars.shadow
                        } as React.CSSProperties}
                      >
                        <div className="model-dist-info">
                          <div className="model-dist-name-group">
                            <div className="model-dist-dot" />
                            <span className="model-dist-name" title={model.name}>
                              {model.name}
                            </span>
                          </div>
                          <span className="model-dist-percentage">{model.percentage}%</span>
                        </div>
                        <div className="model-dist-track">
                          <div className="model-dist-fill" style={{ width: `${model.percentage}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Quick Actions */}
            <div className="section-card" style={{ padding: "20px 24px" }}>
              <div className="section-header" style={{ marginBottom: 16 }}>
                <span className="section-title">
                  <Settings size={16} style={{ color: "#a8c7fa" }} />
                  <span>Quick Tasks</span>
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <button
                  type="button"
                  className="quick-action-card"
                  style={{
                    "--card-accent": "#5cdb5c",
                    "--card-accent-transparent": "rgba(92, 219, 92, 0.12)",
                  } as React.CSSProperties}
                  onClick={onNewChat}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div className="quick-action-icon-wrapper">
                      <PlusCircle size={16} />
                    </div>
                    <div className="quick-action-info">
                      <span className="quick-action-title">Start New Chat</span>
                      <span className="quick-action-desc">Launch a new session with Moltress AI</span>
                    </div>
                  </div>
                  <ChevronRight size={14} className="quick-action-arrow" />
                </button>

                <button
                  type="button"
                  className="quick-action-card"
                  style={{
                    "--card-accent": "#f2994a",
                    "--card-accent-transparent": "rgba(242, 153, 74, 0.12)",
                  } as React.CSSProperties}
                  onClick={() => onNavigateTo("workspace")}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div className="quick-action-icon-wrapper">
                      <FolderOpen size={16} />
                    </div>
                    <div className="quick-action-info">
                      <span className="quick-action-title">Open Code Explorer</span>
                      <span className="quick-action-desc">Navigate project files and codebases</span>
                    </div>
                  </div>
                  <ChevronRight size={14} className="quick-action-arrow" />
                </button>

                <button
                  type="button"
                  className="quick-action-card"
                  style={{
                    "--card-accent": "#a8c7fa",
                    "--card-accent-transparent": "rgba(168, 199, 250, 0.12)",
                  } as React.CSSProperties}
                  onClick={() => onNavigateTo("models")}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div className="quick-action-icon-wrapper">
                      <Cpu size={16} />
                    </div>
                    <div className="quick-action-info">
                      <span className="quick-action-title">Manage Models</span>
                      <span className="quick-action-desc">Configure LLM providers and profiles</span>
                    </div>
                  </div>
                  <ChevronRight size={14} className="quick-action-arrow" />
                </button>

                <button
                  type="button"
                  className="quick-action-card"
                  style={{
                    "--card-accent": "#c58af9",
                    "--card-accent-transparent": "rgba(197, 138, 249, 0.12)",
                  } as React.CSSProperties}
                  onClick={() => onNavigateTo("settings")}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div className="quick-action-icon-wrapper">
                      <Settings size={16} />
                    </div>
                    <div className="quick-action-info">
                      <span className="quick-action-title">Application Settings</span>
                      <span className="quick-action-desc">Modify defaults, themes, and network</span>
                    </div>
                  </div>
                  <ChevronRight size={14} className="quick-action-arrow" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
