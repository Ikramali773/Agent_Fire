import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../types";

interface Props {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  disabled: boolean;
  placeholder: string;
}

export function ChatWindow({ messages, onSend, disabled, placeholder }: Props) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setDraft("");
  };

  return (
    <div className="chat-window">
      <div className="chat-messages">
        {messages.map((message, index) => (
          <div key={index} className={`chat-bubble chat-bubble--${message.role}`}>
            {message.text}
          </div>
        ))}
        {disabled && <div className="chat-bubble chat-bubble--agent chat-bubble--typing">…</div>}
        <div ref={bottomRef} />
      </div>
      <form className="chat-input-row" onSubmit={handleSubmit}>
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
