import "./CardShots.css";

const CARD_SHOTS = [
  { image: "/trip-card.jpg", caption: "the trip card" },
  { image: "/brochure.jpg", caption: "the brochures" },
  { image: "/swipe-deck.jpg", caption: "the activity deck" },
];

export function CardShots() {
  return (
    <section className="card-shots">
      <div className="wrap">
        <h2 className="section-title">it all happens in iMessage.</h2>
      </div>
      <div className="card-shots-row">
        {CARD_SHOTS.map((shot) => (
          <figure key={shot.image}>
            <img src={shot.image} alt="" width={560} height={1072} loading="lazy" />
            <figcaption className="quiet">{shot.caption}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
