import { Paperclip, Send } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "../../design-system/components/Button";
import { VoiceInputButton } from "../../components/VoiceInputButton";
import "./Composer.css";

interface Props {
  onSend: (text: string) => void;
  onUploadDocument: (file: File) => Promise<void>;
  disabled: boolean;
  placeholder: string;
}

const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg"];

export function Composer({ onSend, onUploadDocument, disabled, placeholder }: Props) {
  const [draft, setDraft] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = draft.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setDraft("");
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      window.alert("Please upload a PDF, PNG, or JPEG file.");
      return;
    }
    setUploading(true);
    try {
      await onUploadDocument(file);
    } finally {
      setUploading(false);
    }
  };

  return (
    <form className="ds-composer" onSubmit={handleSubmit}>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(",")}
        className="ds-composer__file-input"
        onChange={handleFileChange}
        disabled={disabled || uploading}
        aria-label="Upload a plan, NOC letter, or certificate"
      />
      <button
        type="button"
        className="ds-composer__icon-btn"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled || uploading}
        aria-label="Upload a document"
        title={uploading ? "Reading document…" : "Upload a plan, NOC letter, or certificate"}
      >
        <Paperclip aria-hidden="true" />
      </button>
      <VoiceInputButton onResult={(text) => setDraft((prev) => (prev ? `${prev} ${text}` : text))} disabled={disabled} />
      <input
        type="text"
        className="ds-composer__input"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
      <Button type="submit" variant="primary" size="sm" icon={<Send />} disabled={disabled || !draft.trim()}>
        Send
      </Button>
    </form>
  );
}
