import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'RedNote AI Chat',
  description: 'Enter a RedNote post link to chat with the content',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
