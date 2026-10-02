import { Database, FileText, Image } from "lucide-react";
import { useI18n } from "../../components/useI18n";
import type { MemoryTab } from "./types";

interface MemoryTabsProps {
  activeTab: MemoryTab;
  onTabChange: (tab: MemoryTab) => void;
}

export function MemoryTabs({
  activeTab,
  onTabChange,
}: MemoryTabsProps): React.JSX.Element {
  const { t } = useI18n();

  const tabs: { id: MemoryTab; icon: typeof Database; label: string }[] = [
    { id: "entries", icon: Database, label: t("memory.agentMemory") },
    { id: "files", icon: FileText, label: "Files" },
    { id: "images", icon: Image, label: "Images" },
  ];

  return (
    <div className="memory-tabs">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        return (
          <button
            key={tab.id}
            className={`memory-tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => onTabChange(tab.id)}
          >
            <Icon size={14} />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
