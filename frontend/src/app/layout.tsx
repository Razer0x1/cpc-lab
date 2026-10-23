import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "CPC Lab — Cross-Paradigm Compression",
    template: "%s · CPC Lab",
  },
  description:
    "CPC Lab: a research platform for cross-paradigm neural network compression — literature catalog, hypotheses, reproducible experiments, benchmarks, and reports.",
  applicationName: "CPC Lab",
  icons: { icon: "/logo-mark.svg" },
};

export const viewport: Viewport = {
  themeColor: "#04060F",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
