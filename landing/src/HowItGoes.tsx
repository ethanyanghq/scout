import "./HowItGoes.css";

const STEPS = [
  {
    title: "add me.",
    detail: "put my number in the group text.",
  },
  {
    title: "tell me what you want.",
    detail: "dates, budget, vibe. 30 seconds.",
  },
  {
    title: "pick a place.",
    detail: "i pitch three that fit. you vote.",
  },
  {
    title: "i plan the rest.",
    detail: "days, flights, and who owes who.",
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
