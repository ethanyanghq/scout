import { DemoPhone } from "./DemoPhone";
import { JoinForm } from "./JoinForm";
import "./Hero.css";

const MESSAGES_BEFORE_SCOUT = [
  "we should go somewhere",
  "omg yes",
  "when tho",
  "i’m free whenever",
  "someone make a doc?",
  "bump",
];

const PLAN_AFTER_SCOUT = [
  { color: "var(--cobalt)", title: "cancún, mar 13–20", detail: "locked in by all 5" },
  { color: "var(--sun)", title: "bos → cun, $412", detail: "best round trip from each city" },
  { color: "var(--leaf)", title: "day 2: cenotes, tacos", detail: "in everyone’s calendar" },
  { color: "var(--ink)", title: "leo owes maya $86", detail: "settled in two payments" },
];

export function Hero() {
  return (
    <section className="wrap hero">
      <h1>
        trips that make it out of the <em>group chat.</em>
      </h1>
      <p className="hero-lede quiet">i’m scout, the AI trip planner you add to your group text.</p>
      <JoinForm />

      <div className="hero-stage">
        <div className="hero-before" aria-hidden="true">
          <p className="hero-stage-label">before</p>
          {MESSAGES_BEFORE_SCOUT.map((message) => (
            <p className="hero-stray-message" key={message}>
              {message}
            </p>
          ))}
        </div>
        <DemoPhone />
        <div className="hero-after" aria-hidden="true">
          <p className="hero-stage-label">after</p>
          {PLAN_AFTER_SCOUT.map((item) => (
            <div className="hero-plan-item" key={item.title}>
              <i style={{ background: item.color }} />
              <p>
                <strong>{item.title}</strong>
                <span>{item.detail}</span>
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
