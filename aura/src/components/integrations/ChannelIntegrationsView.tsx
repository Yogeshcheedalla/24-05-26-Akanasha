'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  AtSign,
  Camera,
  CheckCheck,
  Clock3,
  Copy,
  KeyRound,
  Loader2,
  MessageCircleMore,
  MessageSquareReply,
  PlugZap,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

const API_BASE = 'http://localhost:8000';

type PlatformKey = 'whatsapp' | 'instagram' | 'twitter' | 'telegram';

interface SocialFieldDefinition {
  key: string;
  label: string;
  required: boolean;
  secret: boolean;
  advanced?: boolean;
  auto?: boolean;
}

interface SocialPlatformStatus {
  key: PlatformKey;
  label: string;
  connected: boolean;
  verified: boolean;
  accent: string;
  setup_required: boolean;
  required_fields: string[];
  missing_fields: string[];
  configured_fields: string[];
  fields: SocialFieldDefinition[];
  config_preview: Record<string, string>;
  webhook_url: string;
  last_verified: string | null;
  verification_status: string;
  verification_detail?: string | null;
  account_label: string | null;
}

interface SocialInboxMessage {
  id: number;
  platform: PlatformKey;
  sender: string;
  content: string;
  intent: string;
  sentiment: string;
  is_read: boolean;
  timestamp: string;
  suggested_replies: string[];
}

interface SocialInboxResponse {
  platforms: SocialPlatformStatus[];
  messages: SocialInboxMessage[];
}

const PLATFORM_FALLBACKS: SocialPlatformStatus[] = [
  {
    key: 'whatsapp',
    label: 'WhatsApp',
    connected: false,
    verified: false,
    accent: '#25D366',
    setup_required: true,
    required_fields: ['phone_number_id', 'access_token'],
    missing_fields: ['phone_number_id', 'access_token'],
    configured_fields: [],
    fields: [
      { key: 'phone_number_id', label: 'Phone number ID', required: true, secret: false },
      { key: 'access_token', label: 'Cloud API access token', required: true, secret: true },
      { key: 'webhook_verify_token', label: 'Webhook verify token', required: false, secret: true, advanced: true, auto: true },
      { key: 'business_account_id', label: 'Business account ID', required: false, secret: false, advanced: true },
    ],
    config_preview: {},
    webhook_url: `${API_BASE}/api/social/webhook/whatsapp`,
    last_verified: null,
    verification_status: 'not_configured',
    verification_detail: null,
    account_label: null,
  },
  {
    key: 'instagram',
    label: 'Instagram',
    connected: false,
    verified: false,
    accent: '#F43F5E',
    setup_required: true,
    required_fields: ['page_access_token', 'instagram_business_account_id'],
    missing_fields: ['page_access_token', 'instagram_business_account_id'],
    configured_fields: [],
    fields: [
      { key: 'page_access_token', label: 'Page access token', required: true, secret: true },
      {
        key: 'instagram_business_account_id',
        label: 'Instagram business account ID',
        required: true,
        secret: false,
      },
      { key: 'webhook_verify_token', label: 'Webhook verify token', required: false, secret: true, advanced: true, auto: true },
      { key: 'app_secret', label: 'App secret', required: false, secret: true, advanced: true },
    ],
    config_preview: {},
    webhook_url: `${API_BASE}/api/social/webhook/instagram`,
    last_verified: null,
    verification_status: 'not_configured',
    verification_detail: null,
    account_label: null,
  },
  {
    key: 'twitter',
    label: 'X / Twitter',
    connected: false,
    verified: false,
    accent: '#60A5FA',
    setup_required: true,
    required_fields: ['bearer_token'],
    missing_fields: ['bearer_token'],
    configured_fields: [],
    fields: [
      { key: 'bearer_token', label: 'Bearer token', required: true, secret: true },
      { key: 'api_key', label: 'API key', required: false, secret: true, advanced: true },
      { key: 'api_secret', label: 'API secret', required: false, secret: true, advanced: true },
      { key: 'access_token', label: 'Access token', required: false, secret: true, advanced: true },
      { key: 'access_token_secret', label: 'Access token secret', required: false, secret: true, advanced: true },
    ],
    config_preview: {},
    webhook_url: `${API_BASE}/api/social/webhook/twitter`,
    last_verified: null,
    verification_status: 'not_configured',
    verification_detail: null,
    account_label: null,
  },
  {
    key: 'telegram',
    label: 'Telegram',
    connected: false,
    verified: false,
    accent: '#38BDF8',
    setup_required: true,
    required_fields: ['bot_token'],
    missing_fields: ['bot_token'],
    configured_fields: [],
    fields: [
      { key: 'bot_token', label: 'Bot token', required: true, secret: true },
      { key: 'default_chat_id', label: 'Default chat ID', required: false, secret: false, advanced: true },
      { key: 'webhook_secret', label: 'Webhook secret', required: false, secret: true, advanced: true, auto: true },
    ],
    config_preview: {},
    webhook_url: `${API_BASE}/api/social/webhook/telegram`,
    last_verified: null,
    verification_status: 'not_configured',
    verification_detail: null,
    account_label: null,
  },
];

