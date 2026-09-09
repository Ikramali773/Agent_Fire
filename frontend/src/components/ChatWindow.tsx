import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../types";
import { DocumentUpload } from "./DocumentUpload";
import { VoiceInputButton } from "./VoiceInputButton";

interface Props {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  onUploadDocument: (file: File) => Promise<void>;
  disabled: boolean;
  placeholder: string;
}

const SPEECH_SYNTHESIS_SUPPORTED = typeof window !== "undefined" && "speechSynthesis" in window;

export function ChatWindow({ messages, onSend, onUploadDocument, disabled, placeholder }: Props) {
  const [draft, setDraft] = useState("");
  const [speakReplies, setSpeakReplies] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastSpokenIndexRef = useRef(-1);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // §B.1: voice output. Only speaks a message once (tracked by index) and
  // only agent messages - a user's own typed/spoken text being read back at
  // them would be pointless and, more importantly, was never asked for.
  useEffect(() => {
    if (!speakReplies || !SPEECH_SYNTHESIS_SUPPORTED) return;
    const lastIndex = messages.length - 1;
    if (lastIndex <= lastSpokenIndexRef.current) return;
    lastSpokenIndexRef.current = lastIndex;
    const last = messages[lastIndex];
    if (last.role !== "agent") return;
    window.speechSynthesis.cancel(); // don't queue over a reply still being read
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(last.text));
  }, [messages, speakReplies]);

  useEffect(() => {
    if (!speakReplies && SPEECH_SYNTHESIS_SUPPORTED) {
      window.speechSynthesis.cancel();
    }
  }, [speakReplies]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setDraft("");
  };

  return (
    <div className="chat-window">
      {SPEECH_SYNTHESIS_SUPPORTED && (
        <label className="chat-window__speak-toggle">
          <input
            type="checkbox"
            checked={speakReplies}
            onChange={(event) => setSpeakReplies(event.target.checked)}
          />
          🔊 Read replies aloud
        </label>
      )}
      <div className="chat-messages">
        {messages.map((message, index) => (
          <div key={index} className={`chat-bubble chat-bubble--${message.role}`}>
            {message.text}
          </div>
        ))}
        {disabled && <div className="chat-bubble chat-bubble--agent chat-bubble--typing">…</div>}
        <div ref={bottomRef} />
      </div>
      <DocumentUpload onUpload={onUploadDocument} disabled={disabled} />
      <form className="chat-input-row" onSubmit={handleSubmit}>
        <VoiceInputButton
          onResult={(text) => setDraft((prev) => (prev ? `${prev} ${text}` : text))}
          disabled={disabled}
        />
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          autoFocus
        />
        <button type="submit" disabled={disabled || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
