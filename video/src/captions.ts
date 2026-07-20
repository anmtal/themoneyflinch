// Group edge-tts word timings into short on-screen phrases, mirroring
// phrases_from_words() in tools/reel_v2.py. One idea flashes at a time; the ear
// (voice) holds the viewer while the eye reads the highlighted word.

export type Word = { t: number; d: number; w: string }; // start, duration, text (seconds)

export type Phrase = {
  words: Word[];
  start: number;
  cta: boolean;   // part of the "send this to..." ask -> rendered coral
  hook: boolean;  // the opening phrase -> rendered larger
};

const GAP_BREAK = 0.26; // a pause longer than this starts a new phrase
const MAX_WORDS = 7;    // ...or this many words, whichever comes first

export function phrasesFromWords(words: Word[]): Phrase[] {
  const groups: Word[][] = [];
  let cur: Word[] = [];
  for (let i = 0; i < words.length; i++) {
    cur.push(words[i]);
    const nxt = words[i + 1];
    const gap = nxt ? nxt.t - (words[i].t + words[i].d) : 999;
    if (!nxt || gap > GAP_BREAK || cur.length >= MAX_WORDS) {
      groups.push(cur);
      cur = [];
    }
  }

  // Kill widows: a lone word on screen (e.g. the 8th word of a CTA split off by the
  // 7-word cap, leaving "worst" alone) reads as a mistake. Merge any single-word
  // group back into the previous phrase so lines always feel intentional.
  for (let i = groups.length - 1; i > 0; i--) {
    if (groups[i].length === 1) {
      groups[i - 1] = groups[i - 1].concat(groups[i]);
      groups.splice(i, 1);
    }
  }

  const phrases: Phrase[] = groups.map((g, i) => ({
    words: g,
    start: g[0].t,
    cta: false,
    hook: i === 0,
  }));

  // Everything from the first "send" onward is the CTA — color it as one unit so
  // the ask reads deliberately, not as a stray coral word.
  const ctaFrom = phrases.findIndex((ph) =>
    ph.words.some((w) => w.w.toLowerCase().replace(/[.,!?]/g, "") === "send"),
  );
  if (ctaFrom !== -1) {
    for (let i = ctaFrom; i < phrases.length; i++) phrases[i].cta = true;
  }
  return phrases;
}

export function activePhraseIndex(phrases: Phrase[], t: number): number {
  let idx = 0;
  for (let i = 0; i < phrases.length; i++) if (phrases[i].start <= t) idx = i;
  return idx;
}
