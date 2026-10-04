import "./DemoPhone.css";

// Set this to the screen recording's path under public/ (for example
// "/demo.mp4") once it exists. Until then the frame shows a still chat.
const DEMO_RECORDING_URL: string | null = null;

export function DemoPhone() {
  return (
    <div className="phone">
      <div className="phone-screen">
        {DEMO_RECORDING_URL ? (
          <video
            src={DEMO_RECORDING_URL}
            aria-label="scout planning a trip in a group chat"
            autoPlay
            muted
            loop
            playsInline
          />
        ) : (
          <StillChat />
        )}
      </div>
    </div>
  );
}

function StillChat() {
  return (
    <div className="chat" role="img" aria-label="scout planning a trip in a group chat">
      <div className="chat-head">
        <div className="chat-faces">
          <span style={{ background: "#f08a5d" }}>L</span>
          <span style={{ background: "#8e7cc3" }}>M</span>
          <img src="/logo.png" alt="" />
          <span style={{ background: "#3aa6a0" }}>J</span>
        </div>
        <p className="chat-title">spring break ’27</p>
      </div>
      <div className="chat-body">
        <p className="chat-sender">leo</p>
        <p className="chat-bubble">this chat has 600 messages and zero plans</p>
        <p className="chat-bubble is-mine">ok adding scout</p>
        <p className="chat-sender is-scout">scout</p>
        <div className="chat-scout-turn">
          <img src="/logo.png" alt="" />
          <div>
            <p className="chat-bubble">hi all, i’m scout. tap through the card and i’ll take it from here</p>
            <div className="chat-card">
              <img src="/trip-card.jpg" alt="" />
              <p>
                Let’s plan your trip<span>a few taps, then send</span>
              </p>
            </div>
          </div>
        </div>
        <p className="chat-sender">jordan</p>
        <p className="chat-bubble">mar 13–20, ~$800, boston</p>
        <p className="chat-sender is-scout">scout</p>
        <div className="chat-scout-turn">
          <img src="/logo.png" alt="" />
          <div>
            <p className="chat-bubble">4 of 5 in, and you’re leaning beach. three places coming up</p>
            <div className="chat-card is-brochure">
              <img src="/brochure.jpg" alt="" />
              <p>
                Cancún<span>~$1,450 per person, all in</span>
              </p>
            </div>
          </div>
        </div>
      </div>
      <div className="chat-compose">
        <i />
        <span>iMessage</span>
      </div>
    </div>
  );
}
