'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Bell, CalendarDays, Check, CheckSquare, Clock3, Pencil, Plus, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';

interface TaskItem {
  id: string;
  title: string;
  completed: boolean;
  priority: 'high' | 'medium' | 'low';
  dueDate?: string;
  createdAt: string;
  reminderEnabled?: boolean;
  reminderAt?: string;
  notified?: boolean;
}

interface CalendarEvent {
  id: string;
  title: string;
  date: string;
  startTime: string;
  endTime: string;
  type: 'meeting' | 'reminder' | 'focus';
  reminderEnabled: boolean;
  reminderAt?: string;
  notified?: boolean;
}

const TASKS_STORAGE_KEY = 'akansha-planner-tasks';
const EVENTS_STORAGE_KEY = 'akansha-planner-events';
const PLANNER_ACTION_EVENT = 'akansha-planner-action';

const DEFAULT_TASKS: TaskItem[] = [];

const DEFAULT_EVENTS: CalendarEvent[] = [];

const PRIORITY_STYLES = {
  high: 'border-rose-500/25 bg-rose-500/10 text-rose-200',
  medium: 'border-amber-500/25 bg-amber-500/10 text-amber-200',
  low: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200',
};

const EVENT_STYLES = {
  meeting: 'border-[#6C47FF]/25 bg-[#6C47FF]/10 text-[#c7b8ff]',
  reminder: 'border-sky-500/25 bg-sky-500/10 text-sky-200',
  focus: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200',
};

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

function withoutLegacyPlannerSeed<T extends { id: string }>(items: T[]) {
  return items.filter((item) => !['task-001', 'task-002', 'event-001', 'event-002'].includes(item.id));
}

function formatTime12h(time24: string) {
  const [h, m] = time24.split(':');
  const hours = parseInt(h);
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const h12 = hours % 12 || 12;
  return `${h12}:${m} ${ampm}`;
}

function formatEventWindow(event: CalendarEvent) {
  return `${formatTime12h(event.startTime)} - ${formatTime12h(event.endTime)}`;
}

function getEventStartDate(event: CalendarEvent) {
  return new Date(`${event.date}T${event.startTime}:00`);
}

function formatReminderTime(reminderAt?: string) {
  if (!reminderAt) return '';
  return new Date(reminderAt).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });
}

function toTwelveHourParts(time24: string) {
  const [hourRaw = '09', minute = '00'] = (time24 || '09:00').split(':');
  const hour = Number.parseInt(hourRaw, 10);
  const period = hour >= 12 ? 'PM' : 'AM';
  const displayHour = hour % 12 || 12;
  return {
    hour: displayHour.toString(),
    minute,
    period,
  };
}

function fromTwelveHourParts(hour: string, minute: string, period: string) {
  const parsedHour = Number.parseInt(hour, 10);
  const normalizedHour = Number.isNaN(parsedHour) ? 9 : Math.min(Math.max(parsedHour, 1), 12);
  let hour24 = normalizedHour % 12;
  if (period === 'PM') hour24 += 12;
  return `${hour24.toString().padStart(2, '0')}:${minute.padStart(2, '0')}`;
}

function buildIsoDate(date: string, time24: string) {
  return `${date}T${time24}:00`;
}

function extractStoredTime(reminderAt?: string, fallback = '09:00') {
  if (!reminderAt) return fallback;
  const match = reminderAt.match(/T(\d{2}:\d{2})/);
  return match?.[1] || fallback;
}

function getNextQuarterHourTime() {
  const now = new Date();
  const minutes = now.getMinutes();
  const roundedMinutes = Math.ceil((minutes + 1) / 5) * 5;
  now.setMinutes(roundedMinutes, 0, 0);
  const hh = now.getHours().toString().padStart(2, '0');
  const mm = now.getMinutes().toString().padStart(2, '0');
  return `${hh}:${mm}`;
}

