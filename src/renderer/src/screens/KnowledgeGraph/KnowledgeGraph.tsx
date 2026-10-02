import { useState, useMemo, useEffect, useRef } from "react";
import {
  Plus,
  RotateCcw,
  Search,
  Share2,
  Info,
  Maximize2,
  Minimize2
} from "lucide-react";

interface GraphNode {
  id: string;
  label: string;
  type: "project" | "team" | "service" | "doc" | "repo" | "person";
  x: number;
  y: number;
  vx: number;
  vy: number;
  description: string;
  details: Record<string, string>;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

const DEFAULT_NODES: GraphNode[] = [
  {
    id: "platform-team",
    label: "Platform Team",
    type: "team",
    x: 230,
    y: 150,
    vx: 0,
    vy: 0,
    description: "Core Infrastructure & Tooling Team",
    details: {
      "Lead": "Bob Smith",
      "Members Count": "6 engineers",
      "Scope": "Deployment pipelines, Gateway routing, API contracts"
    }
  },
  {
    id: "alice-chen",
    label: "Alice Chen",
    type: "person",
    x: 150,
    y: 240,
    vx: 0,
    vy: 0,
    description: "Senior Infrastructure Engineer",
    details: {
      "Role": "Kubernetes Architect",
      "Department": "Platform Team",
      "Focus": "Authentication services, CI/CD optimizations"
    }
  },
  {
    id: "frontend-web",
    label: "frontend-web",
    type: "project",
    x: 230,
    y: 330,
    vx: 0,
    vy: 0,
    description: "React SPA UI Gateway client",
    details: {
      "Tech Stack": "React, Vite, TypeScript",
      "Repo URL": "github.com/org/frontend-web",
      "Deployment": "Cloudflare Pages"
    }
  },
  {
    id: "backend-api",
    label: "backend-api",
    type: "project",
    x: 480,
    y: 80,
    vx: 0,
    vy: 0,
    description: "Backend REST API gateway services",
    details: {
      "Tech Stack": "Node.js, Express, PostgreSQL",
      "Repo URL": "github.com/org/backend-api",
      "Cluster Uptime": "99.98%"
    }
  },
  {
    id: "auth-service",
    label: "auth-service",
    type: "service",
    x: 400,
    y: 240,
    vx: 0,
    vy: 0,
    description: "OAuth2 & JWT authentication service",
    details: {
      "Language": "Go 1.21",
      "Throughput": "12k req/sec",
      "Health": "Healthy (99.99% uptime)"
    }
  },
  {
    id: "data-pipeline",
    label: "data-pipeline",
    type: "service",
    x: 570,
    y: 150,
    vx: 0,
    vy: 0,
    description: "Apache Kafka event processing streaming pipeline",
    details: {
      "Framework": "Apache Spark / Scala",
      "Data Rate": "4.5 GB/min",
      "Destinations": "BigQuery, Snowflake"
    }
  },
  {
    id: "data-science",
    label: "Data Science",
    type: "team",
    x: 700,
    y: 240,
    vx: 0,
    vy: 0,
    description: "Machine Learning & Analytics Team",
    details: {
      "Lead": "Dr. Sarah Jenkins",
      "Core Tech": "Python, PyTorch, Jupyter",
      "Active Projects": "Churn prediction, recommendation engine"
    }
  },
  {
    id: "org-auth-service",
    label: "org/auth-service",
    type: "repo",
    x: 380,
    y: 390,
    vx: 0,
    vy: 0,
    description: "Monorepo for authentication middleware modules",
    details: {
      "VCS": "Git (GitHub)",
      "Main Branch": "main",
      "Vulnerabilities": "None (Dependabot clear)"
    }
  },
  {
    id: "architecture-pdf",
    label: "architecture.pdf",
    type: "doc",
    x: 570,
    y: 330,
    vx: 0,
    vy: 0,
    description: "Core authentication flow architectural document",
    details: {
      "Format": "Markdown / PDF",
      "Last Modified": "Last week",
      "Author": "Alice Chen"
    }
  }
];

const DEFAULT_EDGES: GraphEdge[] = [
  { id: "e1", source: "alice-chen", target: "platform-team", label: "member" },
  { id: "e2", source: "auth-service", target: "platform-team", label: "owned by" },
  { id: "e3", source: "frontend-web", target: "platform-team", label: "owned by" },
  { id: "e4", source: "auth-service", target: "data-pipeline", label: "feeds" },
  { id: "e5", source: "data-pipeline", target: "data-science", label: "owned by" },
  { id: "e6", source: "auth-service", target: "org-auth-service", label: "repo" },
  { id: "e7", source: "auth-service", target: "architecture-pdf", label: "documented in" },
  { id: "e8", source: "backend-api", target: "platform-team", label: "owned by" },
  { id: "e9", source: "auth-service", target: "backend-api", label: "authenticates" }
];

const TYPE_METADATA = {
  project: { color: "#3a86ff", label: "Project", dotColor: "#3a86ff" },
  team: { color: "#9b5de5", label: "Folder", dotColor: "#9b5de5" },
  service: { color: "#34a853", label: "Code File", dotColor: "#34a853" },
  doc: { color: "#ffb703", label: "Document", dotColor: "#ffb703" },
  repo: { color: "#9aa0a6", label: "Asset", dotColor: "#9aa0a6" },
  person: { color: "#f15bb5", label: "Other", dotColor: "#f15bb5" }
};

interface TreeViewItemProps {
  name: string;
  path: string;
  isDirectory: boolean;
  depth: number;
  onSelectNode: (id: string) => void;
  selectedId: string | null;
}

const TreeViewItem: React.FC<TreeViewItemProps> = ({
  name,
  path,
  isDirectory,
  depth,
  onSelectNode,
  selectedId
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [children, setChildren] = useState<{ name: string; isDirectory: boolean }[]>([]);
  const [loaded, setLoaded] = useState(false);

  const handleToggle = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!isDirectory) {
      onSelectNode(path);
      return;
    }

    if (!isOpen && !loaded) {
      try {
        const entries = await window.hermesAPI.readDirectory(path);
        if (entries) {
          const ignoredNames = [".git", "node_modules", ".DS_Store", "dist", "build", "out"];
          const filtered = entries
            .filter((entry) => !ignoredNames.includes(entry.name))
            .sort((a, b) => {
              if (a.isDirectory && !b.isDirectory) return -1;
              if (!a.isDirectory && b.isDirectory) return 1;
              return a.name.localeCompare(b.name);
            });
          setChildren(filtered);
          setLoaded(true);
        }
      } catch (err) {
        console.error("Failed to load sub-directory", err);
      }
    }
    setIsOpen(!isOpen);
    onSelectNode(path);
  };

