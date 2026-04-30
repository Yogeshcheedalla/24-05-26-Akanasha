'use client';

import { useEffect, useRef, useState } from 'react';

type PlannerTask = {
  id: string;
  title: string;
  dueDate?: string;
  reminderEnabled?: boolean;
  reminderAt?: string;
  notified?: boolean;
};

type PlannerEvent = {
  id: string;
  title: string;
  date: string;
  startTime: string;
  endTime: string;
  reminderEnabled: boolean;
  reminderAt?: string;
  notified?: boolean;
};

const TASKS_STORAGE_KEY = 'akansha-planner-tasks';
const EVENTS_STORAGE_KEY = 'akansha-planner-events';

function readStorage<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeStorage<T>(key: string, value: T) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(key, JSON.stringify(value));
  window.dispatchEvent(new StorageEvent('storage', { key }));
}

function formatTime12h(time24: string) {
  const [h, m] = time24.split(':');
  const hours = Number.parseInt(h, 10);
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const h12 = hours % 12 || 12;
  return `${h12}:${m} ${ampm}`;
}

function formatEventWindow(event: PlannerEvent) {
  return `${formatTime12h(event.startTime)} - ${formatTime12h(event.endTime)}`;
}

function buildReminderSyncPayload(tasks: PlannerTask[], events: PlannerEvent[]) {
  return {
    reminders: [
      ...tasks
        .filter((task) => task.reminderEnabled && task.reminderAt && !task.notified)
        .map((task) => ({
          reminder_id: `task:${task.id}`,
          title: `Task reminder: ${task.title}`,
          body: `Due: ${task.dueDate || 'Today'}`,
          reminder_at: task.reminderAt as string,
        })),
      ...events
        .filter((event) => event.reminderEnabled && event.reminderAt && !event.notified)
        .map((event) => ({
          reminder_id: `event:${event.id}`,
          title: `Reminder: ${event.title}`,
          body: `Scheduled for ${event.date} · ${formatEventWindow(event)}`,
          reminder_at: event.reminderAt as string,
        })),
    ],
  };
}

function showBrowserNotification(title: string, body: string) {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  new Notification(title, {
    body,
    icon: '/favicon.ico',
    requireInteraction: true,
  });
}

async function sendDesktopNotification(title: string, body: string) {
  try {
    await fetch('http://localhost:8000/api/system/notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, body }),
    });
  } catch (error) {
    console.error('Failed to send desktop planner notification:', error);
  }
}

export default function PlannerReminderBridge() {
  const [tasks, setTasks] = useState<PlannerTask[]>([]);
  const [events, setEvents] = useState<PlannerEvent[]>([]);
  const timerMapRef = useRef<Map<string, number>>(new Map());
  const syncBackendRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const sync = (event?: Event) => {
      const storageEvent = event instanceof StorageEvent ? event : undefined;
      if (
        storageEvent?.key &&
        storageEvent.key !== TASKS_STORAGE_KEY &&
        storageEvent.key !== EVENTS_STORAGE_KEY
      ) {
        return;
      }
      setTasks(readStorage<PlannerTask[]>(TASKS_STORAGE_KEY, []));
      setEvents(readStorage<PlannerEvent[]>(EVENTS_STORAGE_KEY, []));
    };

    sync();
    window.addEventListener('storage', sync);
    window.addEventListener('focus', sync);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener('focus', sync);
    };
  }, []);

  useEffect(() => {
    const nextTimers = new Map<string, number>();
    const now = Date.now();

    const queueNotification = (
      key: string,
      title: string,
      body: string,
      reminderAt: string,
      markNotified: () => void
    ) => {
      const triggerAt = new Date(reminderAt).getTime();
      if (Number.isNaN(triggerAt)) return;
      const delay = triggerAt - now;

      if (delay <= 0) {
        showBrowserNotification(title, body);
        void sendDesktopNotification(title, body);
        markNotified();
        return;
      }

      const timer = window.setTimeout(() => {
        showBrowserNotification(title, body);
        void sendDesktopNotification(title, body);
        markNotified();
      }, delay);
      nextTimers.set(key, timer);
    };

    tasks.forEach((task) => {
      if (!task.reminderEnabled || !task.reminderAt || task.notified) return;
      queueNotification(
        `task:${task.id}`,
        `Task reminder: ${task.title}`,
        `Due: ${task.dueDate || 'Today'}`,
        task.reminderAt,
        () => {
          const updated = readStorage<PlannerTask[]>(TASKS_STORAGE_KEY, []).map((item) =>
            item.id === task.id ? { ...item, notified: true } : item
          );
          writeStorage(TASKS_STORAGE_KEY, updated);
          setTasks(updated);
        }
      );
    });

    events.forEach((event) => {
      if (!event.reminderEnabled || !event.reminderAt || event.notified) return;
      queueNotification(
        `event:${event.id}`,
        `Reminder: ${event.title}`,
        `Scheduled for ${event.date} · ${formatEventWindow(event)}`,
        event.reminderAt,
        () => {
          const updated = readStorage<PlannerEvent[]>(EVENTS_STORAGE_KEY, []).map((item) =>
            item.id === event.id ? { ...item, notified: true } : item
          );
          writeStorage(EVENTS_STORAGE_KEY, updated);
          setEvents(updated);
        }
      );
    });

    timerMapRef.current.forEach((timer) => window.clearTimeout(timer));
    timerMapRef.current = nextTimers;

    return () => {
      nextTimers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [events, tasks]);

  useEffect(() => {
    syncBackendRef.current = () => {
      const payload = buildReminderSyncPayload(tasks, events);
      fetch('http://localhost:8000/api/planner/reminders/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).catch((error) => {
        console.error('Failed to sync planner reminders to backend scheduler:', error);
      });
    };

    syncBackendRef.current();
  }, [events, tasks]);

  useEffect(() => {
    const resync = () => syncBackendRef.current?.();
    const interval = window.setInterval(resync, 15000);
    window.addEventListener('focus', resync);
    document.addEventListener('visibilitychange', resync);

    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', resync);
      document.removeEventListener('visibilitychange', resync);
    };
  }, []);

  return null;
}
