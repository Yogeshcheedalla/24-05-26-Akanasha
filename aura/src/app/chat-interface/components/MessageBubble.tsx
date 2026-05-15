'use client';

import React, { useState } from 'react';
import { Copy, RotateCcw, ThumbsUp, ThumbsDown, Brain, Check, Code2, Pin, GitBranch } from 'lucide-react';
import { toast } from 'sonner';
import type { Message } from './ChatThread';

interface MessageBubbleProps {
  message: Message;
  onTogglePin?: (message: Message) => void;
  onContinueFrom?: (message: Message) => void;
  isBranchAnchor?: boolean;
}

const MODEL_BADGES: Record<string, { label: string; color: string }> = {
  'GPT-4o': { label: 'Akansha', color: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20' },
  'Claude 3.5': { label: 'Claude 3.5', color: 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20' },
  'Gemini 1.5': { label: 'Gemini 1.5', color: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20' },
};

function cleanUrl(url: string) {
  return url.replace(/[),.;:!?]+$/, '');
}

function openLinkOnModifier(event: React.MouseEvent<HTMLAnchorElement>, url: string) {
  if (!event.ctrlKey && !event.metaKey) return;
  event.preventDefault();
  window.open(url, '_blank', 'noopener,noreferrer');
}

function renderLink(label: React.ReactNode, url: string, key: string) {
  const href = cleanUrl(url);
  return (
    <a
      key={key}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(event) => openLinkOnModifier(event, href)}
      className="font-medium text-[#8B6CFF] underline underline-offset-2 hover:text-[#A99AFF]"
    >
      {label}
    </a>
  );
}

function renderInlineText(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const pattern = /(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|https?:\/\/[^\s<]+)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }

    const raw = match[0];
    const markdownLabel = match[2];
    const markdownUrl = match[3];
    const href = markdownUrl || raw;
    nodes.push(renderLink(markdownLabel || cleanUrl(raw), href, `${keyPrefix}-link-${match.index}`));
    cursor = match.index + raw.length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }

  return nodes;
}

function renderInlineSegment(segment: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  segment.split(/(`[^`]+`|\*\*.*?\*\*)/g).forEach((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (!part) return;
    if (part.startsWith('`') && part.endsWith('`')) {
      nodes.push(
        <code key={key} className="px-1.5 py-0.5 rounded bg-muted font-mono text-xs text-[#6C47FF] dark:text-[#9B7FFF]">
          {part.slice(1, -1)}
        </code>
      );
      return;
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      nodes.push(
        <strong key={key} className="font-semibold text-foreground">
          {renderInlineText(part.slice(2, -2), `${key}-bold`)}
        </strong>
      );
      return;
    }
    nodes.push(...renderInlineText(part, key));
  });
  return nodes;
}

function formatContent(content: string): React.ReactNode[] {
  const parts = content.split(/(```[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (part.startsWith('```')) {
      const lines = part.split('\n');
      const lang = lines[0].replace('```', '').trim() || 'code';
      const code = lines.slice(1, -1).join('\n');
      return (
        <div key={`code-block-${i}`} className="my-3 rounded-xl overflow-hidden border border-border bg-zinc-950 dark:bg-zinc-900">
          <div className="flex items-center justify-between px-4 py-2 bg-zinc-900 dark:bg-zinc-800 border-b border-border">
            <div className="flex items-center gap-2">
              <Code2 size={13} className="text-muted-foreground" />
              <span className="text-xs font-mono text-muted-foreground">{lang}</span>
            </div>
            <CopyCodeButton code={code} />
          </div>
          <pre className="p-4 overflow-x-auto scrollbar-thin text-xs font-mono text-zinc-200 leading-relaxed">
            <code>{code}</code>
          </pre>
        </div>
      );
    }
    const lines = part.split('\n');
    return (
      <span key={`text-${i}`}>
        {lines.map((line, li) => {
          return (
            <span key={`line-${li}`}>
              {renderInlineSegment(line, `line-${i}-${li}`)}
              {li < lines.length - 1 && <br />}
            </span>
          );
        })}
      </span>
    );
  });
}

function CopyCodeButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={handleCopy} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
      {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
      <span>{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
}

function formatMessageDateTime(date: Date): string {
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}

export default function MessageBubble({ message, onTogglePin, onContinueFrom, isBranchAnchor }: MessageBubbleProps) {
  const [liked, setLiked] = useState<boolean | null>(null);
  const isUser = message.role === 'user';
  const badge = message.model ? MODEL_BADGES[message.model] : null;

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    toast.success('Message copied to clipboard');
  };

  return (
    <div
      id={`chat-message-${message.id}`}
      className={`flex gap-3 py-3 group scroll-mt-32 ${isUser ? 'flex-row-reverse' : 'flex-row'} ${
        isBranchAnchor ? 'rounded-2xl bg-[#6C47FF]/5 ring-1 ring-[#6C47FF]/20 px-2' : ''
      }`}
    >
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-xs font-semibold mt-0.5 ${
        isUser
          ? 'bg-gradient-to-br from-[#6C47FF] to-[#00C9A7] text-white'
          : 'bg-gradient-to-br from-zinc-700 to-zinc-600 text-zinc-200 border border-border'
      }`}>
        {isUser ? 'A' : 'AI'}
      </div>

      <div className={`flex flex-col gap-1 max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Header row */}
        <div className={`flex items-center gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
          <span className={`text-xs font-medium ${isUser ? 'text-foreground' : 'text-green-600 dark:text-green-400'}`}>
            {isUser ? 'You' : 'Akansha'}
          </span>
          {badge && (
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${badge.color}`}>
              {badge.label}
            </span>
          )}
          {message.memoryRefs && message.memoryRefs.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-[#00C9A7] px-2 py-0.5 rounded-full bg-[#00C9A7]/10 border border-[#00C9A7]/20">
              <Brain size={10} />
              Memory
            </span>
          )}
          <span
            className="text-xs text-muted-foreground/60"
            title={formatMessageDateTime(message.timestamp)}
          >
            {formatTime(message.timestamp)}
          </span>
          {message.pinned && (
            <span className="flex items-center gap-1 text-xs text-amber-400 px-2 py-0.5 rounded-full bg-amber-400/10 border border-amber-400/20">
              <Pin size={10} fill="currentColor" />
              Pinned
            </span>
          )}
        </div>

        {/* Attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-1">
            {message.attachments.map(att => (
              <div key={att.id} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[#6C47FF]/10 border border-[#6C47FF]/20 text-xs">
                {att.previewUrl ? (
                  <img
                    src={att.previewUrl}
                    alt={att.name}
                    className="h-10 w-14 rounded-md object-cover border border-[#6C47FF]/20"
                  />
                ) : (
                  <Code2 size={12} className="text-[#6C47FF]" />
                )}
                <div className="min-w-0">
                  <span className="block font-mono text-[#6C47FF] dark:text-[#9B7FFF] max-w-44 truncate">{att.name}</span>
                  <span className="block text-muted-foreground">{att.size}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Content bubble */}
        <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-[#6C47FF] text-white rounded-tr-sm'
            : 'bg-card border border-border text-foreground rounded-tl-sm'
        }`}>
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <div className="prose-sm">
              {formatContent(message.content)}
              {message.isStreaming && <span className="streaming-cursor" />}
            </div>
          )}
        </div>

        {/* Token count */}
        {message.tokenCount && !isUser && (
          <span className="text-xs text-muted-foreground/50 font-mono tabular-nums px-1">
            {message.tokenCount} tokens
          </span>
        )}

        {/* Actions (AI messages only) */}
        {!message.isStreaming && (
          <div className={`flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ${isUser ? 'flex-row-reverse' : ''}`}>
            <button onClick={handleCopy} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Copy message">
              <Copy size={13} />
            </button>
            {onTogglePin && (
              <button
                onClick={() => onTogglePin(message)}
                className={`p-1.5 rounded-lg transition-colors ${
                  message.pinned
                    ? 'text-amber-400 bg-amber-400/10'
                    : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                }`}
                title={message.pinned ? 'Unpin message' : 'Pin message'}
              >
                <Pin size={13} fill={message.pinned ? 'currentColor' : 'none'} />
              </button>
            )}
            {onContinueFrom && (
              <button
                onClick={() => onContinueFrom(message)}
                className={`p-1.5 rounded-lg transition-colors ${
                  isBranchAnchor
                    ? 'text-[#6C47FF] bg-[#6C47FF]/10'
                    : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                }`}
                title="Continue conversation from this message"
              >
                <GitBranch size={13} />
              </button>
            )}
            {!isUser && (
              <>
                <button className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="Regenerate">
                  <RotateCcw size={13} />
                </button>
                <button
                  onClick={() => setLiked(true)}
                  className={`p-1.5 rounded-lg transition-colors ${liked === true ? 'text-green-500 bg-green-500/10' : 'hover:bg-muted text-muted-foreground hover:text-foreground'}`}
                  title="Good response"
                >
                  <ThumbsUp size={13} />
                </button>
                <button
                  onClick={() => setLiked(false)}
                  className={`p-1.5 rounded-lg transition-colors ${liked === false ? 'text-red-500 bg-red-500/10' : 'hover:bg-muted text-muted-foreground hover:text-foreground'}`}
                  title="Bad response"
                >
                  <ThumbsDown size={13} />
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