const SOCIAL_INBOX_FALLBACK: SocialInboxResponse = {
  platforms: PLATFORM_FALLBACKS,
  messages: [],
};

const SETUP_GUIDES: Record<PlatformKey, { fields: string; steps: string[]; docsUrl: string }> = {
  telegram: {
    fields: '1 box: bot token',
    steps: ['Create a bot in Telegram with BotFather.', 'Paste the bot token here and save.', 'Use the webhook URL for live incoming messages.'],
    docsUrl: 'https://core.telegram.org/bots/api',
  },
  twitter: {
    fields: '1 box: bearer token',
    steps: ['Create an app in the X Developer Console.', 'Copy the Bearer Token for read/search access.', 'Use advanced OAuth tokens only for write/DM actions.'],
    docsUrl: 'https://docs.x.com/x-api/getting-started/getting-access-to-the-x-api',
  },
  whatsapp: {
    fields: '2 boxes: phone number ID + Cloud API access token',
    steps: ['Create a Meta app with WhatsApp Cloud API enabled.', 'Copy the phone number ID and access token from API setup.', 'Akansha generates the webhook verify token if you leave it blank.'],
    docsUrl: 'https://developers.facebook.com/docs/whatsapp/cloud-api/',
  },
  instagram: {
    fields: '2 boxes: page access token + Instagram business account ID',
    steps: ['Use an Instagram Business account connected to a Facebook Page.', 'Generate a Page Access Token with messaging permissions.', 'Paste the Instagram Business Account ID; Akansha handles the webhook secret.'],
    docsUrl: 'https://developers.facebook.com/docs/messenger-platform/instagram/',
  },
};

