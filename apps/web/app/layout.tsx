import type { Metadata } from "next"
import { ThemeProvider } from "@/components/layout/theme-provider"
import "./globals.css"

export const metadata: Metadata = {
  title: "STRIX — Cyber Threat Intelligence Platform",
  description: "Clinical Sentinel Vigilance System",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen">
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  )
}
