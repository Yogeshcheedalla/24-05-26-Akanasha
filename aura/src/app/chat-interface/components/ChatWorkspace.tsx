'use client';

import React, { useState } from 'react';
import ConversationSidebar from './ConversationSidebar';
import ChatThread from './ChatThread';
import ContextPanel from './ContextPanel';
import PromptTemplateModal from './PromptTemplateModal';
import { PanelLeft } from 'lucide-react';

function createSessionId() {
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function ChatWorkspace() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [contextPanelOpen, setContextPanelOpen] = useState(false);
  const [sessionId, setSessionId] = useState('default');
  const [chatStats, setChatStats] = useState({ messages: 0, contextUnits: 0 });
  const [isPromptModalOpen, setIsPromptModalOpen] = useState(false);

  const startNewChat = (nextSessionId?: string) => {
    setSessionId(nextSessionId ?? createSessionId());
    setIsPromptModalOpen(false);
  };

  const handleStatsChange = React.useCallback((messages: number, contextUnits: number) => {
    setChatStats((previous) => {
      if (previous.messages === messages && previous.contextUnits === contextUnits) {
        return previous;
      }
      return { messages, contextUnits };
    });
  }, []);

  React.useEffect(() => {
    if (sessionId !== 'default') {
      sessionStorage.setItem('akansha-current-session', sessionId);
    }
  }, [sessionId]);

  React.useEffect(() => {
    const handleTogglePanel = () => {
      setContextPanelOpen((open) => !open);
    };
    const handleTogglePrompts = () => {
      setIsPromptModalOpen(true);
    };
    const handleSelectSession = (event: Event) => {
      const session = (event as CustomEvent<string>).detail;
      if (session) setSessionId(session);
    };

    const handleNewChatWithDetail = (event: Event) => {
      const nextSessionId = (event as CustomEvent<string | undefined>).detail;
      startNewChat(nextSessionId);
    };

    window.addEventListener('akansha-new-chat', handleNewChatWithDetail);
    window.addEventListener('akansha-toggle-panel', handleTogglePanel);
    window.addEventListener('akansha-toggle-prompts', handleTogglePrompts);
    window.addEventListener('akansha-select-session', handleSelectSession);

    const pendingSession = sessionStorage.getItem('akansha-active-session');
    if (pendingSession) {
      setSessionId(pendingSession);
      sessionStorage.removeItem('akansha-active-session');
    } else {
      setSessionId(sessionStorage.getItem('akansha-current-session') || createSessionId());
    }

    if (sessionStorage.getItem('akansha-open-memory') === 'true') {
      setContextPanelOpen(true);
      sessionStorage.removeItem('akansha-open-memory');
    }

    if (sessionStorage.getItem('akansha-open-prompts') === 'true') {
      setIsPromptModalOpen(true);
      sessionStorage.removeItem('akansha-open-prompts');
    }

    return () => {
      window.removeEventListener('akansha-new-chat', handleNewChatWithDetail);
      window.removeEventListener('akansha-toggle-panel', handleTogglePanel);
      window.removeEventListener('akansha-toggle-prompts', handleTogglePrompts);
      window.removeEventListener('akansha-select-session', handleSelectSession);
    };
  }, []);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Conversation sidebar */}
      {sidebarOpen && (
        <div className="hidden xl:flex w-64 shrink-0 border-r border-border flex-col bg-card/50">
          <ConversationSidebar
            activeSessionId={sessionId}
            onNewChat={startNewChat}
            onSessionChange={setSessionId}
          />
        </div>
      )}

      <div className="hidden xl:flex w-11 shrink-0 border-r border-border bg-card/30 items-start justify-center pt-3">
        <button
          onClick={() => setSidebarOpen((open) => !open)}
          className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors bg-card/80 backdrop-blur"
          title={sidebarOpen ? 'Hide conversations' : 'Show conversations'}
          aria-label={sidebarOpen ? 'Hide conversations' : 'Show conversations'}
        >
          <PanelLeft
            size={16}
            className={`transition-transform duration-200 ${sidebarOpen ? '' : 'rotate-180'}`}
          />
        </button>
      </div>

      {/* Left memory/context drawer */}
      {contextPanelOpen && (
        <div className="hidden lg:flex w-80 shrink-0 border-r border-border flex-col bg-card/50">
          <ContextPanel
            onClose={() => setContextPanelOpen(false)}
            messageCount={chatStats.messages}
            contextUnits={chatStats.contextUnits}
          />
        </div>
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        <ChatThread
          key={sessionId}
          sessionId={sessionId}
          onStatsChange={handleStatsChange}
        />
      </div>
      {/* Modals */}
      <PromptTemplateModal
        open={isPromptModalOpen}
        onClose={() => setIsPromptModalOpen(false)}
        onSelect={(prompt) => {
          // This will be handled by a global chat bar event or ref
          window.dispatchEvent(new CustomEvent('akansha-apply-prompt', { detail: prompt }));
          setIsPromptModalOpen(false);
        }}
      />
    </div>
  );
}
