import { useRef, useState } from "react";

interface Props {
  onUpload: (file: File) => Promise<void>;
  disabled: boolean;
}

const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg"];

export function DocumentUpload({ onUpload, disabled }: Props) {
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-selecting the same file later
    if (!file) return;

    if (!ACCEPTED_TYPES.includes(file.type)) {
      window.alert("Please upload a PDF, PNG, or JPEG file.");
      return;
    }

    setUploading(true);
    try {
      await onUpload(file);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="document-upload">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(",")}
        onChange={handleChange}
        disabled={disabled || uploading}
        id="document-upload-input"
        className="document-upload__input"
      />
      <label htmlFor="document-upload-input" className="document-upload__label">
        {uploading ? "Reading document…" : "📎 Upload a plan, NOC letter, or certificate"}
      </label>
    </div>
  );
}
