/**
 * Shared types mirroring the backend Pydantic response schemas.
 *
 * These are written by hand for now. Once the API surface grows past a handful
 * of endpoints, generate them from the OpenAPI schema instead, so the two sides
 * cannot drift apart silently.
 */

/** Mirrors backend/app/schemas/health.py HealthResponse. */
export interface HealthResponse {
  status: string;
  version: string;
}