export function ChannelIntegrationsView() {
  const [socialInbox, setSocialInbox] = useState<SocialInboxResponse>(SOCIAL_INBOX_FALLBACK);
  const [socialLoading, setSocialLoading] = useState(false);
  const [busyPlatform, setBusyPlatform] = useState<string | null>(null);
  const [selectedReply, setSelectedReply] = useState<Record<number, string>>({});
  const [sendingReplyId, setSendingReplyId] = useState<number | null>(null);
  const [setupPlatform, setSetupPlatform] = useState<PlatformKey>('whatsapp');
  const [setupValues, setSetupValues] = useState<Record<string, Record<string, string>>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);

  const socialPlatformMeta = useMemo(
    () => ({
      whatsapp: { label: 'WhatsApp', icon: MessageCircleMore },
      instagram: { label: 'Instagram', icon: Camera },
      twitter: { label: 'X / Twitter', icon: AtSign },
      telegram: { label: 'Telegram', icon: Send },
    }),
    []
  );

  const activePlatform = socialInbox.platforms.find((platform) => platform.key === setupPlatform) ?? socialInbox.platforms[0];
  const visibleSetupFields = useMemo(
    () => activePlatform?.fields.filter((field) => showAdvanced || !field.advanced) ?? [],
    [activePlatform, showAdvanced]
  );
  const activeSetupGuide = activePlatform ? SETUP_GUIDES[activePlatform.key] : null;

  const loadSocialInbox = useCallback(async () => {
    setSocialLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/social/inbox`);
      if (!res.ok) {
        setSocialInbox(SOCIAL_INBOX_FALLBACK);
        return;
      }
      const data = (await res.json()) as SocialInboxResponse;
      setSocialInbox({
        platforms: data.platforms.length ? data.platforms : PLATFORM_FALLBACKS,
        messages: data.messages ?? [],
      });
    } catch (error) {
      console.warn('Failed to load social inbox:', error);
      setSocialInbox(SOCIAL_INBOX_FALLBACK);
    } finally {
      setSocialLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSocialInbox();
  }, [loadSocialInbox]);

  useEffect(() => {
    setShowAdvanced(false);
  }, [setupPlatform]);

  const updateSetupValue = useCallback((platform: PlatformKey, field: string, value: string) => {
    setSetupValues((previous) => ({
      ...previous,
      [platform]: {
        ...(previous[platform] ?? {}),
        [field]: value,
      },
    }));
  }, []);

  const copyText = useCallback(async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} copied`);
    } catch {
      toast.error(`Could not copy ${label}`);
    }
  }, []);

  const saveSocialPlatformSetup = useCallback(
    async (platform: PlatformKey, testConnection: boolean) => {
      setBusyPlatform(platform);
      try {
        const response = await fetch(`${API_BASE}/api/social/setup/${platform}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            config: setupValues[platform] ?? {},
            test_connection: testConnection,
          }),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail ?? `Could not configure ${platform}`);
        }

        toast.success(testConnection ? `${data.status.label} saved and tested` : `${data.status.label} saved`);
        setSetupValues((previous) => ({ ...previous, [platform]: {} }));
        await loadSocialInbox();
      } catch (error) {
        console.warn(`Failed to configure ${platform}:`, error);
        toast.error(error instanceof Error ? error.message : `Could not configure ${platform}`);
      } finally {
        setBusyPlatform(null);
      }
    },
    [loadSocialInbox, setupValues]
  );

  const testSocialPlatform = useCallback(
    async (platform: PlatformKey) => {
      setBusyPlatform(platform);
      try {
        const response = await fetch(`${API_BASE}/api/social/connect/${platform}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail ?? `Could not test ${platform}`);
        }
        toast.success(`${data.status.label} verified`);
        await loadSocialInbox();
      } catch (error) {
        console.warn(`Failed to test ${platform}:`, error);
        toast.error(error instanceof Error ? error.message : `Could not test ${platform}`);
      } finally {
        setBusyPlatform(null);
      }
    },
    [loadSocialInbox]
  );

  const disconnectSocialPlatform = useCallback(
    async (platform: PlatformKey) => {
      setBusyPlatform(platform);
      try {
        await fetch(`${API_BASE}/api/social/disconnect/${platform}`, { method: 'POST' });
        toast.success(`${platform} disconnected`);
        await loadSocialInbox();
      } catch (error) {
        console.warn(`Failed to disconnect ${platform}:`, error);
        toast.error(`Could not disconnect ${platform}`);
      } finally {
        setBusyPlatform(null);
      }
    },
    [loadSocialInbox]
  );

  const approveAndSendReply = useCallback(
    async (message: SocialInboxMessage) => {
      const reply = selectedReply[message.id] ?? message.suggested_replies[0] ?? '';
      if (!reply.trim()) {
        toast.info('Choose or write a reply first');
        return;
      }

      setSendingReplyId(message.id);
      try {
        const response = await fetch(`${API_BASE}/api/social/send`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message_id: message.id,
            platform: message.platform,
            sender: message.sender,
            reply,
            approved: true,
          }),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail ?? 'Reply could not be sent');
        }

        toast.success(data.status === 'sent' ? `Reply sent to ${message.sender}` : `Reply queued for ${message.sender}`);
        await loadSocialInbox();
      } catch (error) {
        console.warn('Failed to send approved reply:', error);
        toast.error(error instanceof Error ? error.message : 'Reply could not be sent');
      } finally {
        setSendingReplyId(null);
      }
    },
    [loadSocialInbox, selectedReply]
  );

  const connectedMessages = socialInbox.messages.filter((message) =>
    socialInbox.platforms.some((platform) => platform.key === message.platform && platform.connected)
  );

  return (
    <section className="rounded-3xl border border-white/10 bg-slate-900/85 p-6 shadow-[0_30px_90px_rgba(15,23,42,0.45)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Channel integrations</p>
          <h1 className="mt-2 text-2xl font-semibold text-white">
            Paste API tokens and connect Akansha to live channels
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
            WhatsApp, Instagram, X, and Telegram now use real credential forms, local token storage,
            webhook URLs, and connection testing. Akansha only sends replies after your approval.
          </p>
        </div>

        <button
          onClick={() => void loadSocialInbox()}
          className="rounded-full border border-white/10 bg-slate-950 p-2 text-slate-300 transition-colors hover:bg-slate-800"
          aria-label="Refresh integrations"
        >
          {socialLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
        </button>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {socialInbox.platforms.map((platform) => {
          const meta = socialPlatformMeta[platform.key];
          const Icon = meta.icon;
          const isActive = setupPlatform === platform.key;

          return (
            <button
              key={platform.key}
              onClick={() => setSetupPlatform(platform.key)}
              className={`rounded-[24px] border px-5 py-4 text-left transition-colors ${
                isActive
                  ? 'border-[#6c47ff]/60 bg-[#6c47ff]/15'
                  : 'border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(2,6,23,0.96))] hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="rounded-2xl border border-white/10 bg-slate-950/90 p-3">
                    <Icon size={17} style={{ color: platform.accent }} />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-white">{platform.label}</p>
                    <p className="mt-1 text-xs text-slate-400">{platform.account_label ?? 'No account selected'}</p>
                  </div>
                </div>
                <span
                  className={`rounded-full px-2 py-1 text-[11px] ${
                    platform.verified
                      ? 'bg-emerald-500/15 text-emerald-200'
                      : platform.connected
                        ? 'bg-sky-500/15 text-sky-200'
                        : 'bg-amber-500/10 text-amber-200'
                  }`}
                >
                  {platform.verified ? 'Verified' : platform.connected ? 'Configured' : 'Setup'}
                </span>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {platform.required_fields.map((field) => (
                  <span
                    key={`${platform.key}-${field}`}
                    className={`rounded-full border px-2.5 py-1 text-[11px] ${
                      platform.missing_fields.includes(field)
                        ? 'border-amber-400/30 bg-amber-500/10 text-amber-200'
                        : 'border-emerald-400/20 bg-emerald-500/10 text-emerald-200'
                    }`}
                  >
                    {field.replaceAll('_', ' ')}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      {activePlatform && (
        <div className="mt-6 rounded-[28px] border border-[#6c47ff]/20 bg-[#6c47ff]/8 p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Live API setup</p>
              <h2 className="mt-2 text-lg font-semibold text-white">{activePlatform.label} credentials</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
                Paste only the main credential values first. Akansha auto-generates webhook security
                secrets when possible, stores saved tokens encrypted locally, and only returns masked
                previews to the UI.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => void testSocialPlatform(activePlatform.key)}
                disabled={!activePlatform.connected || busyPlatform === activePlatform.key}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
              >
                {busyPlatform === activePlatform.key ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                Test connection
              </button>
              <button
                onClick={() => void disconnectSocialPlatform(activePlatform.key)}
                disabled={!activePlatform.connected || busyPlatform === activePlatform.key}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
              >
                Disconnect
              </button>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-400/15 bg-emerald-500/5 px-4 py-3">
            <p className="text-sm leading-6 text-emerald-100">
              Simple setup: {activePlatform.label} needs{' '}
              <span className="font-semibold">{activePlatform.required_fields.length}</span>{' '}
              required {activePlatform.required_fields.length === 1 ? 'value' : 'values'} here.
              Advanced webhook/security fields are optional.
            </p>
            {activePlatform.fields.some((field) => field.advanced) && (
              <button
                type="button"
                onClick={() => setShowAdvanced((value) => !value)}
                className="rounded-full border border-white/10 bg-slate-950 px-4 py-2 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-800"
              >
                {showAdvanced ? 'Hide advanced fields' : 'Show advanced fields'}
              </button>
            )}
          </div>

          {activePlatform.verification_detail && (
            <div
              className={`mt-4 rounded-2xl border px-4 py-3 text-sm leading-6 ${
                activePlatform.verified
                  ? 'border-emerald-400/20 bg-emerald-500/5 text-emerald-100'
                  : 'border-amber-400/20 bg-amber-500/5 text-amber-100'
              }`}
            >
              {activePlatform.verification_detail}
            </div>
          )}

          {activeSetupGuide && (
            <div className="mt-4 grid gap-3 rounded-2xl border border-white/10 bg-slate-950/65 p-4 lg:grid-cols-[0.8fr_1.2fr_auto] lg:items-center">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">What to paste</p>
                <p className="mt-1 text-sm font-semibold text-white">{activeSetupGuide.fields}</p>
              </div>
              <ol className="grid gap-2 text-sm leading-6 text-slate-300 md:grid-cols-3">
                {activeSetupGuide.steps.map((step, index) => (
                  <li key={step} className="rounded-2xl border border-white/10 bg-slate-900/80 px-3 py-2">
                    <span className="mr-2 text-xs font-semibold text-[#9d7cff]">{index + 1}</span>
                    {step}
                  </li>
                ))}
              </ol>
              <a
                href={activeSetupGuide.docsUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center justify-center rounded-full border border-white/10 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-800"
              >
                Official docs
              </a>
            </div>
          )}

          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {visibleSetupFields.map((field) => (
              <label key={`${activePlatform.key}-${field.key}`} className="block">
                <span className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-slate-500">
                  {field.secret ? <KeyRound size={12} /> : <PlugZap size={12} />}
                  {field.label}
                  {field.required && <span className="text-amber-200">Required</span>}
                  {field.auto && <span className="text-emerald-200">Auto if blank</span>}
                </span>
                <input
                  type={field.secret ? 'password' : 'text'}
                  value={setupValues[activePlatform.key]?.[field.key] ?? ''}
                  onChange={(event) => updateSetupValue(activePlatform.key, field.key, event.target.value)}
                  placeholder={
                    activePlatform.config_preview[field.key] ||
                    (field.auto ? 'Leave blank to auto-generate' : `Enter ${field.label.toLowerCase()}`)
                  }
                  className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-[#6c47ff]/60"
                />
                {activePlatform.config_preview[field.key] && (
                  <p className="mt-1 text-[11px] text-slate-500">Saved value: {activePlatform.config_preview[field.key]}</p>
                )}
              </label>
            ))}
          </div>

          <div className="mt-5 rounded-2xl border border-white/10 bg-slate-950/70 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Webhook URL</p>
                <p className="mt-1 break-all text-sm text-slate-200">{activePlatform.webhook_url}</p>
              </div>
              <button
                onClick={() => void copyText(activePlatform.webhook_url, 'Webhook URL')}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-900 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
              >
                <Copy size={14} />
                Copy
              </button>
            </div>
            <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-slate-400">
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-200" />
              If this app is running only on localhost, external services cannot call the webhook.
              Use a public tunnel or deployed backend URL and set `AKANSHA_PUBLIC_BASE_URL`.
              Webhook verification secrets are generated automatically unless you choose your own
              in advanced fields.
            </p>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <button
              onClick={() => void saveSocialPlatformSetup(activePlatform.key, true)}
              className="inline-flex items-center gap-2 rounded-full bg-[#6c47ff] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#5a35ee] disabled:opacity-60"
              disabled={busyPlatform === activePlatform.key}
            >
              {busyPlatform === activePlatform.key ? <Loader2 size={14} className="animate-spin" /> : <CheckCheck size={14} />}
              Save and test
            </button>
            <button
              onClick={() => void saveSocialPlatformSetup(activePlatform.key, false)}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-60"
              disabled={busyPlatform === activePlatform.key}
            >
              Save without test
            </button>
          </div>
        </div>
      )}

      <div className="mt-6 grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-[28px] border border-white/10 bg-slate-950/55 p-5">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Real message feed</p>
          <div className="mt-4 space-y-3">
            {connectedMessages.slice(0, 5).map((message) => {
              const meta = socialPlatformMeta[message.platform];
              const Icon = meta.icon;
              const accent = socialInbox.platforms.find((platform) => platform.key === message.platform)?.accent ?? '#6c47ff';

              return (
                <article key={message.id} className="rounded-2xl border border-white/10 bg-slate-900 px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="rounded-xl border border-white/10 bg-slate-950/90 p-2">
                        <Icon size={15} style={{ color: accent }} />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white">{message.sender}</p>
                        <p className="text-xs text-slate-400">{meta.label}</p>
                      </div>
                    </div>
                    {!message.is_read && (
                      <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-200">
                        New
                      </span>
                    )}
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-300">{message.content}</p>
                  <p className="mt-2 flex items-center gap-1 text-xs text-slate-500">
                    <Clock3 size={12} />
                    {new Date(message.timestamp).toLocaleString()}
                  </p>
                </article>
              );
            })}
            {!connectedMessages.length && (
              <div className="rounded-2xl border border-dashed border-white/10 bg-slate-900 px-4 py-6 text-sm text-slate-400">
                No live channel messages yet. Save credentials, copy the webhook URL into the platform,
                and incoming webhook messages will appear here.
              </div>
            )}
          </div>
        </div>

        <div className="rounded-[28px] border border-white/10 bg-slate-950/55 p-5">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Reply approval desk</p>
          <div className="mt-4 space-y-4">
            {connectedMessages.slice(0, 2).map((message) => {
              const replyValue = selectedReply[message.id] ?? message.suggested_replies[0] ?? '';

              return (
                <div key={message.id} className="rounded-2xl border border-white/10 bg-slate-900 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-white">{message.sender}</p>
                    <span className="rounded-full bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200">
                      Approval required
                    </span>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {message.suggested_replies.map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => setSelectedReply((previous) => ({ ...previous, [message.id]: suggestion }))}
                        className={`rounded-full px-3 py-2 text-xs transition-colors ${
                          replyValue === suggestion
                            ? 'bg-[#6c47ff] text-white'
                            : 'border border-white/10 bg-slate-950 text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        <MessageSquareReply size={12} className="mr-1 inline" />
                        {suggestion}
                      </button>
                    ))}
                  </div>

                  <textarea
                    value={replyValue}
                    onChange={(event) => setSelectedReply((previous) => ({ ...previous, [message.id]: event.target.value }))}
                    rows={3}
                    className="mt-3 w-full resize-none rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none transition-colors focus:border-[#6c47ff]/60"
                  />

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      onClick={() => void approveAndSendReply(message)}
                      disabled={sendingReplyId === message.id}
                      className="inline-flex items-center gap-2 rounded-full bg-[#6c47ff] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#5a35ee] disabled:opacity-60"
                    >
                      {sendingReplyId === message.id ? <Loader2 size={14} className="animate-spin" /> : <CheckCheck size={14} />}
                      Approve and send
                    </button>
                    <button
                      onClick={() => setSelectedReply((previous) => ({ ...previous, [message.id]: '' }))}
                      className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
                    >
                      <Trash2 size={14} />
                      Clear draft
                    </button>
                  </div>
                </div>
              );
            })}
            {!connectedMessages.length && (
              <div className="rounded-2xl border border-dashed border-white/10 bg-slate-900 px-4 py-6 text-sm text-slate-400">
                Reply suggestions appear after a connected platform receives real messages. Sending
                still requires your approval.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
