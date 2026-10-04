import "./CardShots.css";

const CARD_SHOTS = [
  { image: "/trip-card.jpg", caption: "the trip card everyone fills out" },
  { image: "/brochure.jpg", caption: "a brochure for each place" },
  { image: "/swipe-deck.jpg", caption: "the activity deck you rate" },
];

export function CardShots() {
  return (
    <section className="card-shots">
      <div className="wrap">
        <h2 className="section-title">it all happens in iMessage.</h2>
        <p className="card-shots-lede quiet">
          everything i find lands as a card in the chat, right where you’re already talking.
        </p>
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
