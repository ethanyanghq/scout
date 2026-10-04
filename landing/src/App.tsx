import { CardShots } from "./CardShots";
import { Closing } from "./Closing";
import { Hero } from "./Hero";
import { HowItGoes } from "./HowItGoes";
import "./App.css";

const GITHUB_URL = "https://github.com/ethanyanghq/scout";
const DEVPOST_URL = "https://devpost.com/software/scout-pifctu";

export function App() {
  return (
    <>
      <header className="wrap site-header">
        <a className="brand" href="/">
          <img src="/logo.png" alt="" />
          scout
        </a>
        <a className="site-header-link" href="#how-it-goes">
          how it goes
        </a>
      </header>
      <main>
        <Hero />
        <HowItGoes />
        <CardShots />
        <Closing />
      </main>
      <footer className="wrap site-footer quiet">
        <a className="brand" href="/">
          <img src="/logo.png" alt="" />
          scout
        </a>
        <p className="site-footer-notes">
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            github ↗
          </a>
          <a href={DEVPOST_URL} target="_blank" rel="noreferrer">
            devpost ↗
          </a>
          <span>© 2026 scout</span>
        </p>
      </footer>
    </>
  );
}
