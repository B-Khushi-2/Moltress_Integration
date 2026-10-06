import { useState, useEffect, useCallback } from "react";
import { Image as ImageIcon, Upload, Trash2, Search, X } from "lucide-react";

interface MemoryImageItem {
  id: string;
  name: string;
  dataUrl: string;
  size: number;
  createdAt: number;
}

export function MemoryImages({
  profile,
}: {
  profile?: string;
}): React.JSX.Element {
  const [images, setImages] = useState<MemoryImageItem[]>([]);
  const [search, setSearch] = useState("");
  const [selectedImage, setSelectedImage] = useState<MemoryImageItem | null>(null);

  const loadImages = useCallback(() => {
    try {
      const storageKey = `hermes.memory.images.${profile || "default"}`;
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        setImages(JSON.parse(saved));
      } else {
        setImages([]);
      }
    } catch {
      // Fallback
    }
  }, [profile]);

  useEffect(() => {
    loadImages();
  }, [loadImages]);

  const saveImages = (updated: MemoryImageItem[]) => {
    setImages(updated);
    const storageKey = `hermes.memory.images.${profile || "default"}`;
    try {
      localStorage.setItem(storageKey, JSON.stringify(updated));
    } catch (err) {
      console.warn("Storage quota exceeded for images:", err);
    }
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const uploaded = e.target.files;
    if (!uploaded || uploaded.length === 0) return;
    const fileList = Array.from(uploaded);

    fileList.forEach((file) => {
      if (!file.type.startsWith("image/")) return;
      const reader = new FileReader();
      reader.onload = (event) => {
        const dataUrl = event.target?.result as string;
        if (!dataUrl) return;
        const newImg: MemoryImageItem = {
          id: `img-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
          name: file.name,
          dataUrl,
          size: file.size,
          createdAt: Date.now(),
        };
        setImages((prev) => {
          const next = [newImg, ...prev];
          const storageKey = `hermes.memory.images.${profile || "default"}`;
          try {
            localStorage.setItem(storageKey, JSON.stringify(next));
          } catch {
            /* ignore storage quota error */
          }
          return next;
        });
      };
      reader.readAsDataURL(file);
    });
    e.target.value = "";
  };

  const handleDeleteImage = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const filtered = images.filter((img) => img.id !== id);
    saveImages(filtered);
    if (selectedImage?.id === id) {
      setSelectedImage(null);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const filteredImages = images.filter((img) =>
    img.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="memory-images-section" style={{ marginTop: 20 }}>
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
            placeholder="Search memory images..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <label className="btn btn-primary btn-sm" style={{ cursor: "pointer" }}>
          <Upload size={14} />
          <span>Upload Image</span>
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={handleImageUpload}
            style={{ display: "none" }}
          />
        </label>
      </div>

      {filteredImages.length === 0 ? (
        <div className="memory-empty" style={{ padding: 40, textAlign: "center" }}>
          <ImageIcon size={32} style={{ opacity: 0.3, marginBottom: 12 }} />
          <p className="models-empty-text">No images found in memory</p>
          <p className="models-empty-hint">
            Upload images or screenshots to persist visual memories for context.
          </p>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
            gap: 14,
          }}
        >
          {filteredImages.map((img) => (
            <div
              key={img.id}
              className="models-card"
              style={{
                padding: 8,
                cursor: "pointer",
                position: "relative",
                overflow: "hidden",
              }}
              onClick={() => setSelectedImage(img)}
            >
              <div
                style={{
                  width: "100%",
                  height: 140,
                  borderRadius: 6,
                  overflow: "hidden",
                  background: "rgba(0,0,0,0.2)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  position: "relative",
                }}
              >
                <img
                  src={img.dataUrl}
                  alt={img.name}
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                  }}
                />
                <button
                  className="btn-ghost"
                  style={{
                    position: "absolute",
                    top: 6,
                    right: 6,
                    background: "rgba(0,0,0,0.6)",
                    color: "#fff",
                    borderRadius: 4,
                    padding: 4,
                  }}
                  onClick={(e) => handleDeleteImage(img.id, e)}
                  title="Delete image"
                >
                  <Trash2 size={13} />
                </button>
              </div>
              <div
                style={{
                  marginTop: 8,
                  padding: "0 4px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 500,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    maxWidth: 130,
                  }}
                >
                  {img.name}
                </span>
                <span style={{ fontSize: 11, opacity: 0.6 }}>{formatSize(img.size)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Image Full-Size Preview Modal */}
      {selectedImage && (
        <div
          className="models-modal-overlay"
          onClick={() => setSelectedImage(null)}
        >
          <div
            className="models-modal"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 720, width: "90%" }}
          >
            <div className="models-modal-header">
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <ImageIcon size={18} />
                <h2 className="models-modal-title">{selectedImage.name}</h2>
              </div>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setSelectedImage(null)}
              >
                <X size={18} />
              </button>
            </div>
            <div
              className="models-modal-body"
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              <img
                src={selectedImage.dataUrl}
                alt={selectedImage.name}
                style={{
                  maxWidth: "100%",
                  maxHeight: 480,
                  borderRadius: 6,
                  objectFit: "contain",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
                }}
              />
              <div
                style={{
                  marginTop: 12,
                  fontSize: 12,
                  opacity: 0.7,
                  display: "flex",
                  gap: 16,
                }}
              >
                <span>Size: {formatSize(selectedImage.size)}</span>
                <span>
                  Date: {new Date(selectedImage.createdAt).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
