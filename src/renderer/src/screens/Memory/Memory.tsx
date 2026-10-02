import { useState, useEffect, useCallback } from "react";
import { Refresh } from "../../assets/icons";
import { useI18n } from "../../components/useI18n";
import { CapacityCards } from "./CapacityCards";
import { MemoryTabs } from "./MemoryTabs";
import { MemoryEntries } from "./MemoryEntries";
import { MemoryFiles } from "./MemoryFiles";
import { MemoryImages } from "./MemoryImages";
import type { MemoryData, MemoryTab } from "./types";

function Memory({ profile }: { profile?: string }): React.JSX.Element {
  const { t } = useI18n();
  const [data, setData] = useState<MemoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<MemoryTab>("entries");
  const [error] = useState("");

  const loadData = useCallback(async () => {
    const d = await window.hermesAPI.readMemory(profile);
    setData(d as MemoryData);
    setLoading(false);
  }, [profile]);

  useEffect(() => {
    setLoading(true);
    loadData();
  }, [loadData]);

  if (loading || !data) {
    return (
      <div className="settings-container">
        <h1 className="settings-header">{t("memory.title")}</h1>
        <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
          <div className="loading-spinner" />
        </div>
      </div>
    );
  }

  return (
    <div className="settings-container">
      <div className="memory-header">
        <div>
          <h1 className="settings-header" style={{ marginBottom: 4 }}>
            {t("memory.title")}
          </h1>
          <p className="memory-subtitle">{t("memory.subtitle")}</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={loadData}>
          <Refresh size={13} />
        </button>
      </div>

      <CapacityCards data={data} />
      <MemoryTabs activeTab={tab} onTabChange={setTab} />

      {error && <div className="memory-error">{error}</div>}

      {tab === "entries" && (
        <MemoryEntries
          entries={data.memory.entries}
          profile={profile}
          onRefresh={loadData}
        />
      )}

      {tab === "files" && <MemoryFiles profile={profile} />}

      {tab === "images" && <MemoryImages profile={profile} />}
    </div>
  );
}

export default Memory;
