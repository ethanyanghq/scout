# scout's landing page

One page that says what scout does, shows it working in an iPhone frame, and takes the name and phone number of anyone who wants in. Built with React and Vite, hosted on Netlify.

```
bun install
bun run dev        # the page at http://localhost:5173
bun run test
bun run typecheck
bun run build      # what Netlify runs; the site lands in dist/
```

## Hosting

`netlify.toml` at the repository root tells Netlify to build this folder, so connecting the repository to a Netlify site is the only setup.

## The demo recording

The iPhone frame shows a still chat until there is a screen recording. To add one, put the file in `public/` (for example `public/demo.mp4`) and set `DEMO_RECORDING_URL` in `src/DemoPhone.tsx` to its path (`"/demo.mp4"`). It plays muted on a loop. Record on an iPhone so the video matches the frame's 9:19.5 shape.

## Who wants in

The form sends each name and phone number to [Netlify Forms](https://docs.netlify.com/manage/forms/setup/), under the form named `join`: read them in the Netlify dashboard under Forms. Nothing texts these people automatically. The form only works on Netlify, so submitting it under `bun run dev` shows the "that didn't go through" message.

## The font

Lexend, the brand font, comes from Google Fonts and is served from `public/fonts/` under the license next to it.
