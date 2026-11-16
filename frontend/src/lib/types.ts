export type Status = 'UNKNOWN'|'UP'|'DEGRADED'|'DOWN'|'PAUSED';
export type TimeWindow = '24h'|'7d'|'30d';
export interface MonitorInput { name:string; description:string; url:string; method:'GET'|'HEAD'; interval_seconds:number; timeout_seconds:number; expected_status_min:number; expected_status_max:number; failure_threshold:number; recovery_threshold:number; degraded_latency_ms:number|null; degraded_threshold:number; notification_channel_ids:string[]; }
export interface Monitor extends MonitorInput { id:string; status:Status; created_at:string; last_checked_at:string|null; next_run_at:string; uptime?:number|null; average_latency_ms?:number|null; active_incident_id?:string|null; }
export interface Page<T> { items:T[]; next_cursor:string|null; }
export interface MetricSummary { total:number; successful:number; failed:number; degraded:number; uptime:number|null; average_ms:number|null; p50:number|null; p75:number|null; p90:number|null; p95:number|null; p99:number|null; }
export interface Bucket extends MetricSummary { at:string; until:string; }
export interface Metrics { monitor_id:string; summary:MetricSummary; previous:MetricSummary|null; buckets:Bucket[]; window:TimeWindow; latency_series:string[]; }
export interface Overview { items:Monitor[]; total:number; offset:number; limit:number; summary:{total:number; operational:number; degraded:number; down:number; unknown:number; paused:number; open_incidents:number; average_ms:number|null}; }
export interface Incident { id:string; monitor_id:string; monitor_name:string; state:'OPEN'|'RESOLVED'; started_at:string; detected_at:string; resolved_at:string|null; reason:string; failure_count_at_open:number; failed_checks:number; recovery_successes:number; duration_seconds:number; }
export interface TimelineEvent { id:string; action:string; information:Record<string,string|number|null>; created_at:string; }
export interface Channel { id:string; name:string; provider:'discord'; enabled:boolean; on_down:boolean; on_recovered:boolean; created_at:string; }
export interface Delivery { id:string; event_type:string; delivery_state:'PENDING'|'SENT'|'FAILED'; attempts:number; last_error_sanitized:string|null; created_at:string; }
export interface StatusPage { id:string; name:string; slug:string; description:string; published:boolean; monitor_ids:string[]; }
export interface PublicPage { name:string; description:string; updated_at:string|null; monitors:{name:string;status:Status;uptime:number|null;last_checked_at:string|null;incidents:{state:string;started_at:string;resolved_at:string|null}[]}[]; }
export interface System {version:string; worker_alive:boolean; worker_last_seen:string|null; pending_alerts:number; failed_alerts:number; alert_channel:string; retention_days:number; max_monitors:number; location:string;}
