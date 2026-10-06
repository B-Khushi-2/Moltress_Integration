import { useCallback, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { Zap, Globe, SlidersHorizontal, ChevronRight, Brain, Activity, CheckCircle2, Cpu, Sparkles } from "lucide-react";
import { ChatInput, type ChatInputHandle } from "./ChatInput";
import { ChatEmptyState } from "./ChatEmptyState";
import { MessageList } from "./MessageList";
import { ModelPicker } from "./ModelPicker";
import { ReasoningEffortPicker } from "./ReasoningEffortPicker";
import { ContextFolderChip } from "./ContextFolderChip";
import { WorktreePanel } from "./WorktreePanel";
import { WebPreviewPanel } from "./WebPreviewPanel";
import { useChatScroll } from "./hooks/useChatScroll";
import { useChatIPC } from "./hooks/useChatIPC";
import { useChatActions, parseBackgroundCommand } from "./hooks/useChatActions";
import { useModelConfig } from "./hooks/useModelConfig";
import { useFastMode } from "./hooks/useFastMode";
import { useReasoningEffort } from "./hooks/useReasoningEffort";
import { useLocalCommands } from "./hooks/useLocalCommands";
import {
  dashboardChatEnabledForConnection,
  useDashboardChatTransport,
} from "./hooks/useDashboardChatTransport";
import { useI18n } from "../../components/useI18n";
import { buildChatTranscript } from "./transcriptUtils";
import { ConfigHealthBanner } from "../../components/ConfigHealthBanner";
import FollowUsModal from "../../components/FollowUsModal";
import type { Attachment } from "../../../../shared/attachments";
import type { ActiveTurn, ChatMessage, UsageState } from "./types";
import type { ContextUsage } from "./ContextGauge";
import { contextWindowForModel } from "./contextWindows";
import { QueuedMessages } from "./QueuedMessages";

interface QueuedMessage {
  text: string;
  attachments: Attachment[];
}

export type { ChatMessage } from "./types";

interface ChatProps {
  /** Stable id for this conversation/run. One <Chat> is mounted per run; all
   *  remain mounted (background sessions) and only the active one is shown. */
  runId: string;
  /** Seed transcript when re-opening a session from history; empty for new chats. */
  initialMessages?: ChatMessage[];
  /** Gateway session id when resuming a known session; null for a new chat. */
  initialSessionId?: string | null;
  /** Whether this run is the one currently shown (drives keyboard handlers). */
  active?: boolean;
  profile?: string;
  onSessionStarted?: () => void;
  onNewChat?: () => void;
  /** Optional callback to navigate to Settings → Diagnose section
   *  when the user clicks "Show details" in the config-health banner. */
  onOpenDiagnose?: () => void;
  /** Reports the agent generating state so the sidebar / active-sessions bar
   *  can show a spinner on each running session. */
  onLoadingChange?: (runId: string, loading: boolean) => void;
  /** Reports the gateway session id once known, so the parent can map
   *  runId ↔ sessionId (live re-attach, spinners, titles). */
  onSessionIdChange?: (runId: string, sessionId: string | null) => void;
  /** Reports the first user message as a best-effort conversation title. */
  onTitleChange?: (runId: string, title: string) => void;
}

function Chat({
  runId,
  initialMessages,
  initialSessionId,
  active = true,
  profile,
  onSessionStarted,
  onNewChat,
  onOpenDiagnose,
  onLoadingChange,
  onSessionIdChange,
  onTitleChange,
}: ChatProps): React.JSX.Element {
  const { t } = useI18n();
  const [messages, setMessages] = useState<ChatMessage[]>(
    initialMessages ?? [],
  );
  const [isLoading, setIsLoading] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [temperature, setTemperature] = useState(0.2);
  const [topP, setTopP] = useState(0.9);
  const [systemInstruction, setSystemInstruction] = useState("");
  const isSoulLoaded = useRef(false);
  const saveSoulTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load system instructions (Soul)
  useEffect(() => {
    isSoulLoaded.current = false;
    window.hermesAPI.readSoul(profile).then((text) => {
      setSystemInstruction(text || "");
      setTimeout(() => {
        isSoulLoaded.current = true;
      }, 100);
    });
  }, [profile]);

  // Debounced saving of system instructions
  useEffect(() => {
    if (!isSoulLoaded.current) return;
    if (saveSoulTimer.current) clearTimeout(saveSoulTimer.current);
    saveSoulTimer.current = setTimeout(() => {
      window.hermesAPI.writeSoul(systemInstruction, profile);
    }, 500);
    return () => {
      if (saveSoulTimer.current) clearTimeout(saveSoulTimer.current);
    };
  }, [systemInstruction, profile]);

  useEffect(() => {
    onLoadingChange?.(runId, isLoading);
  }, [runId, isLoading, onLoadingChange]);
  const [hermesSessionId, setHermesSessionId] = useState<string | null>(
    initialSessionId ?? null,
  );
  // Surface the gateway session id upward whenever it resolves/changes.
  useEffect(() => {
    onSessionIdChange?.(runId, hermesSessionId);
  }, [runId, hermesSessionId, onSessionIdChange]);
  // Best-effort title from the first user bubble (for the active-sessions bar).
  const reportedTitleRef = useRef(false);
  useEffect(() => {
    if (reportedTitleRef.current) return;
    const firstUser = messages.find(
      (m) => m.role === "user" && "content" in m && m.content.trim(),
    );
    if (firstUser && "content" in firstUser) {
      reportedTitleRef.current = true;
      onTitleChange?.(runId, firstUser.content.slice(0, 60));
    }
  }, [runId, messages, onTitleChange]);
  const [toolProgress, setToolProgress] = useState<string | null>(null);
  const [usage, setUsage] = useState<UsageState | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [remoteMode, setRemoteMode] = useState(false);
  const [connectionMode, setConnectionMode] = useState<
    "local" | "remote" | "ssh"
  >("local");
  const [chatTransportPreference, setChatTransportPreference] = useState<
    "auto" | "dashboard" | "legacy"
  >("auto");
  const [connectionModeLoaded, setConnectionModeLoaded] = useState(false);
  // Working folder bound to this conversation (issue #27). Per-conversation,
  // held in memory; reset on session switch / new chat below.
  const [contextFolder, setContextFolder] = useState<string | null>(() => {
    return localStorage.getItem("hermes.workspace.folderPath");
  });
  // Whether the worktree panel is visible (only applies when contextFolder is set)
  // Default false so the panel doesn't open automatically and interfere with scrolling
  const [worktreeVisible, setWorktreeVisible] = useState<boolean>(false);
  const [webPreviewVisible, setWebPreviewVisible] = useState<boolean>(false);
  const [webPreviewUrl, setWebPreviewUrl] =
    useState<string>("https://google.com");
  // Explicit session-scoped model override — set only when the user picks
  // from the chat-screen picker (persist:false). Undefined until then so the
  // TUI gateway bypass in sendMessageViaBestApi is not triggered for normal
  // chats where the user never changed the model (issue #688).
  const [sessionModelOverride, setSessionModelOverride] = useState<
    string | undefined
  >(undefined);
  const dragCounter = useRef(0);
  const chatInputRef = useRef<ChatInputHandle>(null);
  const queueRef = useRef<QueuedMessage[]>([]);
  const [queuedMessages, setQueuedMessages] = useState<QueuedMessage[]>([]);
  const activeTurnRef = useRef<ActiveTurn | null>(null);
  const dashboardChatEnabled = dashboardChatEnabledForConnection(
    import.meta.env.VITE_HERMES_DESKTOP_DASHBOARD_CHAT,
    connectionModeLoaded,
    connectionMode,
    chatTransportPreference,
  );

  useEffect(() => {
    let cancelled = false;
    const loadConnectionConfig = async (): Promise<void> => {
      try {
        const conn = await window.hermesAPI.getConnectionConfig();
        if (!cancelled) {
          setConnectionMode(conn.mode);
          setRemoteMode(conn.mode !== "local");
          setChatTransportPreference(
            conn.moltressEnabled
              ? "legacy"
              : conn.mode === "local"
                ? "auto"
                : conn.mode === "ssh"
                  ? (conn.sshChatTransport ?? "auto")
                  : (conn.remoteChatTransport ?? "auto"),
          );
        }
      } catch {
        if (!cancelled) {
          setConnectionMode("ssh");
          setRemoteMode(true);
          setChatTransportPreference("legacy");
        }
      } finally {
        if (!cancelled) setConnectionModeLoaded(true);
      }
    };
    void loadConnectionConfig();
    const unsubscribe = window.hermesAPI.onConnectionConfigChanged((conn) => {
      setConnectionModeLoaded(true);
      setConnectionMode(conn.mode);
      setRemoteMode(conn.mode !== "local");
      setChatTransportPreference(
        conn.moltressEnabled
          ? "legacy"
          : conn.mode === "local"
            ? "auto"
            : conn.mode === "ssh"
              ? (conn.sshChatTransport ?? "auto")
              : (conn.remoteChatTransport ?? "auto"),
      );
    });
    return (): void => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const { containerRef, bottomRef } = useChatScroll(messages);
  const modelConfig = useModelConfig(profile);
  const {
    fastMode,
    toggle: toggleFastMode,
    set: setFastTier,
  } = useFastMode(profile);
  const { reasoningEffort, setReasoningEffort } = useReasoningEffort(profile);

  // Pre-send readiness — fail-open check that disables Send + shows
  // an inline banner when the desktop can predict that the gateway
  // will reject the request (e.g. provider configured but its API
  // key is missing from .env). Re-runs on profile/model/baseUrl
  // change so the banner reflects the current state.
  const [readiness, setReadiness] = useState<{
    ok: boolean;
    code?: string;
    message?: string;
    fixLocation?: string;
    expectedEnvKey?: string;
  }>({ ok: true });
  useEffect(() => {
    let cancelled = false;
    (async (): Promise<void> => {
      try {
        const r = await window.hermesAPI.validateChatReadiness(profile);
        if (!cancelled) setReadiness(r);
      } catch {
        // Fail open on IPC error — never block Send on validation failure
        if (!cancelled) setReadiness({ ok: true });
      }
    })();
    return (): void => {
      cancelled = true;
    };
  }, [
    profile,
    modelConfig.currentModel,
    modelConfig.currentProvider,
    modelConfig.currentBaseUrl,
  ]);

  // Authoritative context-window size for the active model, resolved from the
  // provider's /models catalogue (issue #597). Null until/unless the provider
  // advertises it — the gauge then falls back to the static heuristic.
  const [realContextWindow, setRealContextWindow] = useState<number | null>(
    null,
  );
  useEffect(() => {
    let cancelled = false;
    setRealContextWindow(null);
    if (!modelConfig.currentModel) return;
    window.hermesAPI
      .getModelContextWindow(
        modelConfig.currentProvider,
        modelConfig.currentModel,
        modelConfig.currentBaseUrl,
        profile,
      )
      .then((w) => {
        if (!cancelled && typeof w === "number" && w > 0) {
          setRealContextWindow(w);
        }
      })
      .catch(() => {
        /* fall back to heuristic */
      });
    return (): void => {
      cancelled = true;
    };
  }, [
    profile,
    modelConfig.currentModel,
    modelConfig.currentProvider,
    modelConfig.currentBaseUrl,
  ]);

  const visibleSessionScopeId = messages.length === 0 ? null : hermesSessionId;

  useChatIPC({
    runId,
    sessionScopeId: visibleSessionScopeId,
    setMessages,
    setHermesSessionId,
    setToolProgress,
    setIsLoading,
    setUsage,
    activeTurnRef,
  });

  // No parent-driven reset effects: each run is its own <Chat key={runId}>
  // instance. A new chat is a fresh mount, and switching sessions just flips
  // which mounted instance is shown — local state (session id, context folder,
  // queue) belongs to this run and persists while it streams in the background.

  // Cmd/Ctrl+N → new chat. Only the active (visible) run handles it; otherwise
  // every mounted background Chat would fire onNewChat in parallel.
  useEffect(() => {
    if (!active) return;
    function onKey(e: KeyboardEvent): void {
      if ((e.metaKey || e.ctrlKey) && e.key === "n") {
        e.preventDefault();
        onNewChat?.();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, onNewChat]);

  // Listen for in-app link clicks to load in the split-screen Web Preview panel
  useEffect(() => {
    if (!active) return;
    const handleNavigate = (e: Event): void => {
      const customEvent = e as CustomEvent<string>;
      const url = customEvent.detail;
      if (url) {
        setWebPreviewUrl(url);
        setWebPreviewVisible(true);
      }
    };
    document.addEventListener("web-preview:navigate", handleNavigate);
    return () => {
      document.removeEventListener("web-preview:navigate", handleNavigate);
    };
  }, [active]);

  // "Copy entire chat" context-menu items (issue #298) — serialise the whole
  // conversation in the requested format and copy it. A ref keeps the latest
  // messages without re-registering the IPC listener on every chunk.
  const messagesRef = useRef(messages);
  useEffect(() => {
    messagesRef.current = messages;
  });
  useEffect(() => {
    if (!active) return;
    return window.hermesAPI.onContextMenuCopyChat((format) => {
      const msgs = messagesRef.current;
      if (msgs.length === 0) return;
      void window.hermesAPI.copyToClipboard(buildChatTranscript(msgs, format));
    });
  }, [active]);

  // "Select All" on a message (issue #298): the native selectAll role would
  // select the entire window, so scope it to the .chat-bubble under the
  // cursor — the user can then Copy that message.
  useEffect(() => {
    if (!active) return;
    return window.hermesAPI.onContextMenuSelectBubble(({ x, y }) => {
      const bubble = document.elementFromPoint(x, y)?.closest(".chat-bubble");
      if (!bubble) return;
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.selectAllChildren(bubble);
    });
  }, [active]);

  // Restrict the native context menu to chat bubbles and editable fields
  // so it doesn't appear on random UI chrome (sessions list, settings, etc.).
  useEffect(() => {
    if (!active) return;
    const onContextMenu = (e: MouseEvent): void => {
      const target = e.target as Element | null;
      const inBubble = target?.closest(".chat-bubble") != null;
      const inEditable =
        target?.closest("input, textarea, [contenteditable='true']") != null;
      if (!inBubble && !inEditable) {
        e.preventDefault();
      }
    };
    document.addEventListener("contextmenu", onContextMenu);
    return () => document.removeEventListener("contextmenu", onContextMenu);
  }, [active]);

  const addAgentMessage = useCallback(
    (content: string) => {
      setMessages((prev) => [
        ...prev,
        { id: `agent-local-${Date.now()}`, role: "agent", content },
      ]);
    },
    [setMessages],
  );

  // Flip an inline clarify card to its resolved (read-only) state once the user
  // has answered or skipped. The gateway resumes the turn from here, so loading
  // stays active until the next onChatDone.
  const handleClarifyResolved = useCallback(
    (requestId: string, answer: string) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.kind === "clarify" && m.requestId === requestId
            ? { ...m, answer, resolved: true }
            : m,
        ),
      );
    },
    [setMessages],
  );

  const handleClear = useCallback(() => {
    if (isLoading) {
      window.hermesAPI.abortChat(runId);
      setIsLoading(false);
    }
    const idToDelete = hermesSessionId;
    if (idToDelete) {
      void window.hermesAPI.deleteSession(idToDelete);
      void window.hermesAPI.clearStagedAttachments(idToDelete);
    }
    setMessages([]);
    setHermesSessionId(null);
    setContextFolder(null);
    activeTurnRef.current = null;
    setUsage(null);
    setToolProgress(null);
    queueRef.current = [];
    setQueuedMessages([]);
  }, [isLoading, runId, hermesSessionId, setMessages]);

  const localCommands = useLocalCommands({
    profile,
    usage,
    setFastMode: setFastTier,
    onNewChat,
    onClear: handleClear,
    addAgentMessage,
  });

  // Fired once per connection when the dashboard WebSocket transport can't
  // connect (e.g. SSH tunnel → `hermes gateway`, which has no `/api/ws`, issue
  // #667) and we fall back to legacy chat. A fixed toast id dedupes.
  const handleDashboardUnavailable = useCallback(() => {
    toast(t("chat.dashboardUnavailableFallback"), {
      id: "dashboard-unavailable-fallback",
      icon: "ℹ️",
      duration: 8000,
    });
  }, [t]);

  const dashboardTransport = useDashboardChatTransport({
    activeTurnRef,
    contextFolder,
    connectionMode,
    enabled: dashboardChatEnabled,
    fallbackOnUnavailable: chatTransportPreference === "auto",
    hermesSessionId,
    messages,
    model: modelConfig.currentModel,
    modelBaseUrl: modelConfig.currentBaseUrl,
    profile,
    provider: modelConfig.currentProvider,
    setHermesSessionId,
    setIsLoading,
    setMessages,
    setToolProgress,
    setUsage,
    onDashboardUnavailable: handleDashboardUnavailable,
  });

  // Defer a message onto the busy queue (used when a slash command resolves to
  // an agent prompt while a turn is already in flight).
  const enqueueMessage = useCallback((text: string) => {
    queueRef.current.push({ text, attachments: [] });
    setQueuedMessages([...queueRef.current]);
  }, []);

  const actions = useChatActions({
    runId,
    profile,
    hermesSessionId,
    messages,
    isLoading,
    setIsLoading,
    setMessages,
    onSessionStarted,
    chatInputRef,
    localCommands,
    activeTurnRef,
    contextFolder,
    sessionModel: sessionModelOverride,
    sendViaDashboard: dashboardTransport.enabled
      ? dashboardTransport.sendMessage
      : undefined,
    execSlashViaDashboard: dashboardTransport.enabled
      ? dashboardTransport.execSlash
      : undefined,
    runBackgroundViaDashboard: dashboardTransport.enabled
      ? dashboardTransport.runBackground
      : undefined,
    addAgentMessage,
    enqueueMessage,
    abortDashboard: dashboardTransport.enabled
      ? dashboardTransport.abort
      : undefined,
  });

  // Stable ref to handleSend so the drain effect doesn't re-trigger on
  // identity changes (regression #5 from PR #315).
  const handleSendRef = useRef(actions.handleSend);
  const handleBackgroundRef = useRef(actions.handleBackground);
  useEffect(() => {
    handleSendRef.current = actions.handleSend;
    handleBackgroundRef.current = actions.handleBackground;
  });

  // Drain queued messages one at a time when the agent finishes.
  useEffect(() => {
    if (isLoading) return;
    const next = queueRef.current.shift();
    if (!next) return;
    setQueuedMessages([...queueRef.current]);
    handleSendRef.current(next.text, next.attachments, true).catch(() => {
      // Put the message back at the front so it isn't silently lost if
      // the send fails (e.g. IPC error before onChatError fires).
      queueRef.current.unshift(next);
      setQueuedMessages([...queueRef.current]);
    });
  }, [isLoading]);

  const handleRemoveQueued = useCallback((index: number) => {
    queueRef.current.splice(index, 1);
    setQueuedMessages([...queueRef.current]);
  }, []);

  const handleSubmitOrQueue = useCallback(
    (text: string, attachments: Attachment[]) => {
      // Side questions (`/btw`) run on a concurrent background agent, so they
      // must never queue — fire them immediately even while the main turn is in
      // flight. This is the whole point of "ask without affecting context".
      const bgQuestion = parseBackgroundCommand(text);
      if (bgQuestion !== null) {
        if (bgQuestion)
          void handleBackgroundRef.current(bgQuestion, attachments);
        return;
      }
      // Other slash commands (`/status`, `/compact`, …) run on the gateway's
      // slash worker or are renderer-local — all concurrent with any in-flight
      // turn — so dispatch them immediately instead of queueing. handleSend's
      // own routing decides what each one does (and defers the rare command
      // that resolves to an agent prompt while busy). Limited to local commands
      // and the dashboard transport (which has the worker); the legacy
      // transport has no concurrent path, so its slash commands still queue.
      if (
        text.startsWith("/") &&
        (localCommands.isLocal(text) || dashboardChatEnabled)
      ) {
        void handleSendRef.current(text, attachments, true);
        return;
      }
      if (isLoading) {
        queueRef.current.push({ text, attachments });
        setQueuedMessages([...queueRef.current]);
        return;
      }
      void handleSendRef.current(text, attachments);
    },
    [isLoading, localCommands, dashboardChatEnabled],
  );

  const handleSuggestion = useCallback((text: string) => {
    chatInputRef.current?.setText(text);
  }, []);

  const handlePickFolder = useCallback(async () => {
    const path = await window.hermesAPI.selectFolder();
    if (path) setContextFolder(path);
  }, []);

  const handleClearFolder = useCallback(() => {
    setContextFolder(null);
  }, []);

  // Drag-and-drop: filter for dragenter events carrying files (suppresses
  // text-drag noise from the textarea autocomplete and other in-app drags).
  const eventHasFiles = useCallback((e: React.DragEvent): boolean => {
    const types = e.dataTransfer?.types;
    if (!types) return false;
    for (let i = 0; i < types.length; i++) {
      if (types[i] === "Files") return true;
    }
    return false;
  }, []);

  const handleDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (!eventHasFiles(e)) return;
      e.preventDefault();
      dragCounter.current += 1;
      if (dragCounter.current === 1) setDragActive(true);
    },
    [eventHasFiles],
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!eventHasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    },
    [eventHasFiles],
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current = Math.max(0, dragCounter.current - 1);
    if (dragCounter.current === 0) setDragActive(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      if (!eventHasFiles(e)) return;
      e.preventDefault();
      dragCounter.current = 0;
      setDragActive(false);
      const files = Array.from(e.dataTransfer.files);
      if (files.length === 0) return;
      void chatInputRef.current?.addFiles(files);
    },
    [eventHasFiles],
  );

  // Context-gauge data: the latest turn's prompt tokens vs the model's window.
  const contextUsage: ContextUsage | null = usage?.contextTokens
    ? {
        used: usage.contextTokens,
        window:
          realContextWindow ?? contextWindowForModel(modelConfig.currentModel),
        cacheReadTokens: usage.cacheReadTokens,
        cacheWriteTokens: usage.cacheWriteTokens,
      }
    : null;

  const prettyPrintHTML = (html: string): string => {
    const formatNode = (node: Node, level: number = 0): string => {
      const indent = "  ".repeat(level);
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent?.trim();
        return text ? `${indent}${text}\n` : "";
      }
      if (node.nodeType === Node.COMMENT_NODE) {
        return `${indent}<!--${node.textContent}-->\n`;
      }
      if (node.nodeType === Node.ELEMENT_NODE) {
        const el = node as Element;
        const tagName = el.tagName.toLowerCase();
        let attrs = "";
        for (let i = 0; i < el.attributes.length; i++) {
          const attr = el.attributes[i];
          attrs += ` ${attr.name}="${attr.value}"`;
        }
        const isVoid = [
          "area",
          "base",
          "br",
          "col",
          "embed",
          "hr",
          "img",
          "input",
          "link",
          "meta",
          "param",
          "source",
          "track",
          "wbr",
        ].includes(tagName);
        if (isVoid) {
          return `${indent}<${tagName}${attrs}>\n`;
        }
        if (
          el.childNodes.length === 1 &&
          el.firstChild?.nodeType === Node.TEXT_NODE
        ) {
          const text = el.firstChild.textContent?.trim();
          return text
            ? `${indent}<${tagName}${attrs}>${text}</${tagName}>\n`
            : `${indent}<${tagName}${attrs}></${tagName}>\n`;
        }
        if (el.childNodes.length === 0) {
          return `${indent}<${tagName}${attrs}></${tagName}>\n`;
        }
        let childrenHtml = "";
        for (let i = 0; i < el.childNodes.length; i++) {
          childrenHtml += formatNode(el.childNodes[i], level + 1);
        }
        return `${indent}<${tagName}${attrs}>\n${childrenHtml}${indent}</${tagName}>\n`;
      }
      return "";
    };

    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, "text/html");
      const body = doc.body;
      if (body.childNodes.length > 0) {
        let result = "";
        for (let i = 0; i < body.childNodes.length; i++) {
          result += formatNode(body.childNodes[i], 0);
        }
        return result.trim();
      }
    } catch (e) {
      console.error("Failed to pretty print HTML", e);
    }
    return html;
  };

  const handleInspectElement = useCallback(
    (payload: {
      tagName: string;
      id: string;
      className: string;
      outerHTML: string;
    }) => {
      const formattedHtml = prettyPrintHTML(payload.outerHTML);
      const formatted = `Here is the HTML for the \`<${payload.tagName}>\` component to debug:\n\`\`\`html\n${formattedHtml}\n\`\`\``;
      chatInputRef.current?.appendText(formatted);
    },
    [],
  );

  return (
    <div
      className="chat-container"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{
        display: "flex",
        flexDirection: "row",
        height: "100%",
        width: "100%",
        overflow: "hidden",
      }}
    >
      {/* Left Column: Chat messages, banners, and inputs */}
      <div
        className="chat-main-section"
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          height: "100%",
        }}
      >
        <ConfigHealthBanner profile={profile} onOpenDiagnose={onOpenDiagnose} />

        <div className="chat-body" style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <div className="chat-messages" ref={containerRef}>
            {messages.length === 0 ? (
              <ChatEmptyState
                onSelectSuggestion={handleSuggestion}
                profile={profile}
              />
            ) : (
              <MessageList
                messages={messages}
                isLoading={isLoading}
                toolProgress={toolProgress}
                onApprove={actions.handleApprove}
                onDeny={actions.handleDeny}
                onClarifyResolved={handleClarifyResolved}
              />
            )}
            <div ref={bottomRef} />
          </div>

          {contextFolder && worktreeVisible && (
            <WorktreePanel folderPath={contextFolder} />
          )}

          {webPreviewVisible && (
            <WebPreviewPanel
              initialUrl={webPreviewUrl}
              onClose={() => setWebPreviewVisible(false)}
              onInspectElement={handleInspectElement}
            />
          )}
        </div>

        <div
          className="chat-input-area"
          style={{
            position: "relative",
            padding: "12px 24px 16px",
            borderTop: "1px solid var(--border)",
            flexShrink: 0,
          }}
        >
          <QueuedMessages
            messages={queuedMessages}
            onRemove={handleRemoveQueued}
          />
          <ChatInput
            ref={chatInputRef}
            isLoading={isLoading}
            hasSession={!!hermesSessionId}
            sessionId={hermesSessionId}
            remoteMode={remoteMode}
            profile={profile}
            contextUsage={contextUsage}
            readiness={readiness}
            onSubmit={handleSubmitOrQueue}
            onQuickAsk={actions.handleQuickAsk}
            onAbort={actions.handleAbort}
            toolbarExtras={
              <>
                <ModelPicker
                  currentModel={modelConfig.currentModel}
                  currentProvider={modelConfig.currentProvider}
                  currentBaseUrl={modelConfig.currentBaseUrl}
                  modelGroups={modelConfig.modelGroups}
                  displayModel={modelConfig.displayModel}
                  onOpen={modelConfig.reload}
                  onSelectModel={(provider, model, baseUrl) => {
                    void modelConfig.selectModel(provider, model, baseUrl, {
                      persist: false,
                    });
                    setSessionModelOverride(model || undefined);
                  }}
                />
                <ReasoningEffortPicker
                  value={reasoningEffort}
                  onChange={setReasoningEffort}
                />
                <div className="chat-fast-wrapper">
                  <button
                    type="button"
                    className={`btn-ghost chat-fast-btn ${fastMode ? "chat-fast-active" : ""}`}
                    onClick={toggleFastMode}
                  >
                    <Zap size={14} />
                  </button>
                  <div className="chat-fast-popover">
                    <strong>
                      {fastMode ? t("chat.fastModeOn") : t("chat.fastMode")}
                    </strong>
                    <span>
                      {fastMode
                        ? t("chat.fastModeActive")
                        : t("chat.fastModeInactive")}
                    </span>
                  </div>
                </div>
                <ContextFolderChip
                  contextFolder={contextFolder}
                  show={!remoteMode}
                  worktreeVisible={worktreeVisible}
                  onPickFolder={handlePickFolder}
                  onClearFolder={handleClearFolder}
                  onToggleWorktree={() => setWorktreeVisible((v) => !v)}
                />
                <button
                  type="button"
                  className={`btn-ghost chat-tool-btn ${webPreviewVisible ? "chat-tool-btn-active" : ""}`}
                  onClick={() => setWebPreviewVisible((v) => !v)}
                  title={
                    webPreviewVisible ? "Hide web preview" : "Show web preview"
                  }
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 28,
                    height: 28,
                    padding: 0,
                    borderRadius: 6,
                    color: webPreviewVisible
                      ? "var(--accent-text)"
                      : "var(--text-secondary)",
                    background: webPreviewVisible
                      ? "color-mix(in srgb, var(--accent-text) 10%, transparent)"
                      : "transparent",
                  }}
                >
                  <Globe size={14} />
                </button>

                <button
                  type="button"
                  className={`btn-ghost chat-tool-btn ${showSidebar ? "chat-tool-btn-active" : ""}`}
                  onClick={() => setShowSidebar((v) => !v)}
                  title={showSidebar ? "Hide Run Settings" : "Show Run Settings"}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 28,
                    height: 28,
                    padding: 0,
                    borderRadius: 6,
                    color: showSidebar ? "var(--accent-text)" : "var(--text-secondary)",
                    background: showSidebar
                      ? "color-mix(in srgb, var(--accent-text) 10%, transparent)"
                      : "transparent",
                  }}
                >
                  <SlidersHorizontal size={14} />
                </button>
              </>
            }
          />
        </div>
      </div>

      {/* Right Column: Settings Sidebar */}
      {showSidebar && (
        <div
          className="chat-control-sidebar ai-sidebar-container"
          style={{
            width: 330,
            minWidth: 330,
            borderLeft: "1px solid rgba(255, 255, 255, 0.08)",
            background: "#17181c",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
            height: "100%",
            boxSizing: "border-box",
            color: "#e3e3e3",
          }}
        >
          {/* Custom style overrides for Intelligence Panel */}
          <style>{`
            .ai-sidebar-container::-webkit-scrollbar {
              width: 6px;
            }
            .ai-sidebar-container::-webkit-scrollbar-track {
              background: transparent;
            }
            .ai-sidebar-container::-webkit-scrollbar-thumb {
              background: #2b2c30;
              border-radius: 3px;
            }
            .ai-sidebar-container::-webkit-scrollbar-thumb:hover {
              background: #3c3d42;
            }

            .intel-section {
              margin-bottom: 24px;
            }

            .intel-section-header {
              font-size: 11px;
              font-weight: 700;
              text-transform: uppercase;
              color: #8e918f;
              letter-spacing: 0.8px;
              display: flex;
              align-items: center;
              gap: 8px;
              margin-bottom: 12px;
            }

            .intel-card {
              background: #1e1f24;
              border: 1px solid rgba(255, 255, 255, 0.04);
              border-radius: 12px;
              padding: 16px;
              display: flex;
              flex-direction: column;
              gap: 14px;
            }

            .intel-model-badge {
              display: flex;
              align-items: center;
              gap: 8px;
              background: #131316;
              border: 1px solid rgba(255, 255, 255, 0.06);
              border-radius: 8px;
              padding: 8px 12px;
              font-size: 12px;
              font-weight: 500;
              color: #ffffff;
            }

            .intel-status-dot {
              width: 8px;
              height: 8px;
              border-radius: 50%;
              background: #34a853;
              box-shadow: 0 0 8px #34a853;
            }

            .intel-slider-row {
              display: flex;
              flex-direction: column;
              gap: 6px;
            }
            .intel-slider-header {
              display: flex;
              justify-content: space-between;
              font-size: 12px;
              color: #c4c7c5;
            }
            .intel-slider-value {
              font-weight: 600;
              color: #8ab4f8;
              font-family: monospace;
            }

            .intel-range-input {
              -webkit-appearance: none;
              width: 100%;
              height: 4px;
              border-radius: 2px;
              background: #3c4043;
              outline: none;
              margin: 4px 0;
            }
            .intel-range-input::-webkit-slider-thumb {
              -webkit-appearance: none;
              appearance: none;
              width: 12px;
              height: 12px;
              border-radius: 50%;
              background: #8ab4f8;
              cursor: pointer;
              transition: transform 0.1s;
            }
            .intel-range-input::-webkit-slider-thumb:hover {
              transform: scale(1.2);
            }

            .intel-progress-container {
              display: flex;
              flex-direction: column;
              gap: 6px;
            }
            .intel-progress-header {
              display: flex;
              justify-content: space-between;
              font-size: 12px;
              color: #c4c7c5;
              line-height: 1.4;
            }
            .intel-progress-bar-bg {
              width: 100%;
              height: 6px;
              background: #2b2c30;
              border-radius: 3px;
              overflow: hidden;
            }
            .intel-progress-bar-fill {
              height: 100%;
              border-radius: 3px;
              transition: width 0.3s;
            }

            .intel-grid {
              display: grid;
              grid-template-columns: 1fr 1fr;
              gap: 10px;
            }
            .intel-grid-card {
              background: #131316;
              border: 1px solid rgba(255, 255, 255, 0.05);
              border-radius: 8px;
              padding: 10px 12px;
              display: flex;
              flex-direction: column;
              gap: 4px;
            }
            .intel-grid-card-label {
              font-size: 9px;
              font-weight: 600;
              text-transform: uppercase;
              color: #9aa0a6;
              letter-spacing: 0.5px;
            }
            .intel-grid-card-value {
              font-size: 13px;
              font-weight: 600;
              color: #ffffff;
            }

            .intel-check-list {
              display: flex;
              flex-direction: column;
              gap: 10px;
              font-size: 12px;
              color: #e3e3e3;
            }
            .intel-check-item {
              display: flex;
              align-items: center;
              gap: 10px;
            }
            .intel-check-icon {
              color: #34a853;
              flex-shrink: 0;
              display: flex;
              align-items: center;
            }
          `}</style>

          {/* Header Panel */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "16px",
              borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
              boxSizing: "border-box",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Brain size={16} style={{ color: "#8ab4f8" }} />
              <span style={{ fontWeight: 600, fontSize: 14, color: "#ffffff" }}>Intelligence Panel</span>
            </div>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setShowSidebar(false)}
              style={{
                padding: 6,
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#8e918f",
                cursor: "pointer",
                border: "none",
                background: "transparent",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255, 255, 255, 0.06)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {/* Scrollable Content Body */}
          <div style={{ padding: "20px 16px", display: "flex", flexDirection: "column", gap: 6 }}>
            
            {/* Section 1: Active Model & Parameters */}
            <div className="intel-section">
              <div className="intel-section-header">
                <Cpu size={12} />
                <span>Active Model & Parameters</span>
              </div>
              <div className="intel-card">
                <div className="intel-model-badge">
                  <div className="intel-status-dot" />
                  <span>{modelConfig.displayModel || "Claude 3.5 Sonnet (Moltress Hybrid)"}</span>
                </div>

                {/* Temperature Slider */}
                <div className="intel-slider-row">
                  <div className="intel-slider-header">
                    <span>Temperature</span>
                    <span className="intel-slider-value">{temperature.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="0.0"
                    max="2.0"
                    step="0.05"
                    value={temperature}
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    className="intel-range-input"
                  />
                </div>

                {/* Top P Slider */}
                <div className="intel-slider-row">
                  <div className="intel-slider-header">
                    <span>Top P</span>
                    <span className="intel-slider-value">{topP.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="0.0"
                    max="1.0"
                    step="0.05"
                    value={topP}
                    onChange={(e) => setTopP(parseFloat(e.target.value))}
                    className="intel-range-input"
                  />
                </div>
              </div>
            </div>

            {/* Section 2: Execution & Usage */}
            <div className="intel-section">
              <div className="intel-section-header">
                <Activity size={12} />
                <span>Execution & Usage</span>
              </div>
              <div className="intel-card">
                {/* Context Window */}
                <div className="intel-progress-container">
                  <div className="intel-progress-header">
                    <span>Context Window</span>
                    <span style={{ color: "#ffffff", fontWeight: 500 }}>21% (42,150 / 200k tokens)</span>
                  </div>
                  <div className="intel-progress-bar-bg">
                    <div
                      className="intel-progress-bar-fill"
                      style={{ width: "21%", background: "#8ab4f8" }}
                    />
                  </div>
                </div>

                {/* Grid Metrics */}
                <div className="intel-grid">
                  <div className="intel-grid-card">
                    <span className="intel-grid-card-label">Input Tokens</span>
                    <span className="intel-grid-card-value">32.4k</span>
                  </div>
                  <div className="intel-grid-card">
                    <span className="intel-grid-card-label">Output Tokens</span>
                    <span className="intel-grid-card-value">9.7k</span>
                  </div>
                  <div className="intel-grid-card">
                    <span className="intel-grid-card-label">First Token Latency</span>
                    <span className="intel-grid-card-value">180ms</span>
                  </div>
                  <div className="intel-grid-card">
                    <span className="intel-grid-card-label">Total Duration</span>
                    <span className="intel-grid-card-value">1.24s</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Section 3: Verification & Quality */}
            <div className="intel-section">
              <div className="intel-section-header">
                <Sparkles size={12} />
                <span>Verification & Quality</span>
              </div>
              <div className="intel-card">
                {/* Response Confidence */}
                <div className="intel-progress-container">
                  <div className="intel-progress-header">
                    <span>Response Confidence</span>
                    <span style={{ color: "#34a853", fontWeight: 600 }}>94%</span>
                  </div>
                  <div className="intel-progress-bar-bg">
                    <div
                      className="intel-progress-bar-fill"
                      style={{ width: "94%", background: "#34a853" }}
                    />
                  </div>
                </div>

                {/* Hallucination Risk */}
                <div className="intel-progress-container">
                  <div className="intel-progress-header">
                    <span>Hallucination Risk</span>
                    <span style={{ color: "#8ab4f8", fontWeight: 500 }}>Low (4%)</span>
                  </div>
                  <div className="intel-progress-bar-bg" style={{ height: 4 }}>
                    <div
                      className="intel-progress-bar-fill"
                      style={{ width: "4%", background: "#8ab4f8" }}
                    />
                  </div>
                </div>

                <div style={{ height: "1px", background: "rgba(255, 255, 255, 0.06)", margin: "4px 0" }} />

                {/* Autonomous Quality Checks list */}
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#8e918f", letterSpacing: 0.5 }}>
                  Autonomous Quality Checks
                </div>
                <div className="intel-check-list">
                  <div className="intel-check-item">
                    <div className="intel-check-icon">
                      <CheckCircle2 size={13} fill="#34a853" style={{ color: "#1e1f24" }} />
                    </div>
                    <span>Context Relevance Verified</span>
                  </div>
                  <div className="intel-check-item">
                    <div className="intel-check-icon">
                      <CheckCircle2 size={13} fill="#34a853" style={{ color: "#1e1f24" }} />
                    </div>
                    <span>Syntax Validity Confirmed</span>
                  </div>
                  <div className="intel-check-item">
                    <div className="intel-check-icon">
                      <CheckCircle2 size={13} fill="#34a853" style={{ color: "#1e1f24" }} />
                    </div>
                    <span>Privacy Audit Passed (No PII)</span>
                  </div>
                  <div className="intel-check-item">
                    <div className="intel-check-icon">
                      <CheckCircle2 size={13} fill="#34a853" style={{ color: "#1e1f24" }} />
                    </div>
                    <span>Security Vulnerabilities: None Found</span>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      )}
      {dragActive && (
        <div className="chat-drop-overlay" aria-hidden>
          <div className="chat-drop-overlay-inner">
            {t("chat.dropToAttach")}
          </div>
        </div>
      )}
      {/* Show follow-us modal only after setup is complete */}
      {active && connectionModeLoaded && readiness.ok && <FollowUsModal />}
    </div>
  );
}

export default Chat;
