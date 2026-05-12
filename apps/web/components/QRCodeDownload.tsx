"use client";

import { useState } from "react";
import QRCode from "qrcode";

type Props = {
  url: string;
  filename: string;
  label?: string;
  className?: string;
};

export default function QRCodeDownload({ url, filename, label = "Download QR", className }: Props) {
  const [generating, setGenerating] = useState(false);

  async function handleDownload() {
    setGenerating(true);
    try {
      const dataUrl = await QRCode.toDataURL(url, {
        width: 512,
        margin: 2,
        color: {
          dark: "#1B5EF7",
          light: "#FFFFFF",
        },
        errorCorrectionLevel: "M",
      });

      const anchor = document.createElement("a");
      anchor.href = dataUrl;
      anchor.download = `${filename}-qr.png`;
      anchor.click();
    } finally {
      setGenerating(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleDownload}
      disabled={generating}
      className={className ?? "btn-ghost"}
      aria-label={`Download QR code for ${url}`}
    >
      <span className="material-symbols-outlined" aria-hidden="true">
        qr_code_2
      </span>
      {generating ? "Generating..." : label}
    </button>
  );
}
