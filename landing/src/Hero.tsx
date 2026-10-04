import { DemoVideo } from "./DemoVideo";
import { JoinForm } from "./JoinForm";
import "./Hero.css";

export function Hero() {
  return (
    <section className="wrap hero">
      <h1>
        trips that make it out of the <em>group chat.</em>
      </h1>
      <p className="hero-lede quiet">i’m scout, the AI trip planner you add to your group text.</p>
      <JoinForm />
      <DemoVideo />
    </section>
  );
}
