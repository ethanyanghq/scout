import { type FormEvent, useId, useState } from "react";
import { sendJoinRequest } from "./joinRequest";
import "./JoinForm.css";

type JoinStatus = "idle" | "sending" | "joined" | "failed";

export function JoinForm() {
  const [status, setStatus] = useState<JoinStatus>("idle");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const nameId = useId();
  const phoneId = useId();

  async function join(event: FormEvent) {
    event.preventDefault();
    setStatus("sending");
    try {
      await sendJoinRequest({ name, phone });
      setStatus("joined");
    } catch (error) {
      console.error(error);
      setStatus("failed");
    }
  }

  if (status === "joined") {
    return (
      <p className="join-confirmation" role="status">
        got it, {name.trim().toLowerCase()}. you’re on the waitlist.
      </p>
    );
  }

  return (
    <form className="join-form" onSubmit={join}>
      <div className="join-fields">
        <label className="visually-hidden" htmlFor={nameId}>
          your name
        </label>
        <input
          id={nameId}
          name="name"
          autoComplete="given-name"
          placeholder="your name"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <label className="visually-hidden" htmlFor={phoneId}>
          your phone number
        </label>
        <input
          id={phoneId}
          name="phone"
          type="tel"
          autoComplete="tel"
          placeholder="phone number"
          required
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
        />
        <button className="button" type="submit" disabled={status === "sending"}>
          {status === "sending" ? "sending…" : "join the waitlist"}
        </button>
      </div>
      {status === "failed" && (
        <p className="join-error" role="alert">
          that didn’t go through. check your connection and try again.
        </p>
      )}
    </form>
  );
}
