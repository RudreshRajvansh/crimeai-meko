/**
 * AuthBackground — shared intelligence-themed background for all auth pages.
 *
 * Layers (bottom → top):
 *  1. Near-black base gradient
 *  2. Faint technical grid
 *  3. Barely-visible intelligence visualisation (radar arcs, network nodes, map contours)
 *  4. Slow-floating ambient orbs
 *  5. Central radial glow behind the card area
 *
 * All decorative elements are pointer-events-none and aria-hidden.
 */
export default function AuthBackground() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      {/* 1 — Base gradient */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% 40%, #0a1628 0%, #060a10 50%, #020408 100%)',
        }}
      />

      {/* 2 — Technical grid */}
      <div
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(31,111,235,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(31,111,235,0.35) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
          maskImage:
            'radial-gradient(ellipse 70% 70% at 50% 50%, #000 30%, transparent 100%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 70% 70% at 50% 50%, #000 30%, transparent 100%)',
        }}
      />

      {/* 3 — Intelligence visualisation elements (SVG) */}
      <svg
        className="absolute inset-0 w-full h-full opacity-[0.04]"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid slice"
      >
        {/* Radar sweep arcs */}
        <g className="animate-radar-spin" style={{ transformOrigin: '50% 50%' }}>
          <circle
            cx="50%"
            cy="50%"
            r="180"
            fill="none"
            stroke="#1f6feb"
            strokeWidth="0.5"
            strokeDasharray="40 80"
          />
          <circle
            cx="50%"
            cy="50%"
            r="280"
            fill="none"
            stroke="#1f6feb"
            strokeWidth="0.4"
            strokeDasharray="30 120"
          />
        </g>

        {/* Static concentric radar rings */}
        <circle cx="50%" cy="50%" r="120" fill="none" stroke="#1f6feb" strokeWidth="0.3" opacity="0.5" />
        <circle cx="50%" cy="50%" r="220" fill="none" stroke="#1f6feb" strokeWidth="0.2" opacity="0.35" />
        <circle cx="50%" cy="50%" r="340" fill="none" stroke="#1f6feb" strokeWidth="0.2" opacity="0.2" />

        {/* Abstract network nodes */}
        {[
          [120, 180], [340, 140], [580, 220], [180, 420], [460, 380],
          [700, 300], [250, 550], [550, 480], [80, 320], [650, 150],
        ].map(([cx, cy], i) => (
          <g key={i}>
            <circle cx={cx} cy={cy} r="1.5" fill="#1f6feb" opacity="0.6" />
            {/* Connect to next node */}
            {i < 9 && (
              <line
                x1={cx}
                y1={cy}
                x2={[120,340,580,180,460,700,250,550,80,650][i+1]}
                y2={[180,140,220,420,380,300,550,480,320,150][i+1]}
                stroke="#1f6feb"
                strokeWidth="0.3"
                opacity="0.25"
              />
            )}
          </g>
        ))}

        {/* Abstract geographic contours */}
        <path
          d="M100,600 Q250,520 400,560 T700,500 T1000,540"
          fill="none"
          stroke="#1f6feb"
          strokeWidth="0.4"
          opacity="0.2"
        />
        <path
          d="M0,400 Q200,350 350,380 T600,340 T900,370"
          fill="none"
          stroke="#1f6feb"
          strokeWidth="0.3"
          opacity="0.15"
        />
      </svg>

      {/* 4 — Floating ambient orbs */}
      <div
        className="absolute animate-float-slow"
        style={{
          top: '-8%',
          left: '-5%',
          width: '420px',
          height: '420px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(31,111,235,0.12) 0%, transparent 70%)',
          filter: 'blur(80px)',
        }}
      />
      <div
        className="absolute animate-float-slow-r"
        style={{
          bottom: '-10%',
          right: '-8%',
          width: '500px',
          height: '500px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(56,189,248,0.06) 0%, transparent 70%)',
          filter: 'blur(100px)',
        }}
      />

      {/* 5 — Central radial glow (behind card area) */}
      <div
        className="absolute left-1/2 top-[45%] -translate-x-1/2 -translate-y-1/2"
        style={{
          width: '600px',
          height: '500px',
          borderRadius: '50%',
          background:
            'radial-gradient(ellipse, rgba(31,111,235,0.07) 0%, transparent 70%)',
          filter: 'blur(60px)',
        }}
      />
    </div>
  )
}