function addMinutes(time24: string, minutesToAdd: number) {
  const [hour, minute] = time24.split(':').map(Number);
  const totalMinutes = hour * 60 + minute + minutesToAdd;
  const normalized = ((totalMinutes % (24 * 60)) + (24 * 60)) % (24 * 60);
  const nextHour = Math.floor(normalized / 60)
    .toString()
    .padStart(2, '0');
  const nextMinute = (normalized % 60).toString().padStart(2, '0');
  return `${nextHour}:${nextMinute}`;
}

function TimePicker({
  value,
  onChange,
  className = '',
}: {
  value: string;
  onChange: (nextValue: string) => void;
  className?: string;
}) {
  const parts = useMemo(() => toTwelveHourParts(value), [value]);
  const hours = Array.from({ length: 12 }, (_, index) => `${index + 1}`);
  const minutes = Array.from({ length: 60 }, (_, index) => `${index}`.padStart(2, '0'));

  const update = (patch: Partial<typeof parts>) => {
    const next = { ...parts, ...patch };
    onChange(fromTwelveHourParts(next.hour, next.minute, next.period));
  };

  return (
    <div className={`grid grid-cols-[1fr_1fr_1fr] gap-2 ${className}`}>
      <select
        value={parts.hour}
        onChange={(event) => update({ hour: event.target.value })}
        className="rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground outline-none"
      >
        {hours.map((hour) => (
          <option key={hour} value={hour}>
            {hour}
          </option>
        ))}
      </select>
      <select
        value={parts.minute}
        onChange={(event) => update({ minute: event.target.value })}
        className="rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground outline-none"
      >
        {minutes.map((minute) => (
          <option key={minute} value={minute}>
            {minute}
          </option>
        ))}
      </select>
      <select
        value={parts.period}
        onChange={(event) => update({ period: event.target.value })}
        className="rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground outline-none"
      >
        <option value="AM">AM</option>
        <option value="PM">PM</option>
      </select>
    </div>
  );
}

function showPlannerNotification(title: string, body: string) {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  new Notification(title, {
    body,
    icon: '/favicon.ico',
    requireInteraction: true,
  });
}

async function sendDesktopPlannerNotification(title: string, body: string) {
  try {
    await fetch('http://localhost:8000/api/system/notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, body }),
    });
  } catch (error) {
    console.warn('Failed to send desktop notification:', error);
  }
}

async function sendPlannerTestAlert() {
  showPlannerNotification('Akansha planner test', 'Browser reminder channel is active.');
  await sendDesktopPlannerNotification(
    'Akansha planner test',
    'Desktop reminder channel is active.'
  );
}

