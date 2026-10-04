// YouTube's IFrame Player API:
// https://developers.google.com/youtube/iframe_api_reference
//
// A plain embed with ?autoplay=1 does not start on phones or in Safari,
// because the tap on our poster does not carry into YouTube's frame. A player
// made through the API can be told to play, so one tap is enough everywhere.
const YOUTUBE_API_URL = "https://www.youtube.com/iframe_api";

type YoutubePlayer = {
  playVideo(): void;
};

type YoutubePlayerOptions = {
  videoId: string;
  width: string;
  height: string;
  playerVars: { autoplay: 1; playsinline: 1; rel: 0 };
  events: { onReady: (event: { target: YoutubePlayer }) => void };
};

type YoutubeApi = {
  Player: new (slot: HTMLElement, options: YoutubePlayerOptions) => YoutubePlayer;
};

declare global {
  interface Window {
    YT?: YoutubeApi;
    onYouTubeIframeAPIReady?: () => void;
  }
}

/** Starts the video inside `frame`, and resolves once it is ready and playing. */
export async function playYoutubeVideo(videoId: string, frame: HTMLElement): Promise<void> {
  const youtube = await loadYoutubeApi();
  // YouTube replaces the element it is given with its iframe, so it gets an
  // element of its own instead of one React draws.
  const slot = frame.appendChild(document.createElement("div"));
  return new Promise((resolve) => {
    new youtube.Player(slot, {
      videoId,
      width: "100%",
      height: "100%",
      playerVars: { autoplay: 1, playsinline: 1, rel: 0 },
      events: {
        onReady: (event) => {
          event.target.playVideo();
          resolve();
        },
      },
    });
  });
}

function loadYoutubeApi(): Promise<YoutubeApi> {
  if (window.YT?.Player) {
    return Promise.resolve(window.YT);
  }
  return new Promise((resolve, reject) => {
    // YouTube's script calls this global once the player can be made.
    window.onYouTubeIframeAPIReady = () => resolve(window.YT!);
    const script = document.createElement("script");
    script.src = YOUTUBE_API_URL;
    script.onerror = () => reject(new Error(`YouTube's player script did not load from ${YOUTUBE_API_URL}`));
    document.head.append(script);
  });
}
