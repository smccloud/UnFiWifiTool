import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Device, Schedule, ScheduleWindow } from "./types";
import { DAY_NAMES, describeSchedule, errorMessage } from "./lib/format";

const ACCESS_LABELS: Record<string, string> = {
  allowed: "Allowed",
  blocked: "Blocked",
  scheduled: "Scheduled",
  ignored: "Unmanaged",
};

export function AccessBadge({ mode, label }: { mode: string | null | undefined; label?: string }) {
  const value = mode ?? "ignored";
  return (
    <span className={`badge badge-${value}`}>{label ?? ACCESS_LABELS[value] ?? value}</span>
  );
}

export function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`status-dot ${ok ? "status-ok" : "status-bad"}`} aria-hidden="true" />;
}

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "good" | "bad" | "warn";
}) {
  return (
    <div className={`stat-card tone-${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
    </div>
  );
}

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div className="banner banner-error" role="alert">
      <span>{message}</span>
      {onDismiss ? (
        <button className="icon-button" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      ) : null}
    </div>
  );
}

export function InfoBanner({ children }: { children: ReactNode }) {
  return <div className="banner banner-info">{children}</div>;
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">◇</div>
      <div>{title}</div>
      {hint ? <div className="muted small">{hint}</div> : null}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="spinner-row">
      <span className="spinner" />
      <span className="muted">{label}…</span>
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={onClose} role="presentation">
      <div
        className={`modal ${wide ? "modal-wide" : ""}`}
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
}

const FALLBACK_TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Berlin",
  "Australia/Sydney",
  "Asia/Tokyo",
];

function timezoneOptions(): string[] {
  try {
    const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
    const zones = intl.supportedValuesOf?.("timeZone");
    return zones && zones.length ? zones : FALLBACK_TIMEZONES;
  } catch {
    return FALLBACK_TIMEZONES;
  }
}

const TIMEZONES = timezoneOptions();

const PRESETS: Array<{ label: string; kind: Schedule["kind"]; windows: ScheduleWindow[] }> = [
  {
    label: "Weekdays 9–5",
    kind: "allow_during",
    windows: [{ days: [0, 1, 2, 3, 4], start: "09:00", end: "17:00" }],
  },
  {
    label: "Every day 8–10pm",
    kind: "allow_during",
    windows: [{ days: [0, 1, 2, 3, 4, 5, 6], start: "20:00", end: "22:00" }],
  },
  {
    label: "Overnight 10pm–7am",
    kind: "allow_during",
    windows: [{ days: [0, 1, 2, 3, 4, 5, 6], start: "22:00", end: "07:00" }],
  },
  {
    label: "Block weekdays 9–5",
    kind: "block_during",
    windows: [{ days: [0, 1, 2, 3, 4], start: "09:00", end: "17:00" }],
  },
];

export function ScheduleEditor({
  device,
  defaultTimezone,
  busy,
  onSave,
  onClear,
}: {
  device: Device;
  defaultTimezone: string;
  busy: boolean;
  onSave: (schedule: Schedule) => Promise<void>;
  onClear: () => Promise<void>;
}) {
  const [kind, setKind] = useState<Schedule["kind"]>(device.schedule?.kind ?? "allow_during");
  const [timezone, setTimezone] = useState(device.schedule?.timezone ?? defaultTimezone);
  const [windows, setWindows] = useState<ScheduleWindow[]>(
    device.schedule?.windows ?? [{ days: [0, 1, 2, 3, 4], start: "09:00", end: "17:00" }],
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setKind(device.schedule?.kind ?? "allow_during");
    setTimezone(device.schedule?.timezone ?? defaultTimezone);
    setWindows(
      device.schedule?.windows ?? [{ days: [0, 1, 2, 3, 4], start: "09:00", end: "17:00" }],
    );
    setError("");
  }, [device.id, device.schedule, defaultTimezone]);

  const preview = useMemo(() => {
    if (!windows.length) return "Add at least one window.";
    return describeSchedule({ kind, timezone, windows });
  }, [kind, timezone, windows]);

  function updateWindow(index: number, patch: Partial<ScheduleWindow>) {
    setWindows((current) =>
      current.map((window, position) => (position === index ? { ...window, ...patch } : window)),
    );
  }

  function toggleDay(index: number, day: number) {
    setWindows((current) =>
      current.map((window, position) => {
        if (position !== index) return window;
        const has = window.days.includes(day);
        const days = has ? window.days.filter((item) => item !== day) : [...window.days, day].sort();
        return { ...window, days };
      }),
    );
  }

  async function save() {
    setError("");
    if (!windows.length) {
      setError("Add at least one window.");
      return;
    }
    for (const [index, window] of windows.entries()) {
      if (!window.days.length) {
        setError(`Window ${index + 1} needs at least one day.`);
        return;
      }
      if (window.start === window.end) {
        setError(`Window ${index + 1} start and end must differ.`);
        return;
      }
    }
    setSaving(true);
    try {
      await onSave({ kind, timezone, windows });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function clear() {
    if (!window.confirm("Remove the schedule? The device becomes unmanaged and its current UniFi block state is not changed.")) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onClear();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const disabled = busy || saving;

  return (
    <div className="schedule-editor">
      <div className="section-heading">
        <h3>Time-based access</h3>
        {device.schedule ? <span className="badge badge-scheduled">Active schedule</span> : null}
      </div>
      <p className="muted small">
        The scheduler evaluates every {device.schedule ? "few seconds" : "30 seconds"} and applies
        block or unblock transitions automatically. Timezone-aware, including overnight windows.
      </p>

      <div className="preset-row">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            className="chip"
            disabled={disabled}
            onClick={() => {
              setKind(preset.kind);
              setWindows(preset.windows.map((window) => ({ ...window, days: [...window.days] })));
            }}
          >
            {preset.label}
          </button>
        ))}
      </div>

      <div className="form-grid two">
        <label>
          <span>Schedule behaviour</span>
          <select
            value={kind}
            disabled={disabled}
            onChange={(event) => setKind(event.target.value as Schedule["kind"])}
          >
            <option value="allow_during">Allowed inside windows → blocked outside</option>
            <option value="block_during">Blocked inside windows → allowed outside</option>
          </select>
        </label>
        <label>
          <span>Timezone</span>
          <input
            list="timezone-options"
            value={timezone}
            disabled={disabled}
            onChange={(event) => setTimezone(event.target.value)}
          />
          <datalist id="timezone-options">
            {TIMEZONES.map((zone) => (
              <option key={zone} value={zone} />
            ))}
          </datalist>
        </label>
      </div>

      <div className="windows">
        {windows.map((window, index) => (
          <div className="window-row" key={index}>
            <div className="day-picker" aria-label={`Window ${index + 1} days`}>
              {DAY_NAMES.map((day, dayIndex) => (
                <button
                  key={day}
                  type="button"
                  className={window.days.includes(dayIndex) ? "day active" : "day"}
                  disabled={disabled}
                  onClick={() => toggleDay(index, dayIndex)}
                  title={day}
                >
                  {day.slice(0, 1)}
                </button>
              ))}
            </div>
            <input
              type="time"
              value={window.start}
              disabled={disabled}
              onChange={(event) => updateWindow(index, { start: event.target.value })}
              aria-label={`Window ${index + 1} start`}
            />
            <span className="muted">to</span>
            <input
              type="time"
              value={window.end}
              disabled={disabled}
              onChange={(event) => updateWindow(index, { end: event.target.value })}
              aria-label={`Window ${index + 1} end`}
            />
            <button
              type="button"
              className="icon-button"
              disabled={disabled || windows.length === 1}
              onClick={() => setWindows((current) => current.filter((_, position) => position !== index))}
              aria-label="Remove window"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="button button-ghost"
        disabled={disabled}
        onClick={() =>
          setWindows((current) => [
            ...current,
            { days: [0, 1, 2, 3, 4], start: "09:00", end: "17:00" },
          ])
        }
      >
        + Add window
      </button>

      <div className="schedule-preview">{preview}</div>
      {error ? <ErrorBanner message={error} onDismiss={() => setError("")} /> : null}

      <div className="button-row">
        <button type="button" className="button button-primary" onClick={save} disabled={disabled}>
          {saving ? "Saving…" : device.schedule ? "Update schedule" : "Enable schedule"}
        </button>
        {device.schedule ? (
          <button type="button" className="button button-danger-ghost" onClick={clear} disabled={disabled}>
            Remove schedule
          </button>
        ) : null}
      </div>
    </div>
  );
}
