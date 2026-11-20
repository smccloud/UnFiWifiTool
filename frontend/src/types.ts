export type AccessMode = "allowed" | "blocked" | "scheduled" | "ignored";
export type EditableAccessMode = "allowed" | "blocked" | "ignored";

export interface ScheduleWindow {
  days: number[];
  start: string;
  end: string;
  action: "allow" | "block";
}

export interface Schedule {
  default_access: "allowed" | "blocked";
  timezone: string;
  windows: ScheduleWindow[];
}

export interface Device {
  id: number;
  mac: string;
  label: string;
  notes: string;
  access_mode: AccessMode;
  schedule: Schedule | null;
  effective_access: string | null;
  next_change_at: string | null;
  last_applied_access: string | null;
  last_applied_at: string | null;
  last_synced_at: string | null;
  last_error: string | null;
  observed_blocked: boolean | null;
  hostname: string | null;
  ip_address: string | null;
  last_ssid: string | null;
  last_signal: number | null;
  last_seen_at: string | null;
  unifi_client_id: string | null;
  source: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  connected: boolean | null;
}

export interface DeviceList {
  items: Device[];
  total: number;
}

export interface Client {
  mac: string;
  name: string | null;
  hostname: string | null;
  ip_address: string | null;
  ssid: string | null;
  signal: number | null;
  blocked: boolean | null;
  connected: boolean;
  connection_type: string | null;
  last_seen_at: string | null;
  source: string;
  device_id: number | null;
  label: string | null;
  access_mode: AccessMode | null;
  effective_access: string | null;
  managed: boolean;
}

export interface ClientList {
  items: Client[];
  connected_total: number;
  managed_total: number;
}

export interface AuditEntry {
  id: number;
  created_at: string;
  actor: string;
  action: string;
  target_mac: string | null;
  result: string;
  detail: Record<string, unknown> | null;
  request_id: string | null;
}

export interface AuditList {
  items: AuditEntry[];
  total: number;
}

export interface SyncSummary {
  started_at: string;
  finished_at: string;
  discovered: number;
  updated: number;
  applied: number;
  skipped: number;
  errors: string[];
  transitions: Record<string, unknown>[];
  dry_run: boolean;
}

export interface ControllerInfo {
  host: string;
  integration_ok: boolean;
  classic_ok: boolean;
  ssid_allowlist_ok: boolean;
  version: string | null;
  site: { id: string | null; name: string | null } | null;
  error: string | null;
  warnings: string[];
  checked_at: string | null;
}

export interface EnforcementInfo {
  autoApply: boolean;
  dryRun: boolean;
  schedulerEnabled: boolean;
  intervalSeconds: number;
  discoveryEnabled: boolean;
  ssidAllowlistEnabled: boolean;
  mode: string;
}

export interface Counts {
  devices: number;
  allowed: number;
  blocked: number;
  scheduled: number;
  ignored: number;
  connected: number;
}

export interface Status {
  app_name: string;
  version: string;
  auth_disabled: boolean;
  timezone: string;
  controller: ControllerInfo;
  enforcement: EnforcementInfo;
  counts: Counts;
  last_sync: SyncSummary | null;
  security_note: string | null;
}

export interface WifiNetwork {
  id: string | null;
  name: string | null;
  enabled: boolean | null;
  type: string | null;
  policy: { action?: string | null; macCount?: number };
}

export interface Me {
  username: string;
  csrf_token: string;
  auth_disabled: boolean;
  app_name: string;
  version: string;
}