export default function TaskCalendarPanel() {
  const [activeTab, setActiveTab] = useState<'tasks' | 'calendar'>('tasks');
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [plannerLoaded, setPlannerLoaded] = useState(false);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [showEventForm, setShowEventForm] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskPriority, setTaskPriority] = useState<TaskItem['priority']>('medium');
  const [taskDate, setTaskDate] = useState('');
  const [taskReminder, setTaskReminder] = useState(false);
  const [taskReminderTime, setTaskReminderTime] = useState('09:00');
  const [eventTitle, setEventTitle] = useState('');
  const [eventType, setEventType] = useState<CalendarEvent['type']>('meeting');
  const [eventDate, setEventDate] = useState('');
  const [eventStartTime, setEventStartTime] = useState('09:00');
  const [eventEndTime, setEventEndTime] = useState('10:00');
  const [eventReminder, setEventReminder] = useState(true);
  const [eventReminderTime, setEventReminderTime] = useState('08:45');

  useEffect(() => {
    setTasks(withoutLegacyPlannerSeed(readStorage(TASKS_STORAGE_KEY, DEFAULT_TASKS)));
    setEvents(withoutLegacyPlannerSeed(readStorage(EVENTS_STORAGE_KEY, DEFAULT_EVENTS)));
    setPlannerLoaded(true);
  }, []);

  useEffect(() => {
    if (!plannerLoaded) return;
    writeStorage(TASKS_STORAGE_KEY, tasks);
  }, [plannerLoaded, tasks]);

  useEffect(() => {
    if (!plannerLoaded) return;
    writeStorage(EVENTS_STORAGE_KEY, events);
  }, [events, plannerLoaded]);

  useEffect(() => {
    const syncPlannerState = (event?: StorageEvent) => {
      if (
        event?.key &&
        event.key !== TASKS_STORAGE_KEY &&
        event.key !== EVENTS_STORAGE_KEY
      ) {
        return;
      }

      setTasks(withoutLegacyPlannerSeed(readStorage(TASKS_STORAGE_KEY, DEFAULT_TASKS)));
      setEvents(withoutLegacyPlannerSeed(readStorage(EVENTS_STORAGE_KEY, DEFAULT_EVENTS)));
    };

    window.addEventListener('storage', syncPlannerState);
    return () => window.removeEventListener('storage', syncPlannerState);
  }, []);

  useEffect(() => {
    const handlePlannerAction = (event: Event) => {
      const customEvent = event as CustomEvent<{
        type: 'task' | 'calendar';
        title: string;
        dueDate?: string;
        date?: string;
        startTime?: string;
        endTime?: string;
        reminderEnabled?: boolean;
        reminderAt?: string;
      }>;
      const detail = customEvent.detail;
      if (!detail?.title?.trim()) return;

      if (detail.type === 'task') {
        const nextTask: TaskItem = {
          id: `task-${Date.now()}`,
          title: detail.title.trim(),
          completed: false,
          priority: 'medium',
          dueDate: detail.dueDate,
          createdAt: new Date().toISOString(),
          reminderEnabled: Boolean(detail.reminderEnabled),
          reminderAt: detail.reminderAt,
          notified: false,
        };
        setActiveTab('tasks');
        setTasks((previous) => {
          const next = [nextTask, ...previous];
          writeStorage(TASKS_STORAGE_KEY, next);
          return next;
        });
        toast.success('Added to your to-do planner');
        return;
      }

      const nextEvent: CalendarEvent = {
        id: `event-${Date.now()}`,
        title: detail.title.trim(),
        date: detail.date || new Date().toISOString().slice(0, 10),
        startTime: detail.startTime || getNextQuarterHourTime(),
        endTime: detail.endTime || addMinutes(detail.startTime || getNextQuarterHourTime(), 30),
        type: 'reminder',
        reminderEnabled: Boolean(detail.reminderEnabled),
        reminderAt: detail.reminderAt,
        notified: false,
      };
      setActiveTab('calendar');
      setEvents((previous) => {
        const next = [...previous, nextEvent].sort(
          (a, b) => getEventStartDate(a).getTime() - getEventStartDate(b).getTime()
        );
        writeStorage(EVENTS_STORAGE_KEY, next);
        return next;
      });
      toast.success('Added to your calendar planner');
    };

    window.addEventListener(PLANNER_ACTION_EVENT, handlePlannerAction as EventListener);
    return () =>
      window.removeEventListener(PLANNER_ACTION_EVENT, handlePlannerAction as EventListener);
  }, []);




  const requestBrowserNotificationPermission = async () => {
    if (typeof Notification === 'undefined') {
      toast.info('Browser notifications are unavailable here. Desktop alerts will still be used.');
      return true;
    }

    if (Notification.permission === 'granted') return true;
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      toast.info('Browser notifications were not granted. Desktop alerts will still try to appear.');
      return true;
    }
    toast.success('Notifications enabled for planner reminders');
    return true;
  };

  const resetTaskForm = () => {
    setEditingTaskId(null);
    setTaskTitle('');
    setTaskPriority('medium');
    setTaskDate('');
    setTaskReminder(false);
    setTaskReminderTime('09:00');
    setShowTaskForm(false);
  };

  const resetEventForm = () => {
    setEditingEventId(null);
    setEventTitle('');
    setEventDate('');
    setEventStartTime('09:00');
    setEventEndTime('10:00');
    setEventType('meeting');
    setEventReminder(true);
    setEventReminderTime('08:45');
    setShowEventForm(false);
  };

  const editTask = (task: TaskItem) => {
    setEditingTaskId(task.id);
    setTaskTitle(task.title);
    setTaskPriority(task.priority);
    setTaskDate(task.dueDate || '');
    setTaskReminder(Boolean(task.reminderEnabled));
    setTaskReminderTime(task.reminderAt ? extractStoredTime(task.reminderAt, '09:00') : '09:00');
    setShowTaskForm(true);
  };

  const editEvent = (event: CalendarEvent) => {
    setEditingEventId(event.id);
    setEventTitle(event.title);
    setEventDate(event.date);
    setEventStartTime(event.startTime);
    setEventEndTime(event.endTime);
    setEventType(event.type);
    setEventReminder(event.reminderEnabled);
    setEventReminderTime(event.reminderAt ? extractStoredTime(event.reminderAt, addMinutes(event.startTime, -15)) : addMinutes(event.startTime, -15));
    setShowEventForm(true);
  };

  const addTask = async () => {
    if (!taskTitle.trim()) return;

    const nextTask: TaskItem = {
      id: editingTaskId || `task-${Date.now()}`,
      title: taskTitle.trim(),
      completed: false,
      priority: taskPriority,
      dueDate: taskDate || undefined,
      createdAt: new Date().toISOString(),
      reminderEnabled: taskReminder,
      reminderAt:
        taskReminder && taskDate
          ? buildIsoDate(taskDate, taskReminderTime)
          : undefined,
      notified: false,
    };

    setTasks((previous) => {
      const next = editingTaskId
        ? previous.map((item) => (item.id === editingTaskId ? { ...item, ...nextTask } : item))
        : [nextTask, ...previous];
      writeStorage(TASKS_STORAGE_KEY, next);
      return next;
    });
    resetTaskForm();
    toast.success(editingTaskId ? 'Task updated' : 'Task added to your planner');
  };

  const addEvent = async () => {
    if (!eventTitle.trim()) return;
    if (!eventDate || !eventStartTime || !eventEndTime) {
      toast.error('Calendar events need a date, start time, and end time.');
      return;
    }

    if (eventEndTime <= eventStartTime) {
      toast.error('End time must be later than start time.');
      return;
    }

    const nextEvent: CalendarEvent = {
      id: editingEventId || `event-${Date.now()}`,
      title: eventTitle.trim(),
      date: eventDate,
      startTime: eventStartTime,
      endTime: eventEndTime,
      type: eventType,
      reminderEnabled: eventReminder,
      reminderAt:
        eventReminder && eventDate
          ? buildIsoDate(eventDate, eventReminderTime)
          : undefined,
      notified: false,
    };

    setEvents((previous) => {
      const next = [...previous.filter((item) => item.id !== editingEventId), nextEvent].sort(
        (a, b) => getEventStartDate(a).getTime() - getEventStartDate(b).getTime()
      );
      writeStorage(EVENTS_STORAGE_KEY, next);
      return next;
    });
    resetEventForm();
    toast.success(editingEventId ? 'Calendar reminder updated' : 'Calendar event scheduled');
  };

  const pendingTasks = useMemo(() => tasks.filter((task) => !task.completed).length, [tasks]);
  const doneTasks = useMemo(() => tasks.filter((task) => task.completed).length, [tasks]);
  const upcomingEvents = useMemo(
    () => [...events].sort((a, b) => getEventStartDate(a).getTime() - getEventStartDate(b).getTime()),
    [events]
  );

  return (
    <div className="flex h-full flex-col">
      <div className="grid grid-cols-2 border-b border-border/80 bg-card/40">
        {[
          { key: 'tasks', label: 'To-Do', icon: CheckSquare, badge: pendingTasks },
          { key: 'calendar', label: 'Calendar', icon: CalendarDays, badge: upcomingEvents.length },
        ].map(({ key, label, icon: Icon, badge }) => (
          <button
            type="button"
            key={key}
            onClick={() => setActiveTab(key as 'tasks' | 'calendar')}
            className={`flex items-center justify-center gap-2 px-3 py-3 text-sm font-medium transition-colors ${
              activeTab === key
                ? 'border-b-2 border-[#6C47FF] text-[#9B7FFF]'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon size={14} />
            {label}
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-mono tabular-nums text-muted-foreground">
              {badge}
            </span>
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {activeTab === 'tasks' && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-2xl border border-[#6C47FF]/20 bg-gradient-to-br from-[#6C47FF]/12 to-transparent p-4">
                <p className="text-2xl font-semibold text-[#c7b8ff]">{pendingTasks}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  Pending
                </p>
              </div>
              <div className="rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/12 to-transparent p-4">
                <p className="text-2xl font-semibold text-emerald-200">{doneTasks}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  Completed
                </p>
              </div>
            </div>

            {showTaskForm ? (
              <div className="rounded-3xl border border-[#6C47FF]/25 bg-[#6C47FF]/8 p-4">
                <div className="space-y-3">
                  <input
                    value={taskTitle}
                    onChange={(event) => setTaskTitle(event.target.value)}
                    placeholder="What do you need to get done?"
                    className="w-full rounded-2xl border border-white/10 bg-card px-4 py-3 text-sm text-foreground outline-none focus:border-[#6C47FF]/40"
                  />

                  <div className="grid grid-cols-2 gap-3">
                    <select
                      value={taskPriority}
                      onChange={(event) =>
                        setTaskPriority(event.target.value as TaskItem['priority'])
                      }
                      className="rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground outline-none"
                    >
                      <option value="high">High priority</option>
                      <option value="medium">Medium priority</option>
                      <option value="low">Low priority</option>
                    </select>
                    <input
                      type="date"
                      value={taskDate}
                      onChange={(event) => setTaskDate(event.target.value)}
                      className="rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground outline-none"
                    />
                  </div>

                   <div
                     onClick={async () => {
                        if (!taskReminder) {
                         await requestBrowserNotificationPermission();
                         setTaskReminder(true);
                         if (!taskReminderTime) setTaskReminderTime('09:00');
                       } else {
                         setTaskReminder(false);
                       }
                     }}
                     className="flex cursor-pointer items-center justify-between rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground hover:bg-white/[0.02] transition-colors"
                   >
                    Reminder notification
                      <div
                        className={`relative h-6 w-11 flex-shrink-0 cursor-pointer rounded-full transition-colors duration-200 ease-in-out focus:outline-none ${
                          taskReminder ? 'bg-emerald-500' : 'bg-muted'
                        }`}
                      >
                        <span
                          className={`pointer-events-none absolute left-1 top-1 h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                            taskReminder ? 'translate-x-5' : 'translate-x-0'
                          }`}
                        />
                      </div>
                  </div>

                   {taskReminder && taskDate && (
                    <label className="block">
                      <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Custom reminder time
                      </span>
                      <TimePicker
                        value={taskReminderTime}
                        onChange={setTaskReminderTime}
                      />
                    </label>
                  )}

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={addTask}
                      className="inline-flex items-center gap-2 rounded-2xl bg-[#6C47FF] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#5A35EE]"
                    >
                      <Plus size={14} />
                      {editingTaskId ? 'Update task' : 'Save task'}
                    </button>
                    <button
                      type="button"
                      onClick={resetTaskForm}
                      className="rounded-2xl border border-white/10 px-4 py-2.5 text-sm text-muted-foreground hover:bg-muted"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowTaskForm(true)}
                className="flex w-full items-center justify-center gap-2 rounded-3xl border border-dashed border-[#6C47FF]/30 bg-[#6C47FF]/6 px-4 py-3 text-sm font-medium text-[#b9a8ff] transition-colors hover:border-[#6C47FF]/50 hover:bg-[#6C47FF]/10"
              >
                <Plus size={14} />
                Add to-do
              </button>
            )}

            <div className="space-y-2">
              {tasks.map((task) => (
                <div
                  key={task.id}
                  className={`group rounded-3xl border p-4 transition-colors ${
                    task.completed
                      ? 'border-white/5 bg-card/40 opacity-70'
                      : 'border-border/70 bg-card/70 hover:border-[#6C47FF]/25'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <button
                      type="button"
                      onClick={() =>
                        setTasks((previous) => {
                          const next = previous.map((item) =>
                            item.id === task.id ? { ...item, completed: !item.completed } : item
                          );
                          writeStorage(TASKS_STORAGE_KEY, next);
                          return next;
                        })
                      }
                      className={`mt-0.5 flex h-5 w-5 items-center justify-center rounded-full border transition-colors ${
                        task.completed
                          ? 'border-emerald-500 bg-emerald-500 text-white'
                          : 'border-border hover:border-[#6C47FF]'
                      }`}
                    >
                      {task.completed && <Check size={11} />}
                    </button>

                    <div className="min-w-0 flex-1">
                      <p
                        className={`text-sm font-medium leading-6 ${
                          task.completed ? 'text-muted-foreground line-through' : 'text-foreground'
                        }`}
                      >
                        {task.title}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span
                          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] ${
                            PRIORITY_STYLES[task.priority]
                          }`}
                        >
                          {task.priority}
                        </span>
                        {task.dueDate && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground">
                            <Clock3 size={11} />
                            {task.dueDate}
                          </span>
                        )}
                        {task.reminderEnabled && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-200">
                            <Bell size={11} />
                            {task.reminderAt ? `Notify ${formatReminderTime(task.reminderAt)}` : 'Notify'}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          editTask(task);
                        }}
                        className="rounded-xl p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setTasks((previous) => {
                            const next = previous.filter((item) => item.id !== task.id);
                            writeStorage(TASKS_STORAGE_KEY, next);
                            return next;
                          });
                          toast.success('Task removed');
                        }}
                        className="rounded-xl p-2 text-muted-foreground hover:bg-muted hover:text-red-400"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'calendar' && (
          <div className="space-y-4">
            <div className="rounded-3xl border border-sky-500/20 bg-gradient-to-br from-sky-500/10 via-[#6C47FF]/8 to-transparent p-4">
              <div className="flex items-center gap-2">
                <Bell size={15} className="text-sky-300" />
                <p className="text-sm font-medium text-foreground">Today's time windows</p>
                <button
                  type="button"
                  onClick={() => {
                    void sendPlannerTestAlert();
                    toast.success('Test alert sent');
                  }}
                  className="ml-auto inline-flex items-center gap-2 rounded-full border border-white/10 bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-white/[0.04]"
                >
                  <Bell size={12} />
                  Send test alert
                </button>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Calendar events now use a proper <span className="text-foreground">start time</span>{' '}
                and <span className="text-foreground">end time</span>. Notifications trigger before
                the start time without changing your to-do section.
              </p>
            </div>

            {showEventForm ? (
              <div className="rounded-3xl border border-sky-500/20 bg-sky-500/8 p-4">
                <div className="space-y-3">
                  <input
                    value={eventTitle}
                    onChange={(event) => setEventTitle(event.target.value)}
                    placeholder="Calendar event title"
                    className="w-full rounded-2xl border border-white/10 bg-card px-4 py-3 text-sm text-foreground outline-none focus:border-sky-500/40"
                  />

                  <div className="grid grid-cols-3 gap-3">
                    <input
                      type="date"
                      value={eventDate}
                      onChange={(event) => setEventDate(event.target.value)}
                      className="rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground outline-none"
                    />
                    <TimePicker
                      value={eventStartTime}
                      onChange={setEventStartTime}
                    />
                    <TimePicker
                      value={eventEndTime}
                      onChange={setEventEndTime}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <select
                      value={eventType}
                      onChange={(event) =>
                        setEventType(event.target.value as CalendarEvent['type'])
                      }
                      className="rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground outline-none"
                    >
                      <option value="meeting">Meeting</option>
                      <option value="reminder">Reminder</option>
                      <option value="focus">Focus block</option>
                    </select>

                   <div
                     onClick={async () => {
                      if (!eventReminder) {
                         await requestBrowserNotificationPermission();
                         setEventReminder(true);
                         if (!eventReminderTime && eventStartTime) {
                           const [h, m] = eventStartTime.split(':').map(Number);
                           const reminderMins = (h * 60 + m - 15 + 24 * 60) % (24 * 60);
                           const reminderH = Math.floor(reminderMins / 60);
                           const reminderM = reminderMins % 60;
                           setEventReminderTime(`${reminderH.toString().padStart(2, '0')}:${reminderM.toString().padStart(2, '0')}`);
                         }
                       } else {
                         setEventReminder(false);
                       }
                     }}
                     className="flex cursor-pointer items-center justify-between rounded-2xl border border-white/10 bg-card px-3 py-3 text-sm text-foreground hover:bg-white/[0.02] transition-colors"
                   >
                      Notify me
                      <div
                        className={`relative h-6 w-11 flex-shrink-0 cursor-pointer rounded-full transition-colors duration-200 ease-in-out focus:outline-none ${
                          eventReminder ? 'bg-emerald-500' : 'bg-muted'
                        }`}
                      >
                        <span
                          className={`pointer-events-none absolute left-1 top-1 h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                            eventReminder ? 'translate-x-5' : 'translate-x-0'
                          }`}
                        />
                      </div>
                    </div>
                  </div>

                  {eventReminder && eventDate && (
                    <label className="block">
                      <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Custom reminder time
                      </span>
                      <TimePicker
                        value={eventReminderTime}
                        onChange={setEventReminderTime}
                      />
                    </label>
                  )}

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={addEvent}
                      className="inline-flex items-center gap-2 rounded-2xl bg-sky-500 px-4 py-2.5 text-sm font-medium text-slate-950 transition-colors hover:bg-sky-400"
                    >
                      <Plus size={14} />
                      {editingEventId ? 'Update event' : 'Save event'}
                    </button>
                    <button
                      type="button"
                      onClick={resetEventForm}
                      className="rounded-2xl border border-white/10 px-4 py-2.5 text-sm text-muted-foreground hover:bg-muted"
                    >
                      <X size={14} className="inline" />
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowEventForm(true)}
                className="flex w-full items-center justify-center gap-2 rounded-3xl border border-dashed border-sky-500/30 bg-sky-500/6 px-4 py-3 text-sm font-medium text-sky-200 transition-colors hover:border-sky-500/50 hover:bg-sky-500/10"
              >
                <Plus size={14} />
                Add calendar slot
              </button>
            )}

            <div className="space-y-2">
              {upcomingEvents.map((event) => (
                <div
                  key={event.id}
                  className="group rounded-3xl border border-border/70 bg-card/70 p-4 transition-colors hover:border-sky-500/25"
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`rounded-2xl border px-3 py-2 text-[11px] font-medium uppercase tracking-[0.2em] ${
                        EVENT_STYLES[event.type]
                      }`}
                    >
                      {event.type}
                    </div>

                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground">{event.title}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground">
                          <CalendarDays size={11} />
                          {event.date}
                        </span>
                        <span className="inline-flex items-center gap-1 rounded-full bg-slate-900/70 px-2.5 py-1 text-[11px] text-slate-200">
                          <Clock3 size={11} />
                          {formatEventWindow(event)}
                        </span>
                        {event.reminderEnabled && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-200">
                            <Bell size={11} />
                            {event.reminderAt
                              ? `Notify ${formatReminderTime(event.reminderAt)}`
                              : 'Notification'}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={(clickEvent) => {
                          clickEvent.stopPropagation();
                          editEvent(event);
                        }}
                        className="rounded-xl p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={(clickEvent) => {
                          clickEvent.stopPropagation();
                          setEvents((previous) => {
                            const next = previous.filter((item) => item.id !== event.id);
                            writeStorage(EVENTS_STORAGE_KEY, next);
                            return next;
                          });
                          toast.success('Calendar event removed');
                        }}
                        className="rounded-xl p-2 text-muted-foreground hover:bg-muted hover:text-red-400"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
