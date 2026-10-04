# scout's landing page

One page that says what scout does, shows the demo video, and takes the name and phone number of anyone who joins the waitlist. Built with React and Vite, hosted on Netlify.

```
bun install
bun run dev        # the page at http://localhost:5173
bun run test
bun run typecheck
bun run build      # what Netlify runs; the site lands in dist/
```

## Hosting

`netlify.toml` at the repository root tells Netlify to build this folder, so connecting the repository to a Netlify site is the only setup.

## The demo video

The demo is a YouTube video, but the page shows its own poster and play button, and loads YouTube's player only when someone presses play. To change the video, set `DEMO_VIDEO_ID` in `src/DemoVideo.tsx` and replace `public/demo-poster.jpg` with a 16:9 frame of the new video. YouTube serves one at `https://i.ytimg.com/vi/<video id>/maxresdefault.jpg`.

The play button is placed to sit under the text in the current poster. If the new poster is laid out differently, move it with `top` and `left` on `.demo-video-play` in `src/DemoVideo.css`.

## The waitlist

The form sends each name and phone number to [Netlify Forms](https://docs.netlify.com/manage/forms/setup/), under the form named `join`: read them in the Netlify dashboard under Forms. Nothing texts these people automatically. The form only works on Netlify, so submitting it under `bun run dev` shows the "that didn't go through" message.

## The font

Lexend, the brand font, comes from Google Fonts and is served from `public/fonts/` under the license next to it.
