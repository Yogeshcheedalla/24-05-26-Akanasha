import React from 'react';
import type { Metadata, Viewport } from 'next';
import '../styles/tailwind.css';

import PlannerReminderBridge from '../components/planner/PlannerReminderBridge';
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

export const metadata: Metadata = {
  title: 'Akansha — Multi-Model AI Chat with Persistent Memory',
  description: 'Akansha is a multi-model AI chat platform with persistent memory, RAG document support, prompt libraries, and voice I/O — built for developers and power users.',
  icons: {
    icon: [{ url: '/favicon.ico', type: 'image/x-icon' }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}
        <PlannerReminderBridge />

        <script type="module" async src="https://static.rocket.new/rocket-web.js?_cfg=https%3A%2F%2Fakansha4719back.builtwithrocket.new&_be=https%3A%2F%2Fappanalytics.rocket.new&_v=0.1.18" />
        <script type="module" defer src="https://static.rocket.new/rocket-shot.js?v=0.0.2" /></body>
    </html>
  );
}
