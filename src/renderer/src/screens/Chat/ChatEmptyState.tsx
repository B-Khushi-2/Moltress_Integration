import { memo } from "react";
import { Code, Bug, ShieldCheck, FileText, BarChart3 } from "lucide-react";
import titleLine from "../../assets/title-line.svg";
import { useI18n } from "../../components/useI18n";

interface AgentChip {
  id: string;
  name: string;
  profileName: string;
  Icon: typeof Code;
  promptText: string;
}

const ARCH_AGENT_CHIPS: AgentChip[] = [
  {
    id: "dev",
    name: "Developer Agent",
    profileName: "developer-agent",
    Icon: Code,
    promptText: "Switch to Developer Agent for code engineering",
  },
  {
    id: "debug",
    name: "Debug Agent",
    profileName: "debug-agent",
    Icon: Bug,
    promptText: "Switch to Debug Agent for log diagnosis",
  },
  {
    id: "sec",
    name: "Security Agent",
    profileName: "security-agent",
    Icon: ShieldCheck,
    promptText: "Switch to Security Agent for vulnerability auditing",
  },
  {
    id: "doc",
    name: "Documentation Agent",
    profileName: "documentation-agent",
    Icon: FileText,
    promptText: "Switch to Documentation Agent for documentation",
  },
  {
    id: "data",
    name: "Data Analyst Agent",
    profileName: "data-analyst-agent",
    Icon: BarChart3,
    promptText: "Switch to Data Analyst Agent for data processing",
  },
];

interface ChatEmptyStateProps {
  onSelectSuggestion: (text: string) => void;
  profile?: string;
  onSelectAgent?: (profileName: string) => void;
}

const ARCH_MAP: Record<string, string> = {
  "developer-agent": "Developer Agent",
  "debug-agent": "Debug Agent",
  "security-agent": "Security Agent",
  "documentation-agent": "Documentation Agent",
  "data-analyst-agent": "Data Analyst Agent",
};

export const ChatEmptyState = memo(function ChatEmptyState({
  onSelectSuggestion,
  profile = "default",
  onSelectAgent,
}: ChatEmptyStateProps): React.JSX.Element {
  const { t } = useI18n();

  const agentName = ARCH_MAP[profile] || (profile === "default" ? "Default Agent" : profile);

  const handleAgentClick = async (chip: AgentChip) => {
    try {
      await window.hermesAPI.setActiveProfile(chip.profileName);
    } catch {
      /* fallback */
    }
    if (onSelectAgent) {
      onSelectAgent(chip.profileName);
    } else {
      onSelectSuggestion(chip.promptText);
    }
  };

  return (
    <div className="chat-empty">
      <div className="chat-empty-icon">
        <span
          className="chat-empty-logo"
          role="img"
          aria-label="Hermes"
          style={{
            maskImage: `url(${titleLine})`,
            WebkitMaskImage: `url(${titleLine})`,
          }}
        />
      </div>

      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          marginBottom: 12,
          padding: "4px 12px",
          borderRadius: 20,
          background: "var(--bg-elevated, rgba(255, 255, 255, 0.06))",
          border: "1px solid var(--border-bright, rgba(255, 255, 255, 0.12))",
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary, #fff)" }}>
          {agentName}
        </span>
      </div>

      <div className="chat-empty-text">{t("chat.emptyTitle")}</div>
      <div className="chat-empty-hint">{t("chat.emptyHint")}</div>
      <div className="chat-empty-suggestions" style={{ gap: 10, maxWidth: 640 }}>
        {ARCH_AGENT_CHIPS.map((chip) => {
          const Icon = chip.Icon;
          const isActive = profile === chip.profileName;
          return (
            <button
              key={chip.id}
              className={`chat-suggestion ${isActive ? "active" : ""}`}
              onClick={() => handleAgentClick(chip)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 14px",
                borderRadius: 20,
                border: isActive
                  ? "1px solid var(--accent-color, #4f46e5)"
                  : "1px solid var(--border-bright, rgba(255, 255, 255, 0.15))",
                background: isActive
                  ? "var(--bg-selected, rgba(79, 70, 229, 0.15))"
                  : "var(--bg-elevated, rgba(255, 255, 255, 0.04))",
              }}
            >
              <Icon size={16} />
              <span>{chip.name}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
});
