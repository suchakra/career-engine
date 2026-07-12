import type { components } from "./types.gen";

type Schemas = components["schemas"];

/** Request body for `POST /api/grill` (OpenAPI-typed). */
export type GrillActionRequest = Schemas["GrillActionRequest"];
/** Post-record status snapshot from `POST /api/grill` (OpenAPI-typed). */
export type GrillSnapshot = Schemas["GrillSnapshot"];
export type GrillStatus = Schemas["GrillStatus"];

/**
 * SSE payloads for `GET /api/grill/stream`. These are hand-authored because the
 * endpoint returns a `StreamingResponse`, so FastAPI can't advertise a
 * `response_model` and they never appear in the OpenAPI schema. Keep in sync with
 * `api/schemas.py::GrillTurnEvent` / `GrillErrorEvent` (mirrors `cli.app.TurnResult`).
 */
export interface GrillTurnEvent {
  next_question: string;
  checkpoint_summary: string;
  is_complete: boolean;
  upgrade_required: boolean;
  upgrade_message: string;
  stories_count: number;
  phase: string;
  frontier_label: string;
}

/** SSE payload for a mid-stream model failure (`event: error`). */
export interface GrillErrorEvent {
  message: string;
  rate_limited: boolean;
}
