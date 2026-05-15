'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Clock3, Loader2, RefreshCw, Send, Sparkles, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

interface BrowserAutomationStatus {
  disclaimer: string;
  scheduled_actions: Array<{
    id: string;
    action: string;
    label: string;
    target?: string;
    run_at: string;
    background: boolean;
    status: string;
    created_at: string;
    note: string;
  }>;
}

interface BrowserPromptResponse {
  success: boolean;
  scheduled: boolean;
  message: string;
  note?: string;
  plan?: {
    summary: string;
    steps: Array<{
      action: string;
      target?: string;
    }>;
  };
}

const PROMPT_EXAMPLES = [
  'Open google.com and search for "formal president of India"',
  'Open linkedin.com and type my message in the active field',
  'Open instagram.com, fill username yogesh and password secret123, then login',
  'Open codechef.com with username kl33034 password @Chintu05',
  'Open youtube and play Durandhar songs',
  'Open notepad and type my interview checklist',
  'Open calculator',
  'Open file explorer',
  'Open vscode and type console.log("hello")',
  'Run command dir in powershell',
  'Open downloads folder and convert all pdfs to ppts and create another folder in the same',
];

export function BrowserAutomationCenter() {
  const [status, setStatus] = useState<BrowserAutomationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('Open google.com and search for "formal president of India"');
  const [runAt, setRunAt] = useState('');
  const [lastPlan, setLastPlan] = useState<BrowserPromptResponse['plan'] | null>(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/automation/browser/status');
      if (!res.ok) {
        throw new Error('Could not load browser automation status');
      }
      const data: BrowserAutomationStatus = await res.json();
      setStatus(data);
    } catch (error) {
      console.error('Failed to load browser automation status:', error);
      toast.error('Could not load browser automation');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const runPrompt = useCallback(
    async (scheduled: boolean) => {
      if (!prompt.trim()) {
        toast.info('Type the task you want Akansha to complete');
        return;
      }

      if (scheduled && !runAt) {
        toast.info('Choose a custom time first');
        return;
      }

      setRunning(true);
      try {
        const res = await fetch('http://localhost:8000/api/automation/browser/prompt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt,
            run_at: scheduled ? runAt : null,
            background: true,
          }),
        });
        const data: BrowserPromptResponse = await res.json();
        if (!res.ok) {
          throw new Error((data as any).detail ?? 'Automation failed');
        }

        setLastPlan(data.plan ?? null);
        toast.success(data.message);
        if (scheduled) {
          setRunAt('');
        }
        await loadStatus();
      } catch (error) {
        console.error('Failed to run freeform automation prompt:', error);
        toast.error(error instanceof Error ? error.message : 'Automation failed');
      } finally {
        setRunning(false);
      }
    },
    [loadStatus, prompt, runAt]
  );

  const deleteScheduled = useCallback(
    async (id: string) => {
      setDeletingId(id);
      try {
        const res = await fetch(`http://localhost:8000/api/automation/browser/scheduled/${id}`, {
          method: 'DELETE',
        });
        if (!res.ok) {
          throw new Error('Could not remove scheduled action');
        }
        toast.success('Scheduled automation removed');
        await loadStatus();
      } catch (error) {
        console.error('Failed to remove scheduled automation:', error);
        toast.error('Could not remove scheduled automation');
      } finally {
        setDeletingId(null);
      }
    },
    [loadStatus]
  );

  return (
    <section className="rounded-3xl border border-white/10 bg-slate-900/85 p-6 shadow-[0_30px_90px_rgba(15,23,42,0.45)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Browser task center</p>
          <h1 className="mt-2 text-2xl font-semibold text-white">One prompt box for browser and desktop automation</h1>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-300">
            Type what you want done. Akansha now treats browser permissions as already enabled in this
            page and tries to interpret the important part of your instruction instead of forcing you
            to pick YouTube or flip switches first. It can now open desktop apps too, then type into
            the active app window when your instruction asks for it. It can also open folders, run
            explicit commands, and handle file-work prompts like PDF-to-PPT batch conversion.
          </p>
        </div>

        <button
          onClick={() => void loadStatus()}
          className="rounded-full border border-white/10 bg-slate-950 p-2 text-slate-300 transition-colors hover:bg-slate-800"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
        </button>
      </div>

      <div className="mt-6 rounded-[28px] border border-[#6c47ff]/20 bg-[linear-gradient(180deg,rgba(28,25,68,0.9),rgba(2,6,23,0.96))] p-6">
        <div className="flex items-center gap-2 text-white">
          <Sparkles size={16} className="text-[#a88dff]" />
          <p className="text-sm font-medium">Describe the task once</p>
        </div>
        <p className="mt-2 text-sm leading-6 text-slate-300">
          Example: open a site, search for something, type a message, fill credentials, clear a draft,
          close a tab, or open a desktop app like Notepad, Calculator, Explorer, or VS Code. Akansha
          will try to open the right place and use the most important text from your prompt.
        </p>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {PROMPT_EXAMPLES.map((example) => (
            <button
              key={example}
              onClick={() => setPrompt(example)}
              className="rounded-2xl border border-white/10 bg-slate-950/55 px-4 py-3 text-left text-xs leading-5 text-slate-300 transition-colors hover:bg-slate-900"
            >
              {example}
            </button>
          ))}
        </div>

        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={5}
          placeholder="Type the browser task you want Akansha to complete..."
          className="mt-5 w-full rounded-[24px] border border-white/10 bg-slate-950/75 px-5 py-4 text-sm leading-7 text-white outline-none transition-colors placeholder:text-slate-500 focus:border-[#6c47ff]/45"
        />

        <div className="mt-4 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <label className="text-xs uppercase tracking-[0.2em] text-slate-500">Custom run time</label>
            <input
              type="datetime-local"
              value={runAt}
              onChange={(event) => setRunAt(event.target.value)}
              className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/75 px-4 py-3 text-sm text-white outline-none transition-colors focus:border-[#6c47ff]/45"
            />
          </div>
          <div className="rounded-2xl border border-white/10 bg-slate-950/50 px-4 py-3 text-sm text-slate-300">
            <p className="font-medium text-white">What it understands</p>
            <p className="mt-2 leading-6">
              Open any link, search the important phrase, type into the focused field, fill simple
              username and password flows even if you just write the credentials directly, clear drafts,
              open desktop apps, open folders and paths, run explicit commands, batch-convert PDFs to
              PPTX files, and handle basic tab or window control.
            </p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <button
            onClick={() => void runPrompt(false)}
            className="inline-flex items-center gap-2 rounded-full bg-[#6c47ff] px-5 py-3 text-sm font-medium text-white transition-transform hover:scale-[1.01]"
          >
            {running ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            Run this task
          </button>
          <button
            onClick={() => void runPrompt(true)}
            className="rounded-full border border-white/10 bg-slate-950/75 px-5 py-3 text-sm text-slate-300 hover:bg-slate-900"
          >
            Save with custom time
          </button>
          <button
            onClick={() => {
              setPrompt('');
              setRunAt('');
            }}
            className="rounded-full border border-white/10 bg-slate-950/75 px-5 py-3 text-sm text-slate-300 hover:bg-slate-900"
          >
            Clear
          </button>
        </div>
      </div>

      {lastPlan && (
        <div className="mt-6 rounded-[28px] border border-white/10 bg-slate-950/60 p-5">
          <p className="text-sm font-medium text-white">Latest interpreted plan</p>
          <p className="mt-2 text-sm text-slate-300">{lastPlan.summary}</p>
          <div className="mt-4 grid gap-2">
            {lastPlan.steps.map((step, index) => (
              <div
                key={`${step.action}-${index}`}
                className="rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-sm text-slate-300"
              >
                <span className="font-medium text-white">{index + 1}. {step.action}</span>
                {step.target ? <span className="text-slate-400"> — {step.target}</span> : null}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(2,6,23,0.96))] p-5">
        <div className="flex items-center gap-2">
          <Clock3 size={16} className="text-sky-300" />
          <p className="text-sm font-medium text-white">Saved browser and desktop automations</p>
        </div>
        <p className="mt-2 text-sm leading-6 text-slate-300">
          These are the custom-time automations you saved from the one prompt box.
        </p>

        <div className="mt-5 grid gap-3">
          {status?.scheduled_actions.length ? (
            status.scheduled_actions.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium text-white">{item.label}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {item.target ? item.target : 'No extra target captured'}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {`Runs at ${new Date(item.run_at).toLocaleString()} · ${item.background ? 'background preference on' : 'normal open'
                      }`}
                  </p>
                </div>
                <button
                  onClick={() => void deleteScheduled(item.id)}
                  className="rounded-full border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-xs text-rose-100 hover:bg-rose-400/15"
                >
                  {deletingId === item.id ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <>
                      <Trash2 size={12} className="mr-1 inline" />
                      Remove
                    </>
                  )}
                </button>
              </div>
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/40 px-4 py-8 text-center text-sm text-slate-400">
              No saved automations yet.
            </div>
          )}
        </div>
      </div>

      {status?.disclaimer && (
        <div className="mt-6 rounded-2xl border border-amber-400/15 bg-amber-400/5 px-4 py-3 text-sm text-amber-100">
          {status.disclaimer}
        </div>
      )}
    </section>
  );
}
