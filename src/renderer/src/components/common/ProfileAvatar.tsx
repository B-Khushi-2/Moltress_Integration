import { defaultColorForName } from "../../../../shared/profileColors";
import moltresLogo from "../../assets/moltres.png";

interface ProfileAvatarProps {
  /** Profile/agent name — drives the letter and the default colour. */
  name: string;
  /** Resolved accent colour; falls back to a stable per-name default. */
  color?: string | null;
  /** Avatar image as a data URL; when set it wins over the letter/logo. */
  avatar?: string | null;
  /** Pixel diameter. */
  size?: number;
  /** Show the Hermes logo (instead of a letter) for the default profile when
   *  it has no custom avatar. */
  defaultLogo?: boolean;
  className?: string;
}

/**
 * Unified profile/agent avatar used in the nav, the active-sessions bar and the
 * manage page. Renders a custom image when one is set, otherwise a flat
 * coloured circle with the profile's initial (or the Hermes logo for the
 * default profile).
 */
export default function ProfileAvatar({
  name,
  color,
  avatar,
  size = 24,
  defaultLogo = true,
  className = "",
}: ProfileAvatarProps): React.JSX.Element {
  const resolvedColor = color || defaultColorForName(name);
  const dimension = { width: size, height: size };

  if (avatar) {
    return (
      <img
        src={avatar}
        alt={name}
        className={`profile-avatar profile-avatar-img ${className}`}
        style={dimension}
      />
    );
  }

  if (name === "default" && defaultLogo) {
    return (
      <img
        src={moltresLogo}
        alt={name}
        className={`profile-avatar profile-avatar-img ${className}`}
        style={{
          ...dimension,
          objectFit: "contain",
          boxShadow: "0 0 8px rgba(239, 68, 68, 0.4)",
          border: "1px solid rgba(239, 68, 68, 0.45)"
        }}
      />
    );
  }

  return (
    <div
      className={`profile-avatar profile-avatar-letter ${className}`}
      style={{
        ...dimension,
        background: resolvedColor,
        fontSize: Math.round(size * 0.46),
      }}
      aria-label={name}
    >
      {(name.trim()[0] || "?").toUpperCase()}
    </div>
  );
}
