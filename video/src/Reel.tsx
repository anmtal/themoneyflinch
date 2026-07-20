import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont as loadGelasio } from "@remotion/google-fonts/Gelasio";
import { loadFont as loadCourier } from "@remotion/google-fonts/CourierPrime";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import {
  INK,
  CREAM,
  CREAM_SOFT,
  CORAL,
  DIM,
  GLOW,
  HANDLE,
  FlinchMark,
} from "./brand";
import { Word, phrasesFromWords, activePhraseIndex } from "./captions";

// Load only the weights/subset actually used — otherwise google-fonts fires 100+
// network requests per font at render and slows every frame's first paint.
const fontOpts = { subsets: ["latin"], ignoreTooManyRequestsWarning: true } as const;
const serif = loadGelasio("normal", { weights: ["400"], ...fontOpts }).fontFamily; // Georgia
const mono = loadCourier("normal", { weights: ["700"], ...fontOpts }).fontFamily; // wordmark
const sans = loadInter("normal", { weights: ["600"], ...fontOpts }).fontFamily; // handle

export type ReelProps = {
  slug: string;
  words: Word[];
  audioFile: string; // filename in public/, e.g. "v2-the-number.mp3"
  tail: number; // seconds held after the last word
};

// A single caption word. The word currently being spoken springs up and pops to
// coral; already-spoken words sit in CREAM (or coral in a CTA phrase); unspoken
// words stay DIM. That per-word motion is the thumb-stop a static card never had.
const CaptionWord: React.FC<{
  word: Word;
  isCTA: boolean;
  fps: number;
  t: number;
}> = ({ word, isCTA, fps, t }) => {
  const frame = useCurrentFrame();
  const spoken = word.t <= t;
  const isCurrent = spoken && t < word.t + word.d + 0.28;

  const enter = spring({
    frame: frame - word.t * fps,
    fps,
    config: { damping: 200, mass: 0.5 },
    durationInFrames: 8,
  });

  const baseColor = isCTA ? CORAL : CREAM;
  const color = !spoken ? DIM : isCurrent && !isCTA ? CORAL : isCTA && isCurrent ? CREAM : baseColor;

  return (
    <span
      style={{
        display: "inline-block",
        margin: "0 0.22em",
        color,
        opacity: spoken ? 1 : 0.55,
        transform: `translateY(${(1 - (spoken ? enter : 0)) * 14}px) scale(${
          isCurrent ? 1.05 : 1
        })`,
        transition: "color 90ms linear",
      }}
    >
      {word.w}
    </span>
  );
};

export const Reel: React.FC<ReelProps> = ({ words, audioFile, tail }) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const t = frame / fps;

  const phrases = phrasesFromWords(words);
  const pi = activePhraseIndex(phrases, t);
  const phrase = phrases[pi];

  // Drifting glow — a slow Lissajous wander, same idea as frame_bg() in reel_v2.py,
  // so the background is never dead-still.
  const gx = Math.sin((2 * Math.PI * t) / 11) * 90;
  const gy = Math.sin((2 * Math.PI * t) / 7 + 1) * 70;

  // Phrase swap: fade+lift the whole line as it changes.
  const phraseFrame = frame - phrase.start * fps;
  const phraseEnter = spring({ frame: phraseFrame, fps, config: { damping: 200 }, durationInFrames: 10 });
  const lineLift = interpolate(phraseEnter, [0, 1], [26, 0]);

  const progress = Math.min(1, t / (durationInFrames / fps));
  const hookScale = phrase.hook ? 1.18 : 1;

  return (
    <AbsoluteFill style={{ backgroundColor: INK }}>
      <Audio src={staticFile(audioFile)} />

      {/* drifting radial glow */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(closest-side, ${GLOW} 0%, rgba(44,62,72,0) 70%)`,
          transform: `translate(${gx}px, ${gy}px) scale(2.2)`,
          opacity: 0.55,
        }}
      />

      {/* top wordmark */}
      <div
        style={{
          position: "absolute",
          top: 120,
          width: "100%",
          textAlign: "center",
          fontFamily: mono,
          fontWeight: 700,
          fontSize: 40,
          letterSpacing: 2,
          color: CORAL,
        }}
      >
        THE MONEY FLINCH
      </div>

      {/* center kinetic caption */}
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          padding: "0 70px",
        }}
      >
        <div
          key={pi}
          style={{
            fontFamily: serif,
            fontSize: 86 * hookScale,
            lineHeight: 1.24,
            textAlign: "center",
            transform: `translateY(${lineLift}px)`,
            opacity: phraseEnter,
            maxWidth: 940,
          }}
        >
          {phrase.words.map((w, i) => (
            <CaptionWord key={i} word={w} isCTA={phrase.cta} fps={fps} t={t} />
          ))}
        </div>
      </AbsoluteFill>

      {/* progress bar */}
      <div style={{ position: "absolute", bottom: 96, left: 90, right: 90, height: 6 }}>
        <div style={{ position: "absolute", inset: 0, background: "#38444c", borderRadius: 3 }} />
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            bottom: 0,
            width: `${progress * 100}%`,
            background: CORAL,
            borderRadius: 3,
          }}
        />
      </div>

      {/* mark + handle */}
      <div
        style={{
          position: "absolute",
          bottom: 150,
          width: "100%",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <FlinchMark size={0.42} line={CREAM_SOFT} />
      </div>
      <div
        style={{
          position: "absolute",
          bottom: 118,
          width: "100%",
          textAlign: "center",
          fontFamily: sans,
          fontWeight: 600,
          fontSize: 34,
          color: CREAM_SOFT,
        }}
      >
        {HANDLE}
      </div>
    </AbsoluteFill>
  );
};
