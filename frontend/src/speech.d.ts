// TypeScript's DOM lib already declares SpeechRecognitionEvent,
// SpeechRecognitionErrorEvent, SpeechRecognitionResult(List), and
// SpeechRecognitionErrorCode - but NOT the SpeechRecognition interface
// itself or the (still non-standard/webkit-prefixed in most browsers)
// constructors on Window. Only those missing pieces are declared here.

interface SpeechRecognition extends EventTarget {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

interface Window {
  SpeechRecognition?: new () => SpeechRecognition;
  webkitSpeechRecognition?: new () => SpeechRecognition;
}
