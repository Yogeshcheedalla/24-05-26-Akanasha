'use client';

import React, { useState, useRef, useCallback } from 'react';
import { Paperclip, Mic, MicOff, Send, Square, BookMarked, Image as ImageIcon, X, FileText } from 'lucide-react';
import {
  expandSlashCommand,
  getSlashCommandSuggestions,
  type SlashCommandDefinition,
} from '@/lib/slashCommands';


interface ChatComposerProps {
  onSend: (content: string, attachments?: File[]) => void;
  onOpenPromptLibrary: () => void;
  isStreaming: boolean;
  selectedModel: string;
  onToggleMic?: () => void;
  isListening?: boolean;
}

export default function ChatComposer({ onSend, onOpenPromptLibrary, isStreaming, onToggleMic, isListening }: ChatComposerProps) {
  const [content, setContent] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedSlashIndex, setSelectedSlashIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const shouldRefocusAfterStreamRef = useRef(false);
  const slashSuggestions = React.useMemo(
    () => getSlashCommandSuggestions(content).slice(0, 8),
    [content]
  );
  const showSlashMenu = slashSuggestions.length > 0 && content.trimStart().startsWith('/');

  React.useEffect(() => {
    const handleApplyPrompt = (e: any) => {
      const promptText = e.detail;
      setContent(promptText);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
        textareaRef.current.focus();
      }
    };
    window.addEventListener('akansha-apply-prompt', handleApplyPrompt);
    return () => window.removeEventListener('akansha-apply-prompt', handleApplyPrompt);
  }, []);

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setContent(e.target.value);
    setSelectedSlashIndex(0);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  const focusAndResize = useCallback(() => {
    requestAnimationFrame(() => {
      if (!textareaRef.current) return;
      textareaRef.current.focus();
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    });
  }, []);

  React.useEffect(() => {
    if (isStreaming || !shouldRefocusAfterStreamRef.current) return;
    shouldRefocusAfterStreamRef.current = false;
    focusAndResize();
  }, [focusAndResize, isStreaming]);

  const applySlashSuggestion = useCallback(
    (command: SlashCommandDefinition) => {
      const trimmed = content.trimStart();
      const remainder = trimmed.replace(/^\/\S*\s*/, '').trim();
      setContent(`/${command.name}${remainder ? ` ${remainder}` : ' '}`);
      setSelectedSlashIndex(0);
      focusAndResize();
    },
    [content, focusAndResize]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashMenu) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedSlashIndex((index) => (index + 1) % slashSuggestions.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedSlashIndex((index) => (index - 1 + slashSuggestions.length) % slashSuggestions.length);
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        applySlashSuggestion(slashSuggestions[selectedSlashIndex] || slashSuggestions[0]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setContent('');
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!content.trim() || isStreaming) return;
    shouldRefocusAfterStreamRef.current = true;
    onSend(expandSlashCommand(content), attachments.length > 0 ? attachments : undefined);
    setContent('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    focusAndResize();
  };

  const handleFileSelect = (files: FileList | null) => {
    if (!files) return;
    const newFiles = Array.from(files).slice(0, 5);
    setAttachments(prev => [...prev, ...newFiles].slice(0, 5));
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileSelect(e.dataTransfer.files);
  }, []);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const removeAttachment = (index: number) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
  };

  const getFileIcon = (file: File) => {
    if (file.type.startsWith('image/')) return <ImageIcon size={12} className="text-blue-400" />;
    return <FileText size={12} className="text-muted-foreground" />;
  };

  return (
    <div className="px-4 pb-4 pt-2">
      {isDragging && (
        <div className="absolute inset-4 rounded-xl border-2 border-dashed border-[#6C47FF] bg-[#6C47FF]/5 z-10 flex items-center justify-center pointer-events-none">
          <p className="text-sm font-medium text-[#6C47FF]">Drop files to attach</p>
        </div>
      )}

      <div
        className={`
          relative border rounded-2xl bg-card transition-all duration-150
          ${isDragging ? 'border-[#6C47FF]' : 'border-border'}
          focus-within:border-[#6C47FF]/50 focus-within:ring-1 focus-within:ring-[#6C47FF]/20
        `}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 px-4 pt-3">
            {attachments.map((file, i) => (
              <div key={`attachment-${i}-${file.name}`} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-muted border border-border text-xs group">
                {getFileIcon(file)}
                <span className="font-mono text-foreground max-w-[120px] truncate">{file.name}</span>
                <span className="text-muted-foreground">{(file.size / 1024).toFixed(0)}KB</span>
                <button onClick={() => removeAttachment(i)} className="text-muted-foreground hover:text-red-500 transition-colors ml-1">
                  <X size={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        {isListening && (
          <div className="flex items-center gap-3 px-4 pt-3">
            <div className="flex items-center gap-1">
              {[0, 1, 2, 3, 4].map(i => (
                <div
                  key={`wave-${i}`}
                  className="w-1 bg-red-500 rounded-full waveform-bar"
                  style={{ animationDelay: `${i * 0.1}s` }}
                />
              ))}
            </div>
            <span className="text-xs text-red-500 font-medium animate-pulse">Listening...</span>
          </div>
        )}

        {showSlashMenu && (
          <div className="mx-3 mt-3 rounded-2xl border border-[#6C47FF]/30 bg-background/95 shadow-2xl shadow-[#6C47FF]/10 overflow-hidden animate-fade-in">
            <div className="flex items-center justify-between px-3 py-2 border-b border-border/70">
              <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                Slash commands
              </span>
              <span className="text-[11px] text-muted-foreground">Use arrows, Tab, or click</span>
            </div>
            <div className="max-h-72 overflow-y-auto scrollbar-thin p-1.5">
              {slashSuggestions.map((command, index) => (
                <button
                  key={`slash-${command.name}`}
                  type="button"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    applySlashSuggestion(command);
                  }}
                  className={`w-full text-left rounded-xl px-3 py-2.5 transition-colors ${
                    index === selectedSlashIndex
                      ? 'bg-[#6C47FF]/15 text-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono text-sm text-[#8F72FF]">/{command.name}</span>
                    <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                      {command.category}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed">{command.description}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        <textarea
          ref={textareaRef}
          value={content}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Message Akansha... Type / for commands"
          rows={1}
          className="w-full bg-transparent px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground resize-none focus:outline-none leading-relaxed min-h-[52px]"
          readOnly={isStreaming}
          aria-disabled={isStreaming}
        />

        <div className="flex items-center justify-between px-3 pb-3">
          <div className="flex items-center gap-1">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,.pdf,.txt,.md,.ts,.tsx,.js,.jsx,.py,.json,.csv"
              className="hidden"
              onChange={e => handleFileSelect(e.target.files)}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              title="Attach files"
            >
              <Paperclip size={16} />
            </button>
            <button
              onClick={onOpenPromptLibrary}
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              title="Prompt templates"
            >
              <BookMarked size={16} />
            </button>
            {onToggleMic && (
              <button
                onClick={onToggleMic}
                className={`p-2 rounded-lg transition-colors ${
                  isListening
                    ? 'bg-red-500/10 text-red-500 hover:bg-red-500/20' :'hover:bg-muted text-muted-foreground hover:text-foreground'
                }`}
                title={isListening ? 'Stop listening' : 'Voice input'}
              >
                {isListening ? <MicOff size={16} /> : <Mic size={16} />}
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground/60 hidden sm:block">
              {content.length > 0 && `${content.length} chars`}
            </span>
            {isStreaming ? (
              <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-500 text-xs font-medium hover:bg-red-500/20 transition-colors">
                <Square size={12} fill="currentColor" />
                Stop
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!content.trim()}
                className={`
                  flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all duration-150 active:scale-95
                  ${content.trim()
                    ? 'bg-[#6C47FF] hover:bg-[#5A35EE] text-white shadow-sm shadow-[#6C47FF]/20'
                    : 'bg-muted text-muted-foreground cursor-not-allowed'
                  }
                `}
              >
                <Send size={13} />
                Send
              </button>
            )}
          </div>
        </div>
      </div>

      <p className="text-center text-xs text-muted-foreground/40 mt-2">
        Akansha can make mistakes. Verify important information.
      </p>
    </div>
  );
}
