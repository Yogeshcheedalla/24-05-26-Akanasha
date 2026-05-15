export type ConversationStatus = 'active' | 'archived' | 'summarized';

export type ConversationFolder = {
  id: string;
  name: string;
};

export type ConversationMetadata = {
  folderId?: string;
  starred?: boolean;
  shared?: boolean;
  status?: ConversationStatus;
};

const FOLDERS_KEY = 'akansha-conversation-folders';
const METADATA_KEY = 'akansha-conversation-metadata';

export const DEFAULT_CONVERSATION_FOLDERS: ConversationFolder[] = [
  { id: 'folder-chats', name: 'Chats' },
  { id: 'folder-work', name: 'Work' },
  { id: 'folder-research', name: 'Research' },
  { id: 'folder-personal', name: 'Personal' },
];

function readJson<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function writeJson<T>(key: string, value: T) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

export function readConversationFolders(): ConversationFolder[] {
  const folders = readJson<ConversationFolder[]>(FOLDERS_KEY, DEFAULT_CONVERSATION_FOLDERS);
  const seen = new Set<string>();
  return [...DEFAULT_CONVERSATION_FOLDERS, ...folders]
    .filter((folder) => folder.id && folder.name)
    .filter((folder) => {
      if (seen.has(folder.id)) return false;
      seen.add(folder.id);
      return true;
    });
}

export function writeConversationFolders(folders: ConversationFolder[]) {
  writeJson(FOLDERS_KEY, folders);
}

export function readConversationMetadata(): Record<string, ConversationMetadata> {
  return readJson<Record<string, ConversationMetadata>>(METADATA_KEY, {});
}

export function writeConversationMetadata(metadata: Record<string, ConversationMetadata>) {
  writeJson(METADATA_KEY, metadata);
}

export function clearConversationMetadata() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(METADATA_KEY);
}

export function slugFolderId(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  return `folder-${slug || Date.now()}`;
}
