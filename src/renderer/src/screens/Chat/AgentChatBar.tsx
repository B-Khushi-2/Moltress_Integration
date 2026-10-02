import { useState, useEffect, useCallback, useRef } from "react";
import { ChevronDown, Check, Sparkles } from "lucide-react";
import ProfileAvatar from "../../components/common/ProfileAvatar";

interface ProfileInfo {
  name: string;
  isDefault: boolean;
  isActive: boolean;
  model: string;
  provider: string;
  color?: string;
  avatar?: string | null;
}

const ARCH_AGENTS_MAP: Record<string, { tag: string; label: string; desc: string }> = {
  "developer-agent": { tag: "ORC-3", label: "Developer Agent", desc: "Full-stack code & feature engineering" },
  "debug-agent": { tag: "ORC-4", label: "Debug Agent", desc: "Root cause analysis & stack trace inspection" },
  "security-agent": { tag: "ORC-5", label: "Security Agent", desc: "Security auditing & access control validation" },
  "documentation-agent": { tag: "ORC-6", label: "Documentation Agent", desc: "Technical documentation & API specs" },
  "data-analyst-agent": { tag: "ORC-7", label: "Data Analyst Agent", desc: "Data processing & query optimization" },
};

interface AgentChatBarProps {
  profile?: string;
  onSelectAgent?: (name: string) => void;
}

export function AgentChatBar({
  profile = "default",
  onSelectAgent,
}: AgentChatBarProps): React.JSX.Element {
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const loadProfiles = useCallback(async () => {
    try {
      const list = await window.hermesAPI.listProfiles();
      setProfiles(list);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles, profile]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const activeInfo = profiles.find((p) => p.name === profile);
  const arch = ARCH_AGENTS_MAP[profile];
  const activeLabel = arch ? arch.label : profile === "default" ? "Default Agent" : profile;
  const activeTag = arch ? arch.tag : profile === "default" ? "BASE" : "CUSTOM";

  const handleSwitch = async (name: string) => {
    setOpen(false);
    if (name === profile) return;
    try {
      await window.hermesAPI.setActiveProfile(name);
    } catch {
      /* optimistic update fallback */
    }
    onSelectAgent?.(name);
  };

  return (
    <div
      ref={dropdownRef}
      style={{
        position: "relative",
        padding: "8px 16px",
        background: "var(--bg-elevated, rgba(255, 255, 255, 0.03))",
        borderBottom: "1px solid var(--border-bright, rgba(255, 255, 255, 0.08))",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: 13,
        zIndex: 20,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: "var(--bg-subtle, rgba(255, 255, 255, 0.06))",
            border: "1px solid var(--border-bright, rgba(255, 255, 255, 0.12))",
            borderRadius: 6,
            padding: "5px 10px",
            color: "var(--text-primary, #fff)",
            cursor: "pointer",
            fontWeight: 500,
            transition: "all 0.15s ease",
          }}
        >
          <ProfileAvatar
            name={profile}
            color={activeInfo?.color}
            avatar={activeInfo?.avatar}
            size={18}
          />
          <span>{activeLabel}</span>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: "1px 5px",
              borderRadius: 4,
              background: "var(--accent-color, #4f46e5)",
              color: "#fff",
            }}
          >
            {activeTag}
          </span>
          <ChevronDown size={14} style={{ opacity: 0.7 }} />
        </button>

        {arch && (
          <span style={{ fontSize: 12, opacity: 0.6, display: "inline-block" }}>
            — {arch.desc}
          </span>
        )}
      </div>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 16,
            marginTop: 4,
            width: 320,
            background: "var(--bg-elevated, #1e1e24)",
            border: "1px solid var(--border-bright, rgba(255, 255, 255, 0.15))",
            borderRadius: 8,
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
            overflow: "hidden",
            zIndex: 100,
          }}
        >
          <div
            style={{
              padding: "8px 12px",
              fontSize: 11,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              opacity: 0.6,
              borderBottom: "1px solid var(--border-bright, rgba(255, 255, 255, 0.08))",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <Sparkles size={12} />
            <span>Select Active Agent</span>
          </div>

          <div style={{ maxHeight: 280, overflowY: "auto", padding: 4 }}>
            {profiles.map((p) => {
              const a = ARCH_AGENTS_MAP[p.name];
              const label = a ? a.label : p.name === "default" ? "Default Agent" : p.name;
              const tag = a ? a.tag : p.name === "default" ? "BASE" : "CUSTOM";
              const isSelected = p.name === profile;

              return (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => handleSwitch(p.name)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 10px",
                    borderRadius: 6,
                    border: "none",
                    background: isSelected
                      ? "var(--bg-selected, rgba(79, 70, 229, 0.15))"
                      : "transparent",
                    color: "var(--text-primary, #fff)",
                    cursor: "pointer",
                    textAlign: "left",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <ProfileAvatar
                      name={p.name}
                      color={p.color}
                      avatar={p.avatar}
                      size={24}
                    />
                    <div>
                      <div style={{ fontWeight: 500, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
                        <span>{label}</span>
                        <span
                          style={{
                            fontSize: 9,
                            fontWeight: 600,
                            padding: "1px 4px",
                            borderRadius: 3,
                            background: isSelected
                              ? "var(--accent-color, #4f46e5)"
                              : "rgba(255, 255, 255, 0.15)",
                            color: "#fff",
                          }}
                        >
                          {tag}
                        </span>
                      </div>
                      {a && (
                        <div style={{ fontSize: 11, opacity: 0.5, marginTop: 1 }}>
                          {a.desc}
                        </div>
                      )}
                    </div>
                  </div>

                  {isSelected && (
                    <Check size={14} style={{ color: "var(--accent-color, #4f46e5)" }} />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
