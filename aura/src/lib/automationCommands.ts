'use client';

const AUTOMATION_TRIGGER_PATTERNS = [
  /\bopen\b/i,
  /\bplay\b/i,
  /\bsearch\b/i,
  /\brun\b/i,
  /\bclose\b/i,
  /\bdelete\b/i,
  /\bremove\b/i,
  /\bclear\b/i,
  /\bscroll\b/i,
  /\bfill\b/i,
  /\benter\b/i,
  /\bcomplete\b/i,
  /\bedit\b/i,
  /\btype\b/i,
  /\bwrite\b/i,
  /\bclick\b/i,
  /\bsubmit\b/i,
  /\bselect\b/i,
  /\bcopy\b/i,
  /\bpaste\b/i,
  /\bcut\b/i,
  /\bundo\b/i,
  /\bredo\b/i,
  /\bsave\b/i,
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
  /\bpause\b/i,
  /\bresume\b/i,
  /\bnext\b/i,
  /\bprevious\b/i,
  /\bskip\b/i,
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
  /\bpage\b/i,
  /\bup\b/i,
  /\bdown\b/i,
  /\bform\b/i,
  /\bfields?\b/i,
  /\bdetails?\b/i,
  /\bsubmit\b/i,
  /\bthis\b/i,
  /\ball\b/i,
  /\bselection\b/i,
  /\bcontent\b/i,
  /\btext\b/i,
  /\bdraft\b/i,
  /\bhistory\b/i,
  /\baccount\b/i,
  /\beverything\b/i,
  /\bactive\b/i,
  /\bpresent\b/i,
  /\bcurrent\b/i,
  /\btab\b/i,
  /\bvolume\b/i,
  /\bsound\b/i,
  /\bsong\b/i,
  /\bsongs\b/i,
  /\btrack\b/i,
  /\btracks\b/i,
  /\bvideo\b/i,
  /\bvideos\b/i,
  /\bresult\b/i,
  /\bresults\b/i,
  /\bmedia\b/i,
  /\bmusic\b/i,
  /\bmovie\b/i,
  /\bmovies\b/i,
  /\bbrightness\b/i,
  /\bwindow\b/i,
  /\bscreen\b/i,
];

export function normalizeAutomationPrompt(text: string) {
  const normalized = text
    .replace(/\bdsktop\b/gi, 'desktop')
    .replace(/\bdesk top\b/gi, 'desktop')
    .replace(/\bwebiste\b/gi, 'website')
    .replace(/\bwebs?te\b/gi, 'website')
    .replace(/\bsite app\b/gi, 'website')
    .replace(/\bwebsite app\b/gi, 'website')
    .replace(/\bapp version\b/gi, 'desktop app')
    .replace(/\bdesktop side\b/gi, 'desktop app')
    .replace(/\bwebsite side\b/gi, 'website')
    .replace(/\bweb side\b/gi, 'website')
    .replace(/^(desktop|desktop app|desktop application)\s+(.+)$/i, 'open $2 in the desktop app')
    .replace(/^(website|web|browser|site)\s+(.+)$/i, 'open $2 in the web browser')
    .replace(/^(desktop|desktop app|desktop application)\s+(open|launch|start|use)\s+(.+)$/i, 'open $3 in the desktop app')
    .replace(/^(website|web|browser|site)\s+(open|launch|start|use)\s+(.+)$/i, 'open $3 in the web browser')
    .replace(/^open\s+(.+?)\s+desktop$/i, 'open $1 in the desktop app')
    .replace(/^open\s+(.+?)\s+website$/i, 'open $1 in the web browser')
    .replace(/^open\s+(.+?)\s+web$/i, 'open $1 in the web browser')
    .replace(/\bweb\s+site\b/gi, 'website')
    .replace(/\bwebsite version\b/gi, 'website')
    .replace(/\bweb version\b/gi, 'website')
    .replace(/\bbrowser version\b/gi, 'website')
    .replace(/\bdesktop version\b/gi, 'desktop app')
    .replace(/\bdesktop client\b/gi, 'desktop app')
    .replace(/\bweb client\b/gi, 'website')
    .replace(/\bin\s+website\b/gi, 'in the web browser')
    .replace(/\bon\s+website\b/gi, 'in the web browser')
    .replace(/\bin\s+web\b/gi, 'in the web browser')
    .replace(/\bin\s+desktop\b/gi, 'in the desktop app')
    .replace(/\bwhats?\s*up\b/gi, 'whatsapp')
    .replace(/\bwats?\s*up\b/gi, 'whatsapp')
    .replace(/\bwhats?\s*ap+p?\b/gi, 'whatsapp')
    .replace(/\bwhats\s+app\b/gi, 'whatsapp')
    .replace(/\bwhatsup\b/gi, 'whatsapp')
    .replace(/\bwhatsup\b/gi, 'whatsapp')
    .replace(/\bwhastapp\b/gi, 'whatsapp')
    .replace(/\bmicro\s*soft edge\b/gi, 'microsoft edge')
    .replace(/\bmicrosoftedge\b/gi, 'microsoft edge')
    .replace(/\bms edge\b/gi, 'microsoft edge')
    .replace(/\bedge browser\b/gi, 'microsoft edge')
    .replace(/\bmicrosoft edge browser\b/gi, 'microsoft edge')
    .replace(/\bedge app\b/gi, 'microsoft edge')
    .replace(/\bmicrosoft edge app\b/gi, 'microsoft edge')
    .replace(/\bchrome browser\b/gi, 'google chrome')
    .replace(/\bchrome app\b/gi, 'google chrome')
    .replace(/\bgoogle chrome app\b/gi, 'google chrome')
    .replace(
      /\bop(?:en)?\s*(notepad|calculator|calc|file explorer|explorer|vscode|visual studio code|chrome|brave|edge|microsoft edge|whatsapp|telegram|discord|word|excel|powerpoint|settings|terminal|control panel|youtube|google|codechef|linkedin|instagram|twitter|x)\b/gi,
      'open $1'
    )
    .replace(/\bdesktop\s+open\b/gi, 'open')
    .replace(/\bwebsite\s+open\b/gi, 'open')
    .replace(/\bweb\s+open\b/gi, 'open')
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
