import { useEffect, useRef } from "react";
import splashLogo from "../../assets/hermes-one.svg";

interface SplashScreenProps {
  onFinished: () => void;
  status?: string;
}

function SplashScreen({
  onFinished,
  status,
}: SplashScreenProps): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    onFinished();
  }, [onFinished]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const particles: Array<{
      x: number;
      y: number;
      vx: number;
      vy: number;
      radius: number;
      color: string;
    }> = [];

    // Initialize particles
    const particleCount = Math.min(80, Math.floor((width * height) / 15000));
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        radius: Math.random() * 2 + 1,
        color: `rgba(255, 255, 255, ${Math.random() * 0.3 + 0.1})`,
      });
    }

    const handleResize = (): void => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    window.addEventListener("resize", handleResize);

    let pulseTime = 0;

    const animate = (): void => {
      ctx.fillStyle = "rgba(10, 12, 18, 1)"; // Dark premium tech background
      ctx.fillRect(0, 0, width, height);

      // Draw subtle pulsing radial glow in the center
      pulseTime += 0.005;
      const pulseScale = Math.sin(pulseTime) * 0.15 + 0.85;
      const gradient = ctx.createRadialGradient(
        width / 2,
        height / 2,
        0,
        width / 2,
        height / 2,
        Math.min(width, height) * 0.4 * pulseScale
      );
      // Soft modern gradient: deep indigo/violet to dark background
      gradient.addColorStop(0, "rgba(59, 130, 246, 0.08)");
      gradient.addColorStop(0.5, "rgba(124, 58, 237, 0.03)");
      gradient.addColorStop(1, "rgba(10, 12, 18, 0)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);

      // Draw particles and lines
      ctx.lineWidth = 0.5;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // Update position
        p.x += p.vx;
        p.y += p.vy;

        // Bounce off walls
        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;

        // Draw particle
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.fill();

        // Draw connection lines
        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dx = p.x - p2.x;
          const dy = p.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 120) {
            const alpha = (1 - dist / 120) * 0.12;
            ctx.strokeStyle = `rgba(99, 102, 241, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
          }
        }
      }

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="splash-screen">
      <canvas ref={canvasRef} className="splash-bg" />
      <img className="splash-logo" src={splashLogo} alt="Moltress" />
      {status && <div className="splash-status">{status}</div>}
    </div>
  );
}

export default SplashScreen;
