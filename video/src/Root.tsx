import React from "react";
import { Composition, staticFile } from "remotion";
import { Reel, ReelProps } from "./Reel";
import { Word } from "./captions";

const FPS = 30;
const W = 1080;
const H = 1920;

// Duration is driven by the voiceover: read the words JSON that voice.py wrote and
// end `tail` seconds after the last word. calculateMetadata runs in Node at render
// time, so the composition length always matches the audio with no manual setting.
export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Reel"
      component={Reel}
      durationInFrames={300}
      fps={FPS}
      width={W}
      height={H}
      defaultProps={
        {
          slug: "preview",
          words: [] as Word[],
          audioFile: "preview.mp3",
          tail: 1.5,
        } as ReelProps
      }
      calculateMetadata={async ({ props }) => {
        let words = props.words;
        // In Studio/preview, props.words may be empty — hydrate from the JSON if a
        // slug is given so the timeline shows the real length.
        if ((!words || words.length === 0) && props.slug) {
          try {
            const res = await fetch(staticFile(`${props.slug}.words.json`));
            words = (await res.json()) as Word[];
          } catch {
            words = [];
          }
        }
        const last = words.length ? words[words.length - 1] : { t: 8, d: 0 };
        const seconds = last.t + last.d + (props.tail ?? 1.5);
        return {
          durationInFrames: Math.ceil(seconds * FPS),
          props: { ...props, words, audioFile: props.audioFile || `${props.slug}.mp3` },
        };
      }}
    />
  );
};
