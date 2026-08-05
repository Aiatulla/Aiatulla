/**
 * Types mirroring the backend Pydantic response schemas.
 *
 * Written by hand for now. Once the API surface grows past a handful of
 * endpoints, generate them from the OpenAPI schema instead, so the two sides
 * cannot drift apart silently.
 */

/** Mirrors backend/app/schemas/health.py HealthResponse. */
export interface HealthResponse {
  status: string;
  version: string;
}

/** Mirrors backend/app/schemas/finding.py Severity. */
export type Severity = "critical" | "high" | "medium" | "low" | "info";

/** Mirrors backend/app/models/run.py RunStatus. */
export type RunStatus = "pending" | "running" | "completed" | "failed";

/** Mirrors backend/app/services/diff_service.py Change. */
export type Change = "new" | "fixed" | "persisting";

export interface Finding {
  auditor: string;
  category: string;
  file_path: string;
  line: number | null;
  severity: Severity;
  summary: string;
  evidence: string;
}

export interface Run {
  id: string;
  repository_url: string;
  status: RunStatus;
  error: string | null;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  truncated: boolean;
  created_at: string;
  findings: Finding[];
}

export interface RunSummary {
  id: string;
  repository_url: string;
  status: RunStatus;
  cost_usd: string;
  truncated: boolean;
  created_at: string;
}

export interface DiffEntry {
  change: Change;
  auditor: string;
  category: string;
  file_path: string;
  severity: Severity;
  summary: string;
}

export interface RunDiff {
  run_id: string;
  previous_run_id: string | null;
  is_first_run: boolean;
  counts: Record<Change, number>;
  entries: DiffEntry[];
}

export interface CreateRunBody {
  repository_url: string;
  model?: string;
  max_usd?: string;
}
