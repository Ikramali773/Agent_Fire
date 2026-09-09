import { useRef, useState } from "react";

interface Props {
  onResult: (text: string) => void;
  disabled: boolean;
}

function getSpeechRecognitionCtor(): (new () => SpeechRecognition) | null {
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

// §B.1: voice input via the browser's own SpeechRecognition - no backend
// change needed, and no cost/API key either. Not every browser implements
// it (Firefox doesn't; Safari's support is partial) so this renders nothing
// at all rather than a broken button when it's missing - the text input
// next to it is a complete substitute, never a fallback that's worse than
// just not showing this.
export function VoiceInputButton({ onResult, disabled }: Props) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) return null;

  const handleClick = () => {
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }

    setError(null);
    const recognition = new Ctor();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) onResult(transcript);
    };
    recognition.onerror = (event) => {
      setError(
        event.error === "not-allowed"
          ? "Microphone access denied."
          : "Voice input didn't work — try typing instead.",
      );
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;

    try {
      recognition.start();
      setListening(true);
    } catch {
      setError("Could not start voice input.");
    }
  };

  return (
    <span className="voice-input">
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        className={`voice-input__button${listening ? " voice-input__button--active" : ""}`}
        aria-label={listening ? "Stop voice input" : "Start voice input"}
        title={listening ? "Stop voice input" : "Start voice input"}
      >
        {listening ? "🔴" : "🎤"}
      </button>
      {error && <span className="voice-input__error">{error}</span>}
    </span>
  );
}
