import { CardShots } from "./CardShots";
import { Closing } from "./Closing";
import { Hero } from "./Hero";
import { HowItGoes } from "./HowItGoes";
import "./App.css";

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
        <span>© 2026 scout</span>
      </footer>
    </>
  );
}
