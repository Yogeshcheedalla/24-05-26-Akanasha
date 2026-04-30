'use client';

const AUTOMATION_TRIGGER_PATTERNS = [
  /\bopen\b/i,
  /\bplay\b/i,
  /\bsearch\b/i,
  /\brun\b/i,
  /\bclose\b/i,
  /\btype\b/i,
  /\bwrite\b/i,
  /\bclick\b/i,
  /\blaunch\b/i,
  /\bstart\b/i,
  /\bgo to\b/i,
  /\bincrease\b/i,
  /\bdecrease\b/i,
  /\bturn\b/i,
  /\bset\b/i,
  /\bmute\b/i,
  /\bunmute\b/i,
  /\bstop\b/i,
  /\bwait\b/i,
];

const AUTOMATION_TARGET_PATTERNS = [
  /\byoutube\b/i,
  /\bgoogle\b/i,
  /\bchrome\b/i,
  /\bbrave\b/i,
  /\bedge\b/i,
  /\bcodechef\b/i,
  /\blinkedin\b/i,
  /\binstagram\b/i,
  /\bdiscord\b/i,
  /\btelegram\b/i,
  /\bwhatsapp\b/i,
  /\bdownloads?\b/i,
  /\bdesktop\b/i,
  /\bdocuments?\b/i,
  /\bnotepad\b/i,
  /\bcalculator\b/i,
  /\bexplorer\b/i,
  /\bpowershell\b/i,
  /\bcmd\b/i,
  /\bfile\b/i,
  /\bfolder\b/i,
  /\bpath\b/i,
  /\bwebsite\b/i,
  /\btab\b/i,
  /\bvolume\b/i,
  /\bsound\b/i,
  /\bsong\b/i,
  /\bsongs\b/i,
  /\bmusic\b/i,
  /\bmovie\b/i,
  /\bmovies\b/i,
  /\bbrightness\b/i,
  /\bwindow\b/i,
  /\bscreen\b/i,
];

export function normalizeAutomationPrompt(text: string) {
  const normalized = text
    .replace(/\byoutub\b/gi, 'youtube')
    .replace(/\bvarsham songs?\b/gi, 'Varsham songs')
    .replace(/\bcaland(ar|er)?\b/gi, 'calendar')
    .replace(/\s+/g, ' ')
    .trim();

  if (/\bplay\b/i.test(normalized) && /\b(song|songs|music|movie|movies)\b/i.test(normalized) && !/\byoutube\b/i.test(normalized)) {
    return `open youtube and ${normalized}`;
  }

  return normalized;
}

export function isAutomationIntent(text: string) {
  const normalized = normalizeAutomationPrompt(text);
  const hasTrigger = AUTOMATION_TRIGGER_PATTERNS.some((pattern) => pattern.test(normalized));
  const hasTarget = AUTOMATION_TARGET_PATTERNS.some((pattern) => pattern.test(normalized));
  return hasTrigger && hasTarget;
}
