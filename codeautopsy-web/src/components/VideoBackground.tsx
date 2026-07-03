import { useEffect, useRef } from 'react';

interface VideoBackgroundProps {
  isDark: boolean;
}

interface Node3D {
  x: number;
  y: number;
  z: number;
  baseX: number;
  baseY: number;
  baseZ: number;
  angle: number;
  speed: number;
}

export default function VideoBackground({ isDark }: VideoBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    // Mouse tracking variables
    let mouseX = width / 2;
    let mouseY = height / 2;
    let targetAngleY = 0;
    let targetAngleX = 0;
    let currentAngleY = 0;
    let currentAngleX = 0;

    // Generate 3D nodes arranged in a flowing cyber-mesh orb
    // 120 nodes is the absolute sweet spot for perfect visual density and 60fps mobile execution!
    const nodes: Node3D[] = [];
    const nodeCount = 120;

    for (let i = 0; i < nodeCount; i++) {
      // Golden spiral distribution for a perfectly spherical uniform shell
      const phi = Math.acos(-1 + (2 * i) / nodeCount);
      const theta = Math.sqrt(nodeCount * Math.PI) * phi;

      // Base coordinates on a normalized unit sphere (radius = 1.0)
      const x = Math.sin(phi) * Math.cos(theta);
      const y = Math.sin(phi) * Math.sin(theta);
      const z = Math.cos(phi);

      nodes.push({
        x,
        y,
        z,
        baseX: x,
        baseY: y,
        baseZ: z,
        angle: Math.random() * Math.PI * 2,
        speed: 0.004 + Math.random() * 0.008,
      });
    }

    // Handle resizing
    const handleResize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    // Track mouse movement
    const handleMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
      
      // Calculate target rotation angles based on cursor offset from center
      targetAngleY = ((mouseX / width) - 0.5) * 1.5;
      targetAngleX = -((mouseY / height) - 0.5) * 1.5;
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);

    // Animation Loop
    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      // 1. Render premium ambient backdrop gradient
      const gradient = ctx.createRadialGradient(
        width * 0.7,
        height * 0.4,
        0,
        width * 0.7,
        height * 0.4,
        width * 0.8
      );

      if (isDark) {
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.07)'); // Neon blue glow
        gradient.addColorStop(0.5, 'rgba(99, 102, 241, 0.02)'); // Indigo glow
        gradient.addColorStop(1, 'rgba(10, 10, 12, 1)'); // Deep black/slate base
      } else {
        gradient.addColorStop(0, 'rgba(59, 130, 246, 0.04)');
        gradient.addColorStop(0.6, 'rgba(244, 244, 245, 0.95)');
        gradient.addColorStop(1, 'rgba(255, 255, 255, 1)');
      }

      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);

      // 2. LERP easing for buttery smooth 60fps tracking
      currentAngleY += (targetAngleY - currentAngleY) * 0.08;
      currentAngleX += (targetAngleX - currentAngleX) * 0.08;

      const cosY = Math.cos(currentAngleY);
      const sinY = Math.sin(currentAngleY);
      const cosX = Math.cos(currentAngleX);
      const sinX = Math.sin(currentAngleX);

      // 3. Responsive coordinate and sizing calculations
      const isMobile = width < 768;
      const currentRadius = Math.min(width, height) * (isMobile ? 0.35 : 0.28);
      const centerX = isMobile ? width * 0.5 : width * 0.7; // Centered on mobile, shifted right on desktop
      const centerY = isMobile ? height * 0.55 : height * 0.55;

      const fov = 500;

      // Project and draw connection lines between close 3D points
      interface ProjectedNode {
        x: number;
        y: number;
        z: number;
        scale: number;
        alpha: number;
      }

      const projected: ProjectedNode[] = [];

      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        
        // Add a subtle perpetual orbital wave movement (proportional to base unit size)
        node.angle += node.speed;
        const wave = Math.sin(node.angle) * 0.05;
        const rawX = (node.baseX + node.baseX * wave) * currentRadius;
        const rawY = (node.baseY + node.baseY * wave) * currentRadius;
        const rawZ = (node.baseZ + node.baseZ * wave) * currentRadius;

        // Rotate Y-axis
        let x1 = rawX * cosY - rawZ * sinY;
        let z1 = rawX * sinY + rawZ * cosY;

        // Rotate X-axis
        let y2 = rawY * cosX - z1 * sinX;
        let z2 = rawY * sinX + z1 * cosX;

        // Perspective projection
        const scale = fov / (fov + z2);
        const projX = centerX + x1 * scale;
        const projY = centerY + y2 * scale;

        // Depth-based transparency for gorgeous parallax layering
        const alpha = Math.max(0.1, Math.min(1, (fov - z2) / (fov * 1.5)));

        projected.push({
          x: projX,
          y: projY,
          z: z2,
          scale,
          alpha,
        });
      }

      // Draw structural connection wires (Constellation effect)
      ctx.lineWidth = 0.8;
      const maxDistance = currentRadius * 0.5;

      for (let i = 0; i < projected.length; i++) {
        const p1 = projected[i];
        for (let j = i + 1; j < projected.length; j++) {
          const p2 = projected[j];

          // Calculate distance in 3D space to keep structural connections consistent during rotation
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dz = nodes[i].z - nodes[j].z;
          const dist3D = Math.sqrt(dx * dx + dy * dy + dz * dz) * currentRadius;

          if (dist3D < maxDistance) {
            const opacity = (1 - dist3D / maxDistance) * 0.15 * Math.min(p1.alpha, p2.alpha);
            if (opacity > 0.01) {
              ctx.strokeStyle = isDark
                ? `rgba(59, 130, 246, ${opacity})`
                : `rgba(0, 0, 0, ${opacity * 1.5})`;
              ctx.beginPath();
              ctx.moveTo(p1.x, p1.y);
              ctx.lineTo(p2.x, p2.y);
              ctx.stroke();
            }
          }
        }
      }

      // Draw the glowing constellation nodes
      for (let i = 0; i < projected.length; i++) {
        const p = projected[i];
        const dotSize = Math.max(1, p.scale * 2.2);

        // Core dot
        ctx.fillStyle = isDark
          ? `rgba(255, 255, 255, ${p.alpha * 0.85})`
          : `rgba(0, 0, 0, ${p.alpha * 0.65})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, dotSize, 0, Math.PI * 2);
        ctx.fill();

        // Glowing corona for close depth nodes in dark mode
        if (isDark && p.z < 0) {
          ctx.fillStyle = `rgba(59, 130, 246, ${p.alpha * 0.15})`;
          ctx.beginPath();
          ctx.arc(p.x, p.y, dotSize * 3.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, [isDark]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        width: '100%',
        height: '100%',
        display: 'block',
        pointerEvents: 'none',
        transition: 'opacity 0.6s ease',
      }}
    />
  );
}