  const isSelected = selectedId === path;

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div
        onClick={handleToggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 8px",
          paddingLeft: 8 + depth * 12,
          borderRadius: 4,
          cursor: "pointer",
          fontSize: 12,
          color: isSelected ? "#a8c7fa" : "#c4c7c5",
          background: isSelected ? "rgba(168, 199, 250, 0.08)" : "transparent",
          transition: "background 0.15s, color 0.15s"
        }}
        className="kg-tree-item"
      >
        {isDirectory ? (
          <span style={{ fontSize: 10, color: "#8e918f", display: "inline-block", width: 10, transform: isOpen ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}>
            ▶
          </span>
        ) : (
          <span style={{ width: 10 }} />
        )}
        <span style={{ color: isDirectory ? "#9b5de5" : "#ffb703", fontSize: 13 }}>
          {isDirectory ? "📁" : "📄"}
        </span>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {name}
        </span>
      </div>

      {isOpen && isDirectory && (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {loaded && children.length === 0 ? (
            <div style={{ padding: "4px 8px", paddingLeft: 24 + depth * 12, fontSize: 11, color: "#8e918f", fontStyle: "italic" }}>
              Empty folder
            </div>
          ) : (
            children.map((child) => (
              <TreeViewItem
                key={`${path}/${child.name}`}
                name={child.name}
                path={`${path}/${child.name}`}
                isDirectory={child.isDirectory}
                depth={depth + 1}
                onSelectNode={onSelectNode}
                selectedId={selectedId}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
};

interface KnowledgeGraphProps {
  visible: boolean;
}

export default function KnowledgeGraph({ visible }: KnowledgeGraphProps): React.JSX.Element | null {
  if (!visible) return null;

  const [nodes, setNodes] = useState<GraphNode[]>(DEFAULT_NODES);
  const [edges, setEdges] = useState<GraphEdge[]>(DEFAULT_EDGES);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>("auth-service");
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);

  // Zoom & Pan offset states
  const [zoom, setZoom] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0 });

  // Force Layout simulation settings
  const [physicsEnabled, setPhysicsEnabled] = useState(true);



  // Choose Project Selection State
  const [selectedProject, setSelectedProject] = useState<string>("all");
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());


  const visibleNodeIds = useMemo(() => {
    if (selectedProject === "all") return null;
    const visited = new Set<string>([selectedProject]);
    const queue = [selectedProject];

    while (queue.length > 0) {
      const curr = queue.shift()!;
      // Find all edges connected to curr
      edges.forEach((e) => {
        let neighbor: string | null = null;
        if (e.source === curr) neighbor = e.target;
        else if (e.target === curr) neighbor = e.source;

        if (neighbor && !visited.has(neighbor)) {
          const neighborNode = nodes.find((n) => n.id === neighbor);
          // If the neighbor is another project node, do not traverse
          if (neighborNode && neighborNode.type === "project" && neighborNode.id !== selectedProject) {
            // skip project bleed
          } else {
            visited.add(neighbor);
            queue.push(neighbor);
          }
        }
      });
    }
    return visited;
  }, [nodes, edges, selectedProject]);

  // Filters logic
  const filteredNodes = useMemo(() => {
    return nodes.filter((n) => {
      const matchesSearch = n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
        n.description.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesFilter = activeFilter === "all" || n.type === activeFilter;
      return matchesSearch && matchesFilter;
    });
  }, [nodes, searchQuery, activeFilter]);


  const connectedNodeIds = useMemo(() => {
    const activeId = hoveredNodeId || selectedNodeId;
    if (!activeId) return new Set<string>();
    const neighbors = new Set<string>([activeId]);
    edges.forEach((e) => {
      if (e.source === activeId) neighbors.add(e.target);
      if (e.target === activeId) neighbors.add(e.source);
    });
    return neighbors;
  }, [edges, selectedNodeId, hoveredNodeId]);

  // Running force directed physics layout solver
  useEffect(() => {
    if (!physicsEnabled || draggedNodeId) return;

    let timer: number;
    const runSimulation = () => {
      setNodes((prevNodes) => {
        // Create copies of positions to update
        const updated = prevNodes.map((n) => ({ ...n }));

        // 1. Repulsion forces between nodes
        const visibleNodes = updated.filter(n => visibleNodeIds === null || visibleNodeIds.has(n.id));
        for (let i = 0; i < visibleNodes.length; i++) {
          for (let j = i + 1; j < visibleNodes.length; j++) {
            const n1 = visibleNodes[i];
            const n2 = visibleNodes[j];
            const dx = n2.x - n1.x;
            const dy = n2.y - n1.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            if (dist < 150) {
              const force = (150 - dist) * 0.04;
              const fx = (dx / dist) * force;
              const fy = (dy / dist) * force;
              n1.vx -= fx;
              n1.vy -= fy;
              n2.vx += fx;
              n2.vy += fy;
            }
          }
        }

        // 2. Attraction spring forces along connections
        edges.forEach((e) => {
          if (visibleNodeIds !== null && (!visibleNodeIds.has(e.source) || !visibleNodeIds.has(e.target))) {
            return;
          }
          const sNode = updated.find((n) => n.id === e.source);
          const tNode = updated.find((n) => n.id === e.target);
          if (sNode && tNode) {
            const dx = tNode.x - sNode.x;
            const dy = tNode.y - sNode.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const springForce = (dist - 160) * 0.015;
            const fx = (dx / dist) * springForce;
            const fy = (dy / dist) * springForce;
            sNode.vx += fx;
            sNode.vy += fy;
            tNode.vx -= fx;
            tNode.vy -= fy;
          }
        });

        // 3. Center gravity pull (pulling everything slightly to center)
        const cx = 400;
        const cy = 250;
        updated.forEach((n) => {
          const dx = cx - n.x;
          const dy = cy - n.y;
          n.vx += dx * 0.003;
          n.vy += dy * 0.003;

          // Apply dampening viscosity
          n.vx *= 0.82;
          n.vy *= 0.82;

          // Update positions based on velocity
          n.x += n.vx;
          n.y += n.vy;

          // Constrain within visible viewport boundaries
          n.x = Math.max(50, Math.min(750, n.x));
          n.y = Math.max(50, Math.min(450, n.y));
        });

        return updated;
      });

      timer = requestAnimationFrame(runSimulation);
    };

    timer = requestAnimationFrame(runSimulation);
    return () => cancelAnimationFrame(timer);
  }, [physicsEnabled, edges, draggedNodeId, visibleNodeIds]);

  // Load workspace path on mount
  useEffect(() => {
    const wsPath = localStorage.getItem("hermes.workspace.folderPath");
    if (wsPath) {
      loadRootDirectory(wsPath);
    }
  }, []);

  const loadRootDirectory = async (dirPath: string) => {
    try {
      const entries = await window.hermesAPI.readDirectory(dirPath);
      if (!entries) return;

      const rootId = dirPath;
      const rootLabel = dirPath.split(/[\\/]/).pop() || dirPath;

      const rootNode: GraphNode = {
        id: rootId,
        label: rootLabel,
        type: "project",
        x: 400,
        y: 230,
        vx: 0,
        vy: 0,
        description: `Local project root folder: ${dirPath}`,
        details: {
          "Path": dirPath,
          "Entity Class": "Project Root",
          "Source": "Local Filesystem"
        }
      };

      const newNodes: GraphNode[] = [rootNode];
      const newEdges: GraphEdge[] = [];
      const ignoredNames = [".git", "node_modules", ".DS_Store", "dist", "build", "out"];

      entries.forEach((entry) => {
        if (ignoredNames.includes(entry.name)) return;

        const childId = `${dirPath}/${entry.name}`;
        
        let type: "team" | "service" | "doc" | "repo" | "person" = "doc";
        if (entry.isDirectory) {
          type = "team";
        } else {
          const ext = entry.name.split('.').pop()?.toLowerCase();
          if (["py", "js", "ts", "tsx", "cpp", "go", "java", "rs", "sh"].includes(ext || "")) {
            type = "service";
          } else if (["png", "jpg", "jpeg", "gif", "ico", "svg", "webp"].includes(ext || "")) {
            type = "repo";
          } else if (["pdf", "md", "txt", "csv", "json", "yaml", "yml"].includes(ext || "")) {
            type = "doc";
          }
        }

        const angle = Math.random() * Math.PI * 2;
        const radius = 120 + Math.random() * 50;
        const x = 400 + Math.cos(angle) * radius;
        const y = 230 + Math.sin(angle) * radius;

        newNodes.push({
          id: childId,
          label: entry.name,
          type,
          x,
          y,
          vx: 0,
          vy: 0,
          description: entry.isDirectory ? `Subfolder inside project.` : `File inside project.`,
          details: {
            "Path": childId,
            "Type": entry.isDirectory ? "Folder" : "File",
            "Extension": entry.isDirectory ? "None" : entry.name.split('.').pop() || "None"
          }
        });

        newEdges.push({
          id: `edge-${rootId}-${childId}`,
          source: rootId,
          target: childId,
          label: "contains"
        });
      });

      setNodes(newNodes);
      setEdges(newEdges);
      setSelectedProject(rootId);
      setSelectedNodeId(rootId);
      setExpandedNodeIds(new Set([rootId]));
    } catch (err) {
      console.error("Failed to load directory contents", err);
    }
  };

  const expandFolderNode = async (folderPath: string) => {
    if (expandedNodeIds.has(folderPath)) {
      setExpandedNodeIds((prev) => {
        const next = new Set(prev);
        next.delete(folderPath);
        return next;
      });

      setNodes((prev) => prev.filter((n) => n.id === folderPath || !n.id.startsWith(`${folderPath}/`)));
      setEdges((prev) => prev.filter((e) => !e.target.startsWith(`${folderPath}/`)));
      return;
    }

    try {
      const entries = await window.hermesAPI.readDirectory(folderPath);
      if (!entries) return;

      setExpandedNodeIds((prev) => {
        const next = new Set(prev);
        next.add(folderPath);
        return next;
      });

      const parentNode = nodes.find((n) => n.id === folderPath);
      const px = parentNode?.x || 400;
      const py = parentNode?.y || 230;

      const newNodes: GraphNode[] = [];
      const newEdges: GraphEdge[] = [];
      const ignoredNames = [".git", "node_modules", ".DS_Store", "dist", "build", "out"];

      entries.forEach((entry) => {
        if (ignoredNames.includes(entry.name)) return;

        const childId = `${folderPath}/${entry.name}`;
        if (nodes.some((n) => n.id === childId)) return;

        let type: "team" | "service" | "doc" | "repo" | "person" = "doc";
        if (entry.isDirectory) {
          type = "team";
        } else {
          const ext = entry.name.split('.').pop()?.toLowerCase();
          if (["py", "js", "ts", "tsx", "cpp", "go", "java", "rs", "sh"].includes(ext || "")) {
            type = "service";
          } else if (["png", "jpg", "jpeg", "gif", "ico", "svg", "webp"].includes(ext || "")) {
            type = "repo";
          } else if (["pdf", "md", "txt", "csv", "json", "yaml", "yml"].includes(ext || "")) {
            type = "doc";
          }
        }

        const angle = Math.random() * Math.PI * 2;
        const radius = 80 + Math.random() * 40;
        const x = px + Math.cos(angle) * radius;
        const y = py + Math.sin(angle) * radius;

        newNodes.push({
          id: childId,
          label: entry.name,
          type,
          x,
          y,
          vx: 0,
          vy: 0,
          description: entry.isDirectory ? `Subfolder inside project.` : `File inside project.`,
          details: {
            "Path": childId,
            "Type": entry.isDirectory ? "Folder" : "File",
            "Extension": entry.isDirectory ? "None" : entry.name.split('.').pop() || "None"
          }
        });

        newEdges.push({
          id: `edge-${folderPath}-${childId}`,
          source: folderPath,
          target: childId,
          label: "contains"
        });
      });

      setNodes((prev) => [...prev, ...newNodes]);
      setEdges((prev) => [...prev, ...newEdges]);
      setPhysicsEnabled(true);
    } catch (err) {
      console.error("Failed to expand folder", err);
    }
  };

  const handleReset = () => {
    const wsPath = localStorage.getItem("hermes.workspace.folderPath");
    if (wsPath) {
      loadRootDirectory(wsPath);
    }
    setSelectedNodeId(null);
    setSearchQuery("");
    setActiveFilter("all");
    setZoom(1);
    setPanOffset({ x: 0, y: 0 });
    setSelectedProject("all");
  };

  // Zoom helpers
  const zoomIn = () => setZoom((z) => Math.min(2.5, z + 0.15));
  const zoomOut = () => setZoom((z) => Math.max(0.4, z - 0.15));

  // Canvas Mouse events handling
  const handleCanvasMouseDown = (e: React.MouseEvent) => {
    setIsPanning(true);
    panStart.current = { x: e.clientX - panOffset.x, y: e.clientY - panOffset.y };
  };

  const handleCanvasMouseMove = (e: React.MouseEvent) => {
    if (isPanning) {
      setPanOffset({
        x: e.clientX - panStart.current.x,
        y: e.clientY - panStart.current.y
      });
    }
  };

  const handleCanvasMouseUp = () => {
    setIsPanning(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    const factor = e.deltaY < 0 ? 1.05 : 0.95;
    setZoom((z) => Math.max(0.4, Math.min(2.5, z * factor)));
  };

  const handleNodeMouseDown = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedNodeId(id);
    setDraggedNodeId(id);

    // If node is a project, select/filter by it!
    const nodeObj = nodes.find((n) => n.id === id);
    if (nodeObj && nodeObj.type === "project") {
      setSelectedProject(id);
    }
    // If node is a folder, expand it on click!
    if (nodeObj && nodeObj.type === "team") {
      expandFolderNode(id);
    }
  };

  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!draggedNodeId) return;
    const rect = e.currentTarget.getBoundingClientRect();
    // Invert zoom and pan offset transformations
    const rawX = e.clientX - rect.left - panOffset.x;
    const rawY = e.clientY - rect.top - panOffset.y;
    const x = Math.max(20, Math.min(1000, rawX / zoom));
    const y = Math.max(20, Math.min(800, rawY / zoom));

    setNodes((prev) =>
      prev.map((n) => (n.id === draggedNodeId ? { ...n, x, y, vx: 0, vy: 0 } : n))
    );
  };

  const handleSvgMouseUp = () => {
    setDraggedNodeId(null);
  };


  const handleChooseProjectFolder = async () => {
    try {
      const selectedPath = await window.hermesAPI.selectFolder();
      if (!selectedPath) return; // User cancelled

      await loadRootDirectory(selectedPath);
    } catch (err) {
      console.error("Failed to select folder", err);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        padding: "24px 32px",
        background: "#0c0c0e",
        color: "#ffffff",
        overflowY: "auto",
        height: "100%",
        boxSizing: "border-box"
      }}
    >
      {/* CSS Stylesheet */}
      <style>{`
        .kg-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 20px;
        }
        .kg-title-container h1 {
          font-size: 24px;
          font-weight: 700;
          margin: 0 0 4px 0;
          color: #ffffff;
        }
        .kg-subtitle {
          font-size: 13px;
          color: #8e918f;
          margin: 0;
        }
        .kg-header-actions {
          display: flex;
          gap: 12px;
        }
        .kg-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          background: #17181d;
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #ffffff;
          padding: 8px 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
        }
        .kg-btn:hover {
          background: #23242b;
          border-color: rgba(255, 255, 255, 0.15);
        }
        .kg-btn-primary {
          background: rgba(168, 199, 250, 0.1);
          border-color: rgba(168, 199, 250, 0.25);
          color: #a8c7fa;
        }
        .kg-btn-primary:hover {
          background: rgba(168, 199, 250, 0.18);
        }
        .kg-toolbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          flex-wrap: wrap;
          gap: 12px;
        }
        .kg-search {
          display: flex;
          align-items: center;
          gap: 8px;
          background: #131316;
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          padding: 6px 12px;
          width: 240px;
        }
        .kg-search input {
          background: transparent;
          border: none;
          outline: none;
          color: #ffffff;
          font-size: 13px;
          width: 100%;
        }
        .kg-project-select {
          display: flex;
          align-items: center;
          gap: 6px;
          background: #131316;
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 8px;
          padding: 6px 12px;
        }
        .kg-project-select select {
          background: transparent;
          border: none;
          outline: none;
          color: #ffffff;
          font-size: 13px;
          cursor: pointer;
        }
        .kg-legend {
          display: flex;
          align-items: center;
          gap: 14px;
          flex-wrap: wrap;
        }
        .kg-legend-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: #8e918f;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 4px;
          transition: all 0.15s;
        }
        .kg-legend-item:hover {
          color: #ffffff;
          background: rgba(255, 255, 255, 0.03);
        }
        .kg-legend-item.active {
          color: #ffffff;
          font-weight: 500;
          background: rgba(255, 255, 255, 0.06);
        }
        .kg-legend-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .kg-workspace {
          display: grid;
          grid-template-columns: 1fr 310px;
          gap: 20px;
          height: calc(100vh - 200px);
          min-height: 500px;
        }
        .kg-canvas-card {
          position: relative;
          background: #0f0f11;
          border: 1px solid rgba(255, 255, 255, 0.04);
          border-radius: 16px;
          overflow: hidden;
          cursor: grab;
        }
        .kg-canvas-card:active {
          cursor: grabbing;
        }
        .kg-floating-controls {
          position: absolute;
          top: 16px;
          left: 16px;
          display: flex;
          gap: 6px;
          z-index: 10;
        }
        .kg-float-btn {
          width: 32px;
          height: 32px;
          background: rgba(30, 30, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #e3e3e3;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.2s;
        }
        .kg-float-btn:hover {
          background: rgba(45, 45, 50, 0.95);
          border-color: rgba(255, 255, 255, 0.15);
          color: #ffffff;
        }
        .kg-float-btn.active {
          background: rgba(168, 199, 250, 0.15);
          border-color: rgba(168, 199, 250, 0.3);
          color: #a8c7fa;
        }
        .kg-zoom-badge {
          position: absolute;
          bottom: 16px;
          right: 16px;
          background: rgba(24, 24, 28, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          padding: 5px 9px;
          border-radius: 6px;
          font-size: 11px;
          font-family: monospace;
          color: #8e918f;
        }
        .kg-sidebar {
          background: #131316;
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 16px;
          overflow-y: auto;
        }
        .kg-node-inspector {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.04);
          border-radius: 12px;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .kg-inspector-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .kg-inspector-title {
          font-size: 15px;
          font-weight: 600;
          color: #ffffff;
        }
        .kg-inspector-badge {
          font-size: 10px;
          font-weight: 700;
          text-transform: uppercase;
          padding: 2px 6px;
          border-radius: 4px;
          letter-spacing: 0.5px;
        }
        .kg-inspector-desc {
          font-size: 12px;
          color: #8e918f;
          line-height: 1.4;
        }
        .kg-inspector-kv {
          border-top: 1px solid rgba(255, 255, 255, 0.06);
          padding-top: 12px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          font-size: 12px;
        }
        .kg-inspector-row {
          display: flex;
          justify-content: space-between;
        }
        .kg-inspector-label {
          color: #8e918f;
        }
        .kg-inspector-val {
          color: #ffffff;
          font-weight: 500;
          text-align: right;
        }
        .kg-inspector-section-label {
          font-size: 11px;
          text-transform: uppercase;
          font-weight: 600;
          color: #8e918f;
          letter-spacing: 0.5px;
          margin-top: 14px;
          display: block;
          border-top: 1px solid rgba(255, 255, 255, 0.06);
          padding-top: 12px;
        }
        .kg-relation-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 11px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.04);
          border-radius: 6px;
          padding: 8px 10px;
          color: #ffffff;
        }
        .kg-relation-item span.dir {
          color: #8e918f;
          font-size: 9px;
          text-transform: uppercase;
        }
        .kg-relation-item strong.label {
          color: #a8c7fa;
          font-weight: 500;
        }
        .kg-relation-item span.node {
          color: #e3e3e3;
        }
        .kg-relation-delete-btn {
          border: none;
          background: transparent;
          color: rgba(255,255,255,0.25);
          cursor: pointer;
          transition: color 0.15s;
          padding: 2px;
          display: flex;
          align-items: center;
        }
        .kg-relation-delete-btn:hover {
          color: #ef4444;
        }

        /* SVG styles */
        .svg-link {
          stroke: rgba(255, 255, 255, 0.06);
          stroke-width: 1.5;
          transition: stroke 0.3s, stroke-width 0.3s;
        }
        .svg-link.highlighted {
          stroke: rgba(168, 199, 250, 0.4);
          stroke-width: 2;
          stroke-dasharray: 6 4;
          animation: kgDash 1.2s linear infinite;
        }
        @keyframes kgDash {
          to {
            stroke-dashoffset: -20;
          }
        }
        .svg-link-text {
          font-size: 9px;
          fill: #8e918f;
          text-anchor: middle;
          paint-order: stroke;
          stroke: #0f0f11;
          stroke-width: 3px;
          stroke-linejoin: round;
        }
        .svg-link-text.highlighted {
          fill: #a8c7fa;
          font-weight: 500;
        }
        .svg-node {
          cursor: pointer;
        }
        .svg-node-ring {
          fill: none;
          stroke-width: 1.2px;
          transition: stroke-width 0.2s, stroke-opacity 0.2s;
        }
        .svg-node:hover .svg-node-ring {
          stroke-width: 1.5px;
          filter: drop-shadow(0 0 8px var(--glow-color));
        }
        .svg-node-center-dot {
          /* Stable central dot */
        }
        .svg-node-text {
          font-size: 11px;
          fill: #a8b2c1;
          text-anchor: middle;
          transition: fill 0.2s, font-weight 0.2s;
          pointer-events: none;
        }
        .svg-node:hover .svg-node-text {
          fill: #ffffff;
          font-weight: 500;
        }
        .svg-node.selected .svg-node-text {
          fill: #ffffff;
          font-weight: 600;
        }

        /* Modal Overlay */
        .kg-modal-overlay {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0, 0, 0, 0.6);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          backdrop-filter: blur(4px);
        }
        .kg-modal {
          background: #1c1d22;
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          width: 400px;
          max-width: 90%;
          padding: 24px;
          box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .kg-modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .kg-modal-header h2 {
          font-size: 16px;
          font-weight: 600;
          margin: 0;
        }
        .kg-modal-close {
          background: transparent;
          border: none;
          color: #8e918f;
          cursor: pointer;
        }
        .kg-form-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .kg-form-group label {
          font-size: 12px;
          color: #c4c7c5;
          font-weight: 500;
        }
        .kg-form-group input, .kg-form-group select, .kg-form-group textarea {
          background: #131316;
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 6px;
          color: #ffffff;
          padding: 8px 12px;
          font-size: 13px;
          outline: none;
        }
        .kg-form-group input:focus, .kg-form-group select:focus, .kg-form-group textarea:focus {
          border-color: rgba(168, 199, 250, 0.4);
        }
      `}</style>

      {/* Header Info */}
      <div className="kg-header">
        <div className="kg-title-container">
          <h1>Knowledge Graph</h1>
          <p className="kg-subtitle">Visualize relationships between projects, teams, services, and documents</p>
        </div>
        <div className="kg-header-actions">
          <button className="kg-btn" onClick={handleChooseProjectFolder}>
            <Plus size={14} />
            <span>Select Folder</span>
          </button>
          <button className="kg-btn" onClick={handleReset}>
            <RotateCcw size={14} />
            <span>Reset View</span>
          </button>
        </div>
      </div>

      {/* Toolbar & Filters */}
      <div className="kg-toolbar">
        {/* Search */}
        <div className="kg-search">
          <Search size={13} style={{ color: "#8e918f" }} />
          <input
            placeholder="Filter nodes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Legend / Category Toggles */}
        <div className="kg-legend">
          <div
            className={`kg-legend-item ${activeFilter === "all" ? "active" : ""}`}
            onClick={() => setActiveFilter("all")}
          >
            <div className="kg-legend-dot" style={{ background: "#ffffff" }} />
            <span>All Types</span>
          </div>
          {Object.entries(TYPE_METADATA).map(([key, meta]) => (
            <div
              key={key}
              className={`kg-legend-item ${activeFilter === key ? "active" : ""}`}
              onClick={() => setActiveFilter(key)}
            >
              <div className="kg-legend-dot" style={{ background: meta.dotColor }} />
              <span>{meta.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Workspace Panel */}
      <div className="kg-workspace">
        {/* Canvas Card */}
        <div
          className="kg-canvas-card"
          onMouseDown={handleCanvasMouseDown}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={handleCanvasMouseUp}
          onMouseLeave={handleCanvasMouseUp}
          onWheel={handleWheel}
        >
          {/* Floating Controls Overlay */}
          <div className="kg-floating-controls">
            <button className="kg-float-btn" onClick={zoomIn} title="Zoom In">
              <Maximize2 size={13} />
            </button>
            <button className="kg-float-btn" onClick={zoomOut} title="Zoom Out">
              <Minimize2 size={13} />
            </button>
            <button
              className={`kg-float-btn ${physicsEnabled ? "active" : ""}`}
              onClick={() => setPhysicsEnabled(!physicsEnabled)}
              title={physicsEnabled ? "Pause Physics Simulation" : "Resume Physics Simulation"}
            >
              <RotateCcw size={13} style={{ animation: physicsEnabled ? "spin 12s linear infinite" : "none" }} />
            </button>
          </div>

          <svg
            width="100%"
            height="100%"
            style={{ display: "block" }}
            onMouseMove={handleSvgMouseMove}
            onMouseUp={handleSvgMouseUp}
            onMouseDown={() => {
              setSelectedNodeId(null);
              setSelectedProject("all");
            }}
          >
            {/* Grid Pattern definition */}
            <defs>
              <pattern id="kg-grid" width="35" height="35" patternUnits="userSpaceOnUse">
                <circle cx="2" cy="2" r="1" fill="rgba(255, 255, 255, 0.05)" />
              </pattern>
              <marker
                id="kg-arrowhead-default"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255, 255, 255, 0.28)" />
              </marker>
              <marker
                id="kg-arrowhead-project"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#3a86ff" />
              </marker>
              <marker
                id="kg-arrowhead-team"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#9b5de5" />
              </marker>
              <marker
                id="kg-arrowhead-service"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#34a853" />
              </marker>
              <marker
                id="kg-arrowhead-doc"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#ffb703" />
              </marker>
              <marker
                id="kg-arrowhead-repo"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa0a6" />
              </marker>
              <marker
                id="kg-arrowhead-person"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#f15bb5" />
              </marker>
            </defs>

            {/* Transform Group (Zoom and Pan) */}
            <g transform={`translate(${panOffset.x}, ${panOffset.y}) scale(${zoom})`}>
              {/* Pattern Grid Fill inside transformed group */}
              <rect x="-2000" y="-2000" width="4000" height="4000" fill="url(#kg-grid)" />

              {/* Edges */}
              {edges.map((e) => {
                const src = nodes.find((n) => n.id === e.source);
                const tgt = nodes.find((n) => n.id === e.target);
                if (!src || !tgt) return null;

                // Hide edges that do not belong to the active project sub-graph
                if (visibleNodeIds !== null && (!visibleNodeIds.has(e.source) || !visibleNodeIds.has(e.target))) {
                  return null;
                }

                const isHighlighted = connectedNodeIds.has(e.source) && connectedNodeIds.has(e.target);
                const isSearching = searchQuery.length > 0;
                const belongsToFiltered =
                  filteredNodes.some((n) => n.id === e.source) && filteredNodes.some((n) => n.id === e.target);

                let lineOpacity = isHighlighted ? 0.95 : 0.45;
                if (isSearching) {
                  lineOpacity = belongsToFiltered ? 0.6 : 0.05;
                } else if (activeFilter !== "all") {
                  const srcNode = nodes.find(n => n.id === e.source);
                  const tgtNode = nodes.find(n => n.id === e.target);
                  if (srcNode?.type !== activeFilter || tgtNode?.type !== activeFilter) {
                    lineOpacity = 0.08;
                  }
                }

                // Mathematics calculation to offset lines to touch circle boundaries perfectly
                const dx = tgt.x - src.x;
                const dy = tgt.y - src.y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                const radiusOffset = 22; // aligns to edge of node circles
                const x1 = src.x + (dx / dist) * radiusOffset;
                const y1 = src.y + (dy / dist) * radiusOffset;
                const x2 = tgt.x - (dx / dist) * radiusOffset;
                const y2 = tgt.y - (dy / dist) * radiusOffset;

                const midX = (src.x + tgt.x) / 2;
                const midY = (src.y + tgt.y) / 2;

                const targetMeta = TYPE_METADATA[tgt.type];

                return (
                  <g key={e.id} style={{ opacity: lineOpacity }}>
                    <line
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      className={`svg-link ${isHighlighted ? "highlighted" : ""}`}
                      style={{
                        stroke: isHighlighted ? targetMeta.color : "rgba(255, 255, 255, 0.22)",
                        strokeWidth: isHighlighted ? 2.2 : 1.2
                      }}
                      markerEnd={`url(#${isHighlighted ? `kg-arrowhead-${tgt.type}` : "kg-arrowhead-default"})`}
                    />
                    <text
                      x={midX}
                      y={midY - 5}
                      className={`svg-link-text ${isHighlighted ? "highlighted" : ""}`}
                      style={isHighlighted ? { fill: targetMeta.color, fontWeight: 600 } : undefined}
                    >
                      {e.label}
                    </text>
                  </g>
                );
              })}

              {/* Nodes */}
              {nodes.map((n) => {
                const meta = TYPE_METADATA[n.type];
                const isSelected = n.id === selectedNodeId;
                const isHovered = n.id === hoveredNodeId;

                // Hide nodes that do not belong to the active project sub-graph
                if (visibleNodeIds !== null && !visibleNodeIds.has(n.id)) {
                  return null;
                }

                const isSearchResult = searchQuery.length > 0 &&
                  (n.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
                    n.description.toLowerCase().includes(searchQuery.toLowerCase()));

                const passesFilter = activeFilter === "all" || n.type === activeFilter;
                const isSearching = searchQuery.length > 0;

                let opacity = 1.0;
                if (isSearching) {
                  opacity = isSearchResult ? 1.0 : 0.15;
                } else if (!passesFilter) {
                  opacity = 0.2;
                }

                return (
                  <g
                    key={n.id}
                    className={`svg-node ${isSelected ? "selected" : ""}`}
                    onMouseDown={(e) => handleNodeMouseDown(n.id, e)}
                    onMouseEnter={() => setHoveredNodeId(n.id)}
                    onMouseLeave={() => setHoveredNodeId(null)}
                    style={{
                      opacity,
                      transition: "opacity 0.2s",
                      "--glow-color": meta.color
                    } as React.CSSProperties}
                  >
                    {/* Glowing outer aura halo circle */}
                    <circle
                      cx={n.x}
                      cy={n.y}
                      r={24}
                      fill="transparent"
                      stroke={`${meta.color}25`}
                      strokeWidth={1.5}
                      style={{ transition: "stroke 0.2s" }}
                    />

                    {/* Ring Circle (Node bounds) */}
                    <circle
                      cx={n.x}
                      cy={n.y}
                      r={18}
                      stroke={isSelected ? "#ffffff" : meta.color}
                      className="svg-node-ring"
                      fill="#0d0d0f"
                    />

                    {/* Rotated Diamond / Dot Center */}
                    <rect
                      x={n.x - 4}
                      y={n.y - 4}
                      width={8}
                      height={8}
                      fill={meta.dotColor}
                      transform={`rotate(45 ${n.x} ${n.y})`}
                      className="svg-node-center-dot"
                    />

                    {/* Floating label */}
                    <text
                      x={n.x}
                      y={n.y + 32}
                      className="svg-node-text"
                      style={{
                        fill: isSelected ? "#ffffff" : isHovered ? "#ffffff" : "#a8b2c1"
                      }}
                    >
                      {n.label}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>

          {/* Zoom Badge */}
          <div className="kg-zoom-badge">{Math.round(zoom * 100)}%</div>
        </div>

        {/* Sidebar Inspector Panel */}
        <div className="kg-sidebar">
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "#8e918f",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              display: "flex",
              alignItems: "center",
              gap: 6,
              marginBottom: 14
            }}
          >
            <Share2 size={13} style={{ color: "#a8c7fa" }} />
            <span>Directory Tree</span>
          </div>

          {selectedProject !== "all" ? (
            <div
              style={{
                flex: 1,
                overflowY: "auto",
                background: "#111113",
                border: "1px solid rgba(255,255,255,0.03)",
                borderRadius: 8,
                padding: 12,
                display: "flex",
                flexDirection: "column",
                gap: 2
              }}
            >
              <TreeViewItem
                name={selectedProject.split(/[\\/]/).pop() || selectedProject}
                path={selectedProject}
                isDirectory={true}
                depth={0}
                onSelectNode={(id) => {
                  setSelectedNodeId(id);
                }}
                selectedId={selectedNodeId}
              />
            </div>
          ) : (
            <div
              style={{
                background: "rgba(255,255,255,0.01)",
                border: "1px dashed rgba(255,255,255,0.05)",
                borderRadius: 12,
                padding: 24,
                textAlign: "center",
                color: "#8e918f",
                fontSize: 12,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 8,
                marginTop: 20
              }}
            >
              <Info size={18} />
              <span>Select or load a project folder to view its directory tree explorer.</span>
            </div>
          )}
        </div>
      </div>

      {/* Add Node Modal Overlay */}
    </div>
  );
}
