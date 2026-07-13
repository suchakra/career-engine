/**
 * Thin, typed aliases over the OpenAPI-generated schema (types.gen.ts).
 *
 * The frontend never hand-transcribes schema.py — these pull the exact request /
 * response shapes from the generated `components["schemas"]`. If the backend
 * contract changes, re-run `npm run gen:openapi` and these follow automatically.
 */
import type { components } from "./types.gen";

type Schemas = components["schemas"];

export type MeResponse = Schemas["MeResponse"];
export type DashboardResponse = Schemas["DashboardResponse"];
export type PortfolioResponse = Schemas["PortfolioResponse"];
export type EntryCardResponse = Schemas["EntryCardResponse"];
export type StoryCardResponse = Schemas["StoryCardResponse"];
export type JobsResponse = Schemas["JobsResponse"];
export type JobCardResponse = Schemas["JobCardResponse"];
export type UserProfile = Schemas["UserProfile"];
export type SessionPreferences = Schemas["SessionPreferences"];

// Tailor + résumé export (10.6b)
export type TailorRequest = Schemas["TailorRequest"];
export type StructuredResume = Schemas["StructuredResumeDTO"];
export type Contact = Schemas["ContactDTO"];
export type RoleBlock = Schemas["RoleBlockDTO"];
/** One rendered résumé line, carrying the identity of the bullet/story it came from (CQ-6). */
export type ResumeLine = Schemas["ResumeLineDTO"];

// Applications (parity P4)
export type ApplicationWriteRequest = Schemas["ApplicationWriteRequest"];
export type Application = Schemas["Application"];

// Copywriter (CQ-4)
export type CopyProposalsResponse = Schemas["CopyProposalsResponse"];
export type CopyProposalResponse = Schemas["CopyProposalResponse"];
