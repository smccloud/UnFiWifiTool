import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import {
  AccessBadge,
  EmptyState,
  ErrorBanner,
  InfoBanner,
  Modal,
  ScheduleEditor,
  Spinner,
  StatCard,
  StatusDot,
} from "./components";
import {
  describeSchedule,
  errorMessage,
  formatDateTime,
  relativeTime,
  signalLabel,
} from "./lib/format";
import type {
  AuditEntry,
  Client,
  Device,
  EditableAccessMode,
  LicenseInfo,
  Schedule,
  Status,
  WifiNetwork,
} from "./types";

export type Page = "overview" | "devices" | "clients" | "audit" | "settings";

function deviceName(device: Device): string {
  return device.label || device.hostname || device.mac;
}

function clientName(client: Client): string {
  return client.label || client.name || client.hostname || "Unknown device";
}


// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

export function OverviewPage({
  status,
  refreshKey,
  onNavigate,
  onSync,
  syncing,
}: {
  status: Status | null;
  refreshKey: number;
  onNavigate: (page: Page) => void;
  onSync: () => void;
  syncing: boolean;
}) {
  const [recent, setRecent] = useState<AuditEntry[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .audit({ limit: 8 })
      .then((data) => {
        if (!cancelled) setRecent(data.items);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!status) {
    return <Spinner label="Loading dashboard" />;
  }

  const { counts, controller, enforcement } = status;
  const classicOk = controller.classic_ok;

  return (
    <div className="page-stack">
      {status.security_note ? <InfoBanner>{status.security_note}</InfoBanner> : null}
      {!classicOk ? (
        <InfoBanner>
          Block and unblock are unavailable. Add <code>UNIFI_USERNAME</code> and{" "}
          <code>UNIFI_PASSWORD</code> for a local-only UniFi admin. The official API key is
          read-only for this feature.
        </InfoBanner>
      ) : null}
      {enforcement.dryRun ? (
        <InfoBanner>
          <strong>Dry run is on.</strong> Intended block/unblock calls are recorded in the audit log
          but not sent to UniFi.
        </InfoBanner>
      ) : null}

      <div className="stats-grid">
        <StatCard label="Managed devices" value={counts.devices - counts.ignored} hint={`${counts.devices} known in total`} />
        <StatCard label="Allowed" value={counts.allowed} tone="good" hint="Trusted devices" />
        <StatCard label="Blocked" value={counts.blocked} tone="bad" hint="Denied devices" />
        <StatCard label="Scheduled" value={counts.scheduled} tone="warn" hint="Time-based access" />
        <StatCard label="Seen recently" value={counts.connected} hint="Last 10 minutes" />
      </div>

      <div className="two-col">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Controller</h2>
              <p className="muted small">UniFi OS · {controller.site?.name ?? "site not resolved"}</p>
            </div>
            <button className="button button-ghost" onClick={onSync} disabled={syncing}>
              {syncing ? "Syncing…" : "Sync now"}
            </button>
          </div>
          <div className="key-values">
            <div>
              <span>Status</span>
              <strong>
                <StatusDot ok={!controller.error} />{" "}
                {controller.error ? "Attention needed" : "Connected"}
              </strong>
            </div>
            <div>
              <span>Version</span>
              <strong>{controller.version ?? "Unknown"}</strong>
            </div>
            <div>
              <span>Official API</span>
              <strong>{controller.integration_ok ? "Available" : "Unavailable"}</strong>
            </div>
            <div>
              <span>Block / unblock</span>
              <strong>{controller.classic_ok ? "Available" : "Unavailable"}</strong>
            </div>
            <div>
              <span>SSID allowlist</span>
              <strong>{controller.ssid_allowlist_ok ? "Available" : "Unavailable"}</strong>
            </div>
            <div>
              <span>Last sync</span>
              <strong>{status.last_sync ? relativeTime(status.last_sync.finished_at) : "Never"}</strong>
            </div>
          </div>
          {controller.error ? <ErrorBanner message={controller.error} /> : null}
          {controller.warnings.length ? (
            <ul className="warning-list">
              {controller.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Enforcement</h2>
              <p className="muted small">How access changes reach the controller</p>
            </div>
            <span className={`badge ${enforcement.autoApply ? "badge-allowed" : "badge-ignored"}`}>
              {enforcement.autoApply ? "Automatic" : "Manual only"}
            </span>
          </div>
          <div className="key-values">
            <div>
              <span>Scheduler</span>
              <strong>{enforcement.schedulerEnabled ? `Every ${enforcement.intervalSeconds}s` : "Disabled"}</strong>
            </div>
            <div>
              <span>Discovery</span>
              <strong>{enforcement.discoveryEnabled ? "On" : "Off"}</strong>
            </div>
            <div>
              <span>Dry run</span>
              <strong>{enforcement.dryRun ? "Yes" : "No"}</strong>
            </div>
            <div>
              <span>Timezone</span>
              <strong>{status.timezone}</strong>
            </div>
            <div>
              <span>SSID allowlist writes</span>
              <strong>{enforcement.ssidAllowlistEnabled ? "Enabled" : "Disabled"}</strong>
            </div>
          </div>
          <div className="button-row">
            <button className="button button-primary" onClick={() => onNavigate("devices")}>
              Manage devices
            </button>
            <button className="button button-ghost" onClick={() => onNavigate("clients")}>
              View live clients
            </button>
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Recent activity</h2>
            <p className="muted small">Every state change and controller call is audited</p>
          </div>
          <button className="button button-ghost" onClick={() => onNavigate("audit")}>
            Open audit log
          </button>
        </div>
        {error ? <ErrorBanner message={error} onDismiss={() => setError("")} /> : null}
        {recent.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Device</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((entry) => (
                  <tr key={entry.id}>
                    <td title={formatDateTime(entry.created_at)}>{relativeTime(entry.created_at)}</td>
                    <td>{entry.actor}</td>
                    <td>{entry.action.replaceAll("_", " ")}</td>
                    <td className="mono">{entry.target_mac ?? "—"}</td>
                    <td>
                      <span className={`badge ${entry.result === "success" ? "badge-allowed" : entry.result === "failure" ? "badge-blocked" : "badge-ignored"}`}>
                        {entry.result}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No activity yet" hint="Add a device or run a sync to populate the audit log." />
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Devices
// ---------------------------------------------------------------------------

export function DevicesPage({
  status,
  refreshKey,
  onChanged,
}: {
  status: Status | null;
  refreshKey: number;
  onChanged: () => void;
}) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [selected, setSelected] = useState<Device | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.devices({ q, access_mode: filter });
      setDevices(data.items);
      setTotal(data.total);
      setError("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [q, filter]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 220);
    return () => window.clearTimeout(timer);
  }, [load, refreshKey]);

  async function setMode(device: Device, mode: EditableAccessMode) {
    setBusyId(device.id);
    setError("");
    setNotice("");
    try {
      const updated = await api.updateDevice(device.id, { access_mode: mode, apply: true });
      setSelected((current) => (current?.id === updated.id ? updated : current));
      if (updated.last_error) {
        setError(updated.last_error);
      } else {
        setNotice(`${deviceName(updated)} is now ${mode}.`);
      }
      await load();
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  const classicOk = status?.controller.classic_ok ?? false;

  return (
    <div className="page-stack">
      {!classicOk ? (
        <InfoBanner>
          Enforcement is unavailable without local admin credentials. Devices can still be
          inventoried and scheduled, but block/unblock calls will fail.
        </InfoBanner>
      ) : null}
      {error ? <ErrorBanner message={error} onDismiss={() => setError("")} /> : null}
      {notice ? (
        <div className="banner banner-success">
          <span>{notice}</span>
          <button className="icon-button" onClick={() => setNotice("")} aria-label="Dismiss">
            ×
          </button>
        </div>
      ) : null}

      <section className="panel">
        <div className="panel-heading toolbar-heading">
          <div>
            <h2>Devices</h2>
            <p className="muted small">{total} devices in the local inventory</p>
          </div>
          <div className="toolbar">
            <input
              type="search"
              placeholder="Search name, MAC, IP or notes"
              value={q}
              onChange={(event) => setQ(event.target.value)}
            />
            <select value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="">All states</option>
              <option value="allowed">Allowed</option>
              <option value="blocked">Blocked</option>
              <option value="scheduled">Scheduled</option>
              <option value="ignored">Unmanaged</option>
            </select>
            <button className="button button-primary" onClick={() => setAddOpen(true)}>
              + Add device
            </button>
          </div>
        </div>

        {loading && !devices.length ? (
          <Spinner label="Loading devices" />
        ) : devices.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Access</th>
                  <th>Effective</th>
                  <th>Network</th>
                  <th>Last seen</th>
                  <th>Next change</th>
                  <th className="right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {devices.map((device) => (
                  <tr key={device.id} className={selected?.id === device.id ? "selected-row" : ""}>
                    <td>
                      <button className="link-button" onClick={() => setSelected(device)}>
                        <span className="device-name">{deviceName(device)}</span>
                        <span className="mono muted small">{device.mac}</span>
                      </button>
                    </td>
                    <td>
                      <AccessBadge mode={device.access_mode} />
                      {device.last_error ? <span className="error-dot" title={device.last_error}>!</span> : null}
                    </td>
                    <td>
                      <AccessBadge mode={device.effective_access} />
                    </td>
                    <td>
                      <div>{device.last_ssid ?? "—"}</div>
                      <div className="muted small mono">{device.ip_address ?? "—"}</div>
                    </td>
                    <td title={formatDateTime(device.last_seen_at)}>{relativeTime(device.last_seen_at)}</td>
                    <td title={formatDateTime(device.next_change_at)}>
                      {device.access_mode === "scheduled" ? relativeTime(device.next_change_at) : "—"}
                    </td>
                    <td className="right">
                      <div className="row-actions">
                        <button
                          className="button button-small"
                          disabled={busyId === device.id}
                          onClick={() => void setMode(device, "allowed")}
                        >
                          Allow
                        </button>
                        <button
                          className="button button-small button-danger-ghost"
                          disabled={busyId === device.id}
                          onClick={() => void setMode(device, "blocked")}
                        >
                          Block
                        </button>
                        <button className="button button-small button-ghost" onClick={() => setSelected(device)}>
                          Edit
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No devices match"
            hint="Add a device by MAC, or let discovery populate connected WiFi clients."
          />
        )}
      </section>

      {addOpen ? (
        <AddDeviceModal
          onClose={() => setAddOpen(false)}
          onCreated={async (device) => {
            setAddOpen(false);
            setNotice(`Added ${deviceName(device)}.`);
            await load();
            onChanged();
          }}
        />
      ) : null}

      {selected ? (
        <DeviceDrawer
          device={selected}
          status={status}
          busy={busyId === selected.id}
          onClose={() => setSelected(null)}
          onUpdated={(updated) => {
            setSelected(updated);
            setDevices((current) => current.map((item) => (item.id === updated.id ? updated : item)));
            if (updated.last_error) setError(updated.last_error);
            onChanged();
          }}
          onDeleted={() => {
            setSelected(null);
            setNotice("Device removed from the local inventory.");
            void load();
            onChanged();
          }}
        />
      ) : null}
    </div>
  );
}

function AddDeviceModal({
  onClose,
  onCreated,
  initialMac = "",
}: {
  onClose: () => void;
  onCreated: (device: Device) => Promise<void> | void;
  initialMac?: string;
}) {
  const [mac, setMac] = useState(initialMac);
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [accessMode, setAccessMode] = useState<EditableAccessMode>("allowed");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function createDevice() {
    setError("");
    if (!/^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$/i.test(mac.trim()) && !/^[0-9a-f]{12}$/i.test(mac.trim())) {
      setError("Enter a MAC address like aa:bb:cc:dd:ee:ff");
      return;
    }
    setBusy(true);
    try {
      const device = await api.createDevice({
        mac: mac.trim(),
        label: label.trim(),
        notes: notes.trim(),
        access_mode: accessMode,
      });
      await onCreated(device);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void createDevice();
  }

  return (
    <Modal
      title="Add device"
      onClose={onClose}
      footer={
        <>
          <button className="button button-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="button button-primary" onClick={() => void createDevice()} disabled={busy}>
            {busy ? "Adding…" : "Add device"}
          </button>
        </>
      }
    >
      <form className="form-stack" onSubmit={submit}>
        {error ? <ErrorBanner message={error} onDismiss={() => setError("")} /> : null}
        <label>
          <span>MAC address</span>
          <input
            autoFocus
            value={mac}
            onChange={(event) => setMac(event.target.value)}
            placeholder="aa:bb:cc:dd:ee:ff"
            className="mono"
          />
        </label>
        <label>
          <span>Label</span>
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="e.g. Living room TV"
          />
        </label>
        <label>
          <span>Access</span>
          <select
            value={accessMode}
            onChange={(event) => setAccessMode(event.target.value as EditableAccessMode)}
          >
            <option value="allowed">Allowed</option>
            <option value="blocked">Blocked</option>
            <option value="ignored">Unmanaged</option>
          </select>
        </label>
        <label>
          <span>Notes</span>
          <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} />
        </label>
      </form>
    </Modal>
  );
}

function DeviceDrawer({
  device,
  status,
  busy,
  onClose,
  onUpdated,
  onDeleted,
}: {
  device: Device;
  status: Status | null;
  busy: boolean;
  onClose: () => void;
  onUpdated: (device: Device) => void;
  onDeleted: () => void;
}) {
  const [label, setLabel] = useState(device.label);
  const [notes, setNotes] = useState(device.notes);
  const [accessMode, setAccessMode] = useState<string>(device.access_mode);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    setLabel(device.label);
    setNotes(device.notes);
    setAccessMode(device.access_mode);
  }, [device]);

  async function saveDetails() {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const updated = await api.updateDevice(device.id, {
        label,
        notes,
        ...(accessMode !== device.access_mode
          ? { access_mode: accessMode as EditableAccessMode, apply: true }
          : {}),
      });
      onUpdated(updated);
      if (updated.last_error) setError(updated.last_error);
      else setNotice("Device saved.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function saveSchedule(schedule: Schedule) {
    const updated = await api.setSchedule(device.id, schedule);
    onUpdated(updated);
    if (updated.last_error) setError(updated.last_error);
    else setNotice("Schedule saved. The scheduler will apply changes automatically.");
  }

  async function removeSchedule() {
    const updated = await api.removeSchedule(device.id);
    onUpdated(updated);
    setNotice("Schedule removed. Device is now unmanaged.");
  }

  async function applyNow() {
    setSaving(true);
    setError("");
    try {
      const updated = await api.applyDevice(device.id);
      onUpdated(updated);
      setNotice(updated.last_error ?? "Applied the current effective state.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Remove ${deviceName(device)} from the local inventory? UniFi block state is not changed.`)) {
      return;
    }
    setSaving(true);
    try {
      await api.deleteDevice(device.id);
      onDeleted();
    } catch (err) {
      setError(errorMessage(err));
      setSaving(false);
    }
  }

  const disabled = busy || saving;

  return (
    <div className="drawer-backdrop" onMouseDown={onClose} role="presentation">
      <aside
        className="drawer"
        onMouseDown={(event) => event.stopPropagation()}
        aria-label={`Device details for ${deviceName(device)}`}
      >
        <div className="drawer-header">
          <div>
            <h2>{deviceName(device)}</h2>
            <div className="mono muted">{device.mac}</div>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="drawer-scroll">
          <div className="drawer-badges">
            <AccessBadge mode={device.access_mode} />
            <AccessBadge mode={device.effective_access} label={`Effective: ${device.effective_access ?? "unknown"}`} />
            {device.source === "discovered" ? <span className="badge badge-ignored">Discovered</span> : null}
          </div>

          {error ? <ErrorBanner message={error} onDismiss={() => setError("")} /> : null}
          {notice ? (
            <div className="banner banner-success">
              <span>{notice}</span>
              <button className="icon-button" onClick={() => setNotice("")} aria-label="Dismiss">
                ×
              </button>
            </div>
          ) : null}
          {!status?.controller.classic_ok ? (
            <InfoBanner>Block/unblock requires local admin credentials.</InfoBanner>
          ) : null}

          <div className="drawer-section">
            <h3>Details</h3>
            <div className="form-stack">
              <label>
                <span>Label</span>
                <input value={label} onChange={(event) => setLabel(event.target.value)} />
              </label>
              <label>
                <span>Access mode</span>
                <select value={accessMode} onChange={(event) => setAccessMode(event.target.value)}>
                  {device.access_mode === "scheduled" ? (
                    <option value="scheduled" disabled>
                      Scheduled (edit below)
                    </option>
                  ) : null}
                  <option value="allowed">Allowed</option>
                  <option value="blocked">Blocked</option>
                  <option value="ignored">Unmanaged</option>
                </select>
              </label>
              <label>
                <span>Notes</span>
                <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} />
              </label>
              <div className="button-row">
                <button className="button button-primary" onClick={saveDetails} disabled={disabled}>
                  {saving ? "Saving…" : "Save details"}
                </button>
                <button className="button button-ghost" onClick={applyNow} disabled={disabled}>
                  Apply now
                </button>
              </div>
            </div>
          </div>

          <div className="drawer-section">
            <h3>Observed state</h3>
            <div className="key-values compact">
              <div>
                <span>SSID</span>
                <strong>{device.last_ssid ?? "—"}</strong>
              </div>
              <div>
                <span>IP address</span>
                <strong className="mono">{device.ip_address ?? "—"}</strong>
              </div>
              <div>
                <span>Last seen</span>
                <strong title={formatDateTime(device.last_seen_at)}>{relativeTime(device.last_seen_at)}</strong>
              </div>
              <div>
                <span>Controller block flag</span>
                <strong>{device.observed_blocked === null ? "Unknown" : device.observed_blocked ? "Blocked" : "Not blocked"}</strong>
              </div>
              <div>
                <span>Last applied</span>
                <strong>{device.last_applied_access ?? "Never"}</strong>
              </div>
              <div>
                <span>Next schedule change</span>
                <strong title={formatDateTime(device.next_change_at)}>{relativeTime(device.next_change_at)}</strong>
              </div>
            </div>
            {device.last_error ? <ErrorBanner message={device.last_error} /> : null}
          </div>

          <div className="drawer-section">
            <ScheduleEditor
              device={device}
              defaultTimezone={status?.timezone ?? "UTC"}
              busy={disabled}
              onSave={saveSchedule}
              onClear={removeSchedule}
            />
            {device.schedule ? (
              <p className="muted small">
                Current rule: {describeSchedule(device.schedule)}
              </p>
            ) : null}
          </div>

          <div className="drawer-section danger-zone">
            <h3>Remove from inventory</h3>
            <p className="muted small">
              This deletes the local record and schedule. It does not change the device&apos;s UniFi
              block state.
            </p>
            <button className="button button-danger-ghost" onClick={remove} disabled={disabled}>
              Remove device
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

export function ClientsPage({
  status,
  refreshKey,
  onChanged,
}: {
  status: Status | null;
  refreshKey: number;
  onChanged: () => void;
}) {
  const [clients, setClients] = useState<Client[]>([]);
  const [includeWired, setIncludeWired] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyMac, setBusyMac] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.clients(includeWired);
      setClients(data.items);
      setError("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [includeWired]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  async function act(client: Client, mode: EditableAccessMode) {
    setBusyMac(client.mac);
    setError("");
    setNotice("");
    try {
      let device: Device;
      if (client.device_id) {
        device = await api.updateDevice(client.device_id, { access_mode: mode, apply: true });
      } else {
        device = await api.createDevice({
          mac: client.mac,
          label: client.name || client.hostname || "",
          access_mode: mode,
        });
      }
      if (device.last_error) setError(device.last_error);
      else setNotice(`${clientName(client)} is now ${mode}.`);
      await load();
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyMac(null);
    }
  }

  const classicOk = status?.controller.classic_ok ?? false;

  return (
    <div className="page-stack">
      {!classicOk ? (
        <InfoBanner>Block/unblock requires local admin credentials in the container environment.</InfoBanner>
      ) : null}
      {error ? <ErrorBanner message={error} onDismiss={() => setError("")} /> : null}
      {notice ? (
        <div className="banner banner-success">
          <span>{notice}</span>
          <button className="icon-button" onClick={() => setNotice("")} aria-label="Dismiss">
            ×
          </button>
        </div>
      ) : null}

      <section className="panel">
        <div className="panel-heading toolbar-heading">
          <div>
            <h2>Connected clients</h2>
            <p className="muted small">Live view from the UniFi controller</p>
          </div>
          <div className="toolbar">
            <label className="check">
              <input
                type="checkbox"
                checked={includeWired}
                onChange={(event) => setIncludeWired(event.target.checked)}
              />
              Show wired
            </label>
            <button className="button button-ghost" onClick={() => void load()} disabled={loading}>
              Refresh
            </button>
          </div>
        </div>

        {loading ? (
          <Spinner label="Loading clients" />
        ) : clients.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Network</th>
                  <th>Signal</th>
                  <th>Access</th>
                  <th>Source</th>
                  <th className="right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.mac}>
                    <td>
                      <div className="device-name">{clientName(client)}</div>
                      <div className="mono muted small">{client.mac}</div>
                    </td>
                    <td>
                      <div>{client.ssid ?? "—"}</div>
                      <div className="muted small mono">
                        {client.ip_address ?? "—"} · {client.connection_type ?? "unknown"}
                      </div>
                    </td>
                    <td>{signalLabel(client.signal)}</td>
                    <td>
                      {client.access_mode ? <AccessBadge mode={client.access_mode} /> : <span className="badge badge-ignored">Unmanaged</span>}
                      {client.blocked ? <span className="badge badge-blocked">Controller blocked</span> : null}
                    </td>
                    <td className="muted small">{client.source}</td>
                    <td className="right">
                      <div className="row-actions">
                        <button
                          className="button button-small"
                          disabled={busyMac === client.mac}
                          onClick={() => void act(client, "allowed")}
                        >
                          Allow
                        </button>
                        <button
                          className="button button-small button-danger-ghost"
                          disabled={busyMac === client.mac}
                          onClick={() => void act(client, "blocked")}
                        >
                          Block
                        </button>
                        <button
                          className="button button-small button-ghost"
                          disabled={busyMac === client.mac}
                          onClick={() => void act(client, "ignored")}
                        >
                          Unmanage
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No connected clients" hint="Clients appear here when the controller reports them." />
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export function AuditPage({ refreshKey }: { refreshKey: number }) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState("");
  const [result, setResult] = useState("");
  const [mac, setMac] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const limit = 100;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.audit({ action, result, mac, limit, offset });
      setEntries(data.items);
      setTotal(data.total);
      setError("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [action, result, mac, offset]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <div className="page-stack">
      {error ? <ErrorBanner message={error} onDismiss={() => setError("")} /> : null}
      <section className="panel">
        <div className="panel-heading toolbar-heading">
          <div>
            <h2>Audit log</h2>
            <p className="muted small">{total} entries · newest first</p>
          </div>
          <div className="toolbar">
            <input
              type="search"
              placeholder="Filter MAC"
              value={mac}
              onChange={(event) => {
                setMac(event.target.value);
                setOffset(0);
              }}
              className="mono"
            />
            <select
              value={action}
              onChange={(event) => {
                setAction(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All actions</option>
              <option value="block">Block</option>
              <option value="unblock">Unblock</option>
              <option value="access_changed">Access changed</option>
              <option value="schedule_set">Schedule set</option>
              <option value="schedule_cleared">Schedule cleared</option>
              <option value="device_added">Device added</option>
              <option value="device_removed">Device removed</option>
              <option value="sync">Sync</option>
              <option value="login">Login</option>
              <option value="audit_retention_changed">Retention changed</option>
              <option value="audit_purged">Audit purged</option>
              <option value="dry_run">Dry run</option>
            </select>
            <select
              value={result}
              onChange={(event) => {
                setResult(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">Any result</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
              <option value="skipped">Skipped</option>
            </select>
          </div>
        </div>

        {loading ? (
          <Spinner label="Loading audit log" />
        ) : entries.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Actor</th>
                    <th>Action</th>
                    <th>Device</th>
                    <th>Result</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={entry.id}>
                      <td title={formatDateTime(entry.created_at)}>
                        <div>{relativeTime(entry.created_at)}</div>
                        <div className="muted small">{formatDateTime(entry.created_at)}</div>
                      </td>
                      <td>{entry.actor}</td>
                      <td>{entry.action.replaceAll("_", " ")}</td>
                      <td className="mono">{entry.target_mac ?? "—"}</td>
                      <td>
                        <span className={`badge ${entry.result === "success" ? "badge-allowed" : entry.result === "failure" ? "badge-blocked" : "badge-ignored"}`}>
                          {entry.result}
                        </span>
                      </td>
                      <td>
                        <code className="detail" title={entry.detail ? JSON.stringify(entry.detail) : ""}>
                          {entry.detail ? JSON.stringify(entry.detail) : "—"}
                        </code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <button
                className="button button-ghost"
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
              >
                Previous
              </button>
              <span className="muted small">
                {offset + 1}–{Math.min(offset + limit, total)} of {total}
              </span>
              <button
                className="button button-ghost"
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total}
              >
                Next
              </button>
            </div>
          </>
        ) : (
          <EmptyState title="No audit entries match" />
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export function SettingsPage({
  status,
  onSync,
  syncing,
  onRefreshStatus,
}: {
  status: Status | null;
  onSync: () => void;
  syncing: boolean;
  onRefreshStatus: () => void;
}) {
  const [wifi, setWifi] = useState<WifiNetwork[]>([]);
  const [wifiError, setWifiError] = useState("");
  const [testing, setTesting] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [license, setLicense] = useState<LicenseInfo | null>(null);
  const [licenseError, setLicenseError] = useState("");
  const [retentionDays, setRetentionDays] = useState(0);
  const [retentionBusy, setRetentionBusy] = useState(false);
  const [retentionNotice, setRetentionNotice] = useState("");
  const [retentionError, setRetentionError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .license()
      .then((data) => {
        if (!cancelled) {
          setLicense(data);
          setLicenseError("");
        }
      })
      .catch((err) => {
        if (!cancelled) setLicenseError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .wifi()
      .then((data) => {
        if (!cancelled) {
          setWifi(data);
          setWifiError("");
        }
      })
      .catch((err) => {
        if (!cancelled) setWifiError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [status?.controller.checked_at]);

  useEffect(() => {
    if (status) setRetentionDays(status.audit.retention_days);
  }, [status?.audit.retention_days]);

  if (!status) {
    return <Spinner label="Loading settings" />;
  }

  async function test() {
    setTesting(true);
    setError("");
    setNotice("");
    try {
      await api.testConnection();
      setNotice("Connection test completed.");
      onRefreshStatus();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setTesting(false);
    }
  }

  async function saveRetention() {
    setRetentionBusy(true);
    setRetentionError("");
    setRetentionNotice("");
    try {
      const result = await api.setAuditRetention(retentionDays);
      setRetentionNotice(
        result.retention_days === 0
          ? "Audit retention disabled; entries are kept forever."
          : `Retention set to ${result.retention_days} days and removed ${result.deleted} old entries.`,
      );
      onRefreshStatus();
    } catch (err) {
      setRetentionError(errorMessage(err));
    } finally {
      setRetentionBusy(false);
    }
  }

  async function purgeNow() {
    setRetentionBusy(true);
    setRetentionError("");
    setRetentionNotice("");
    try {
      const result = await api.purgeAudit();
      setRetentionNotice(`Removed ${result.deleted} old audit entries.`);
      onRefreshStatus();
    } catch (err) {
      setRetentionError(errorMessage(err));
    } finally {
      setRetentionBusy(false);
    }
  }

  const controller = status.controller;
  const lastPurge = status.audit.last_purge;

  return (
    <div className="page-stack">
      {error ? <ErrorBanner message={error} onDismiss={() => setError("")} /> : null}
      {notice ? (
        <div className="banner banner-success">
          <span>{notice}</span>
          <button className="icon-button" onClick={() => setNotice("")} aria-label="Dismiss">
            ×
          </button>
        </div>
      ) : null}
      {status.security_note ? <InfoBanner>{status.security_note}</InfoBanner> : null}

      <div className="two-col">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Controller</h2>
              <p className="muted small">{controller.host || "UNIFI_HOST is not set"}</p>
            </div>
            <div className="button-row">
              <button className="button button-ghost" onClick={test} disabled={testing}>
                {testing ? "Testing…" : "Test connection"}
              </button>
              <button className="button button-primary" onClick={onSync} disabled={syncing}>
                {syncing ? "Syncing…" : "Sync now"}
              </button>
            </div>
          </div>
          <div className="key-values">
            <div>
              <span>Site</span>
              <strong>{controller.site?.name ?? "Not resolved"}</strong>
            </div>
            <div>
              <span>Site ID</span>
              <strong className="mono small">{controller.site?.id ?? "—"}</strong>
            </div>
            <div>
              <span>Network version</span>
              <strong>{controller.version ?? "Unknown"}</strong>
            </div>
            <div>
              <span>Official API key</span>
              <strong>{controller.integration_ok ? "Working" : "Not working"}</strong>
            </div>
            <div>
              <span>Local admin session</span>
              <strong>{controller.classic_ok ? "Working" : "Not working"}</strong>
            </div>
            <div>
              <span>SSID allowlist API</span>
              <strong>{controller.ssid_allowlist_ok ? "Available" : "Not available"}</strong>
            </div>
          </div>
          {controller.error ? <ErrorBanner message={controller.error} /> : null}
          {controller.warnings.length ? (
            <ul className="warning-list">
              {controller.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Enforcement</h2>
              <p className="muted small">Environment-controlled behaviour</p>
            </div>
          </div>
          <div className="key-values">
            <div>
              <span>Auto apply</span>
              <strong>{status.enforcement.autoApply ? "Enabled" : "Disabled"}</strong>
            </div>
            <div>
              <span>Dry run</span>
              <strong>{status.enforcement.dryRun ? "Enabled" : "Disabled"}</strong>
            </div>
            <div>
              <span>Scheduler</span>
              <strong>
                {status.enforcement.schedulerEnabled
                  ? `Every ${status.enforcement.intervalSeconds}s`
                  : "Disabled"}
              </strong>
            </div>
            <div>
              <span>Discovery</span>
              <strong>{status.enforcement.discoveryEnabled ? "Enabled" : "Disabled"}</strong>
            </div>
            <div>
              <span>Default timezone</span>
              <strong>{status.timezone}</strong>
            </div>
            <div>
              <span>SSID allowlist writes</span>
              <strong>{status.enforcement.ssidAllowlistEnabled ? "Enabled" : "Disabled"}</strong>
            </div>
          </div>
          <p className="muted small">
            Change these with environment variables in <code>.env</code> and restart the container.
            See <code>.env.example</code> for the full list.
          </p>
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Audit retention</h2>
            <p className="muted small">
              How long to keep login, access-change, block, and unblock history
            </p>
          </div>
          <span className={`badge ${status.audit.retention_days === 0 ? "badge-ignored" : "badge-scheduled"}`}>
            {status.audit.retention_days === 0
              ? "Keep forever"
              : `${status.audit.retention_days} days`}
          </span>
        </div>
        <div className="form-grid two">
          <label>
            <span>Retention (days)</span>
            <input
              type="number"
              min={0}
              max={36500}
              value={retentionDays}
              onChange={(event) =>
                setRetentionDays(event.target.value === "" ? 0 : Number(event.target.value))
              }
            />
            <span className="muted small">0 keeps every entry forever.</span>
          </label>
          <div className="key-values compact">
            <div>
              <span>Last cleanup</span>
              <strong>{lastPurge?.at ? formatDateTime(String(lastPurge.at)) : "Never"}</strong>
            </div>
            <div>
              <span>Removed in last cleanup</span>
              <strong>{lastPurge?.deleted ?? 0}</strong>
            </div>
          </div>
        </div>
        <div className="button-row retention-actions">
          <button
            className="button button-primary"
            onClick={saveRetention}
            disabled={retentionBusy}
          >
            {retentionBusy ? "Saving…" : "Save retention"}
          </button>
          <button
            className="button button-ghost"
            onClick={purgeNow}
            disabled={retentionBusy || retentionDays === 0}
          >
            Run cleanup now
          </button>
        </div>
        <p className="muted small">
          Automatic cleanup runs at most once a day while the scheduler is enabled. Entries older
          than the cutoff are deleted in UTC.
        </p>
        {retentionError ? (
          <ErrorBanner message={retentionError} onDismiss={() => setRetentionError("")} />
        ) : null}
        {retentionNotice ? (
          <div className="banner banner-success">
            <span>{retentionNotice}</span>
            <button
              className="icon-button"
              onClick={() => setRetentionNotice("")}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>WiFi networks</h2>
            <p className="muted small">
              Per-SSID MAC allowlists are available on Network 10.0+ through the official API.
            </p>
          </div>
        </div>
        {wifiError ? (
          <InfoBanner>{wifiError}</InfoBanner>
        ) : wifi.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>SSID</th>
                  <th>Type</th>
                  <th>Enabled</th>
                  <th>Client filter</th>
                </tr>
              </thead>
              <tbody>
                {wifi.map((network) => (
                  <tr key={network.id ?? network.name ?? "unknown"}>
                    <td>{network.name ?? "—"}</td>
                    <td>{network.type ?? "—"}</td>
                    <td>{network.enabled ? "Yes" : "No"}</td>
                    <td>
                      {network.policy.action ? (
                        <span>
                          {network.policy.action} · {network.policy.macCount ?? 0} MACs
                        </span>
                      ) : (
                        <span className="muted">Not configured</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No WiFi networks available" hint="The API key may not have access, or there are no SSIDs." />
        )}
      </section>

      <section className="panel">
        <h2>Security notes</h2>
        <ul className="security-list">
          <li>Use a dedicated UniFi local admin restricted to local access, not a Super Admin.</li>
          <li>API keys inherit the creating admin&apos;s role. Keep the key out of source control.</li>
          <li>Serve this app behind HTTPS and set <code>COOKIE_SECURE=true</code>.</li>
          <li>Prefer <code>UNIFI_CA_BUNDLE</code> over <code>UNIFI_TLS_INSECURE</code> for private certificates.</li>
          <li>Review the audit log for unexpected blocks, unblocks, and login attempts.</li>
          <li>
            API documentation is available at <a href="/api/docs">/api/docs</a>.
          </li>
        </ul>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>About</h2>
            <p className="muted small">
              {status.app_name} v{status.version}
            </p>
          </div>
          <span className="badge badge-allowed">MIT License</span>
        </div>
        <div className="key-values">
          <div>
            <span>License</span>
            <strong>MIT</strong>
          </div>
          <div>
            <span>Source</span>
            <strong>
              <a
                href="https://github.com/smccloud/UniFiWifiTool"
                target="_blank"
                rel="noreferrer"
              >
                GitHub repository
              </a>
            </strong>
          </div>
        </div>
        {licenseError ? <InfoBanner>{licenseError}</InfoBanner> : null}
        <details className="license-details">
          <summary>View MIT license text</summary>
          <pre className="license-text">{license?.text ?? "License text unavailable."}</pre>
        </details>
        <p className="muted small license-link-row">
          <a href="/LICENSE" target="_blank" rel="noreferrer">
            Open the license in a new tab
          </a>
        </p>
      </section>
    </div>
  );
}
