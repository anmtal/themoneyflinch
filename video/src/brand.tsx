// The Money Flinch brand kit, mirrored from tools/carousel_batch.py so the coded
// reel is pixel-consistent with the carousels and the old PIL reels.
import React from "react";

export const INK = "#16232a";        // rgb(22,35,42)   — deep navy background
export const CREAM = "#f6f1e7";      // rgb(246,241,231)— spoken text
export const CREAM_SOFT = "#c4c7c4"; // rgb(196,199,196)— handle / secondary
export const CORAL = "#d96c4f";      // rgb(217,108,79) — accent / the "flinch"
export const DIM = "#5c666e";        // rgb(92,102,110) — not-yet-spoken text
export const GLOW = "#2c3e48";       // rgb(44,62,72)   — lighter navy drift patch

export const HANDLE = "@themoneyflinch";

// The flinch mark: a flatline with a single coral heartbeat spike in the middle —
// the visual pun of the brand (money makes you flinch). Coordinates match
// flinch_mark() in carousel_batch.py, drawn here as SVG.
export const FlinchMark: React.FC<{ size?: number; line?: string }> = ({
  size = 1,
  line = CREAM_SOFT,
}) => {
  const s = size;
  const w = 10 * s;
  const pt = (x: number, y: number) => `${x * s},${y * s}`;
  return (
    <svg
      width={220 * s}
      height={110 * s}
      viewBox={`${-110 * s} ${-55 * s} ${220 * s} ${110 * s}`}
      style={{ overflow: "visible" }}
    >
      <polyline
        points={`${pt(-95, 0)} ${pt(-29, 0)}`}
        stroke={line}
        strokeWidth={w}
        strokeLinecap="round"
        fill="none"
      />
      <polyline
        points={`${pt(29, 0)} ${pt(95, 0)}`}
        stroke={line}
        strokeWidth={w}
        strokeLinecap="round"
        fill="none"
      />
      <polyline
        points={`${pt(-29, 0)} ${pt(-9, -38)} ${pt(14, 43)} ${pt(29, 0)}`}
        stroke={CORAL}
        strokeWidth={w}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
};
