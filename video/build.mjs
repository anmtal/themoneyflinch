// Render one (or all) @themoneyflinch reels with Remotion.
//
// Pipeline per slug:
//   1. python voice.py <slug>   -> public/<slug>.mp3 + public/<slug>.words.json
//   2. bundle the Remotion project (once, reused across slugs)
//   3. render Reel with the words as inputProps -> out/<slug>.mp4
//   4. copy to ../content/reels/<slug>.mp4  (what the publisher hosts + posts)
//
// Usage: node build.mjs <slug>     # one reel
//        node build.mjs all        # every script in content/reel-v2-scripts.json
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, copyFileSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { selectComposition, renderMedia, ensureBrowser } from "@remotion/renderer";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = dirname(HERE);
const PUBLIC = join(HERE, "public");
const OUT = join(HERE, "out");
const REELS = join(ROOT, "content", "reels");
for (const d of [PUBLIC, OUT, REELS]) if (!existsSync(d)) mkdirSync(d, { recursive: true });

const PYTHON = process.env.PYTHON || "python";
const arg = process.argv[2] || "all";

const scripts = JSON.parse(
  readFileSync(join(ROOT, "content", "reel-v2-scripts.json"), "utf-8"),
);
const targets = arg === "all" ? scripts : scripts.filter((s) => s.slug === arg);
if (targets.length === 0) {
  console.error(`no script with slug '${arg}'`);
  process.exit(1);
}

// 1. Voiceover for every target FIRST. bundle() snapshots public/ into the bundle,
// so the mp3/words must already be on disk before we bundle — otherwise the render
// 404s on the audio.
for (const s of targets) {
  execFileSync(PYTHON, [join(HERE, "voice.py"), s.slug], { stdio: "inherit" });
}

console.log("Ensuring a headless browser is available...");
await ensureBrowser();

console.log("Bundling the Remotion project (one-time)...");
const serveUrl = await bundle({
  entryPoint: join(HERE, "src", "index.ts"),
  // keep the bundle quiet; brand fonts load via @remotion/google-fonts at runtime
  onProgress: () => {},
});

for (const s of targets) {
  const slug = s.slug;
  console.log(`\n=== ${slug} ===`);

  // 2. render
  const words = JSON.parse(readFileSync(join(PUBLIC, `${slug}.words.json`), "utf-8"));
  const inputProps = { slug, words, audioFile: `${slug}.mp3`, tail: 1.5 };

  const composition = await selectComposition({ serveUrl, id: "Reel", inputProps });
  const outFile = join(OUT, `${slug}.mp4`);

  // A concurrent Chrome tab occasionally dies mid-render on Windows ("Target
  // closed"). Keep concurrency modest and retry once so a 12-reel batch doesn't
  // abort on a single flaky tab.
  const render = () =>
    renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      outputLocation: outFile,
      inputProps,
      concurrency: 2,
      onProgress: ({ progress }) => {
        process.stdout.write(`\r  render ${Math.round(progress * 100)}%   `);
      },
    });
  try {
    await render();
  } catch (e) {
    console.log(`\n  render hiccup (${e.message?.split("\n")[0]}) — retrying once...`);
    await render();
  }

  // 3. publish location the scheduler hosts + posts
  const dest = join(REELS, `${slug}.mp4`);
  copyFileSync(outFile, dest);
  console.log(`\n  -> content/reels/${slug}.mp4  (${(composition.durationInFrames / composition.fps).toFixed(1)}s)`);
}

console.log(`\nDone. Rendered ${targets.length} reel(s).`);
