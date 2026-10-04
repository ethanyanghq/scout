import { useRef, useState } from "react";
import { playYoutubeVideo } from "./youtubePlayer";
import "./DemoVideo.css";

const DEMO_VIDEO_ID = "K9avihlDf5E";
const DEMO_VIDEO_URL = `https://youtu.be/${DEMO_VIDEO_ID}`;

type DemoVideoStatus = "waiting" | "loading" | "playing" | "failed";

// The page shows its own poster and play button, and YouTube's player loads
// only when someone presses play. Until then nothing is requested from
// YouTube and none of its branding sits on the page.
export function DemoVideo() {
  const [status, setStatus] = useState<DemoVideoStatus>("waiting");
  const playerFrame = useRef<HTMLDivElement>(null);

  async function play() {
    setStatus("loading");
    try {
      await playYoutubeVideo(DEMO_VIDEO_ID, playerFrame.current!);
      setStatus("playing");
    } catch (error) {
      console.error(error);
      setStatus("failed");
    }
  }

  return (
    <div className="demo-video">
      <div className="demo-video-screen">
        <div className="demo-video-player" ref={playerFrame} />
        {status !== "playing" && (
          <button className="demo-video-poster" type="button" disabled={status === "loading"} onClick={play}>
            <img src="/demo-poster.jpg" alt="" width={1280} height={720} />
            <span className="demo-video-play">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M7 4.8v14.4a1 1 0 0 0 1.5.9l11.9-7.2a1 1 0 0 0 0-1.8L8.5 3.9A1 1 0 0 0 7 4.8Z" />
              </svg>
              watch the demo
            </span>
          </button>
        )}
      </div>
      {status === "failed" && (
        <p className="demo-video-error" role="alert">
          the video didn’t load.{" "}
          <a href={DEMO_VIDEO_URL} target="_blank" rel="noreferrer">
            watch it on youtube ↗
          </a>
        </p>
      )}
    </div>
  );
}
