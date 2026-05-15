import React from 'react';
import AppLayout from '@/components/AppLayout';
import { AkanshaAssistant } from '@/components/assistant/AkanshaAssistant';

export default function VoiceAssistantPage() {
  return (
    <AppLayout activePath="/voice-assistant">
      <div className="min-h-full scroll-smooth bg-[radial-gradient(circle_at_top,_rgba(108,71,255,0.22),_transparent_28%),linear-gradient(180deg,_#020617_0%,_#0f172a_100%)] px-4 py-6 pb-16 lg:px-8">
        <div className="mx-auto w-full max-w-[1600px]">
          <div className="relative">
            <AkanshaAssistant />
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
