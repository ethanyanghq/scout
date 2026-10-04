import "./HowItGoes.css";

const STEPS = [
  {
    title: "add me.",
    detail: "put my number in the group text. i say hi once and drop a trip card in the chat.",
  },
  {
    title: "tell me what you want.",
    detail: "everyone taps through the card: dates, budget, home city, what you’re into. takes like 30 seconds.",
  },
  {
    title: "pick a place.",
    detail: "i pitch three places that fit, with real photos, hotels and prices. lock one in, or vote.",
  },
  {
    title: "i plan the rest.",
    detail: "the days, flights from each home city, the room, and who owes who at the end.",
  },
];

export function HowItGoes() {
  return (
    <section className="wrap how-it-goes" id="how-it-goes">
      <h2 className="section-title">here’s how it goes.</h2>
      <ol className="steps">
        {STEPS.map((step, index) => (
          <li className="step" key={step.title}>
            <p className="step-number">{String(index + 1).padStart(2, "0")}</p>
            <h3>{step.title}</h3>
            <p className="quiet">{step.detail}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
