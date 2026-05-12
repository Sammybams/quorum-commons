import "./globals.css";
import type { ReactNode } from "react";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
const themeInitScript = `
(() => {
  try {
    const stored = window.localStorage.getItem("quorum-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = stored === "light" || stored === "dark" ? stored : (prefersDark ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  } catch (error) {
    document.documentElement.dataset.theme = "light";
    document.documentElement.style.colorScheme = "light";
  }
})();
`;

export const metadata = {
  metadataBase: new URL(APP_URL),
  title: "Quorum",
  description: "Student body operating system",
  icons: {
    icon: "/brand/quorum-favicon.svg",
    shortcut: "/brand/quorum-favicon.svg",
  },
  openGraph: {
    title: "Quorum",
    description: "Where student bodies get things done.",
    images: ["/brand/quorum-icon.svg"],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {children}
      </body>
    </html>
  );
}
