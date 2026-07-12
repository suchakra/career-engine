import { http, HttpResponse } from "msw";

import type {
  DashboardResponse,
  JobsResponse,
  MeResponse,
  PortfolioResponse,
  SessionPreferences,
  UserProfile,
} from "@/lib/api/models";

const BASE = "http://localhost:8080";

export const mockMe: MeResponse = {
  user_id: "user-123",
  email: "jane@example.com",
};

export const mockDashboard: DashboardResponse = {
  progress_meter: "62%",
  show_nudge: true,
  nudge_message: "You haven't grilled in 6 days — a 5-min session keeps your portfolio sharp.",
  pending_actions: ["Follow up: Acme — SWE", "Add metrics to Migration project"],
  application_count: 5,
  can_tailor: true,
  can_start_grill: true,
  can_find_jobs: true,
  pending_actions_detail: [{ label: "Follow up: Acme — SWE" }],
};

export const mockPortfolio: PortfolioResponse = {
  entries: [
    {
      entry_id: "entry-1",
      title: "Senior Engineer",
      org: "Acme",
      dates: "2022–present",
      type_label: "role",
      status_label: "DOCUMENTED",
      bullets: ["Cut p95 latency 40%"],
      stories: [
        {
          situation: "Latency spikes on checkout",
          task: "Reduce p95",
          action: "Profiled + cached",
          result: "40% faster",
          metric_validated: true,
          story_id: "story-1",
        },
      ],
      highlighted: true,
      story_count: 1,
      stories_target: 3,
    },
  ],
  empty_text: "",
  is_empty: false,
};

export const mockJobs: JobsResponse = {
  accepted: [
    {
      job_id: "job-1",
      title: "Staff Engineer",
      company: "Globex",
      location: "Remote",
      work_model: "remote",
      employment_type: "full_time",
      url: "https://example.com/job-1",
      status: "accepted",
      rationale: "Strong match on backend + cloud.",
    },
  ],
  for_review: [],
  iterations: 1,
  hard_rejected_count: 0,
  ran: true,
  empty_text: "",
  is_empty: false,
};

/** Serialize one SSE frame (`event:` + `data:` + blank line). */
export function grillFrame(event: string, payload: object): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

/** Build a `text/event-stream` ReadableStream from pre-serialized frames. */
export function sseStream(frames: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const f of frames) controller.enqueue(enc.encode(f));
      controller.close();
    },
  });
}

const mockTurn = {
  next_question: "Can you put a number on that improvement?",
  checkpoint_summary: "",
  is_complete: false,
  upgrade_required: false,
  upgrade_message: "",
  stories_count: 1,
  phase: "grilling",
  frontier_label: "Senior Engineer — Acme",
};

/** A persisted profile — note it carries fields no form edits (email/phone/links). */
export const mockProfile: UserProfile = {
  name: "Ada Lovelace",
  email: "ada@example.com",
  phone: "+1 555 0100",
  location: "Remote · UK",
  links: ["https://github.com/ada"],
  contract_version: "2.8.0",
};

/** A persisted rubric — `nice_to_haves` is edited by no form, so it must survive a save. */
export const mockPreferences: SessionPreferences = {
  target_roles: ["Staff Engineer"],
  dealbreakers: ["on-site"],
  nice_to_haves: ["remote-first"],
  contract_version: "2.8.0",
};

/** Default happy-path handlers. Tests override individual routes as needed. */
export const handlers = [
  http.get(`${BASE}/api/me`, () => HttpResponse.json(mockMe)),
  http.get(`${BASE}/api/dashboard`, () => HttpResponse.json(mockDashboard)),
  http.get(`${BASE}/api/portfolio`, () => HttpResponse.json(mockPortfolio)),
  http.get(`${BASE}/api/jobs`, () => HttpResponse.json(mockJobs)),
  http.get(`${BASE}/api/profile`, () => HttpResponse.json(mockProfile)),
  http.get(`${BASE}/api/preferences`, () => HttpResponse.json(mockPreferences)),
  http.post(`${BASE}/api/profile`, async ({ request }) => {
    const body = (await request.json()) as Partial<UserProfile>;
    const saved: UserProfile = {
      name: body.name ?? "",
      email: body.email ?? "",
      phone: body.phone ?? "",
      location: body.location ?? "",
      links: body.links ?? [],
      contract_version: "2.8.0",
    };
    return HttpResponse.json(saved);
  }),
  http.post(`${BASE}/api/jobs/discover`, () => HttpResponse.json({ ...mockJobs, ran: true })),
  http.post(`${BASE}/api/jobs/dismiss`, () => new HttpResponse(null, { status: 204 })),
  http.patch(`${BASE}/api/experience/:id/bullet`, () => new HttpResponse(null, { status: 204 })),
  http.post(`${BASE}/api/experience/:id/bullet`, () => new HttpResponse(null, { status: 204 })),
  http.get(`${BASE}/api/key`, () => HttpResponse.json({ has_key: false })),
  http.post(`${BASE}/api/key`, () => new HttpResponse(null, { status: 204 })),
  http.delete(`${BASE}/api/key`, () => new HttpResponse(null, { status: 204 })),
  // Default: NO existing session, so the Grill page shows the start card.
  http.get(`${BASE}/api/grill`, () =>
    HttpResponse.json({
      has_session: false,
      phase: "",
      frontier_label: "",
      awaiting: "idle",
      current_question: "",
      checkpoint_summary: "",
    }),
  ),
  http.post(`${BASE}/api/grill`, () =>
    HttpResponse.json({
      phase: "grilling",
      frontier_label: "Senior Engineer — Acme",
      awaiting: "question",
    }),
  ),
  http.post(`${BASE}/api/grill/resume`, () =>
    HttpResponse.json({
      phase: "grilling",
      frontier_label: "Senior Engineer — Acme",
      awaiting: "question",
    }),
  ),
  http.get(`${BASE}/api/grill/stream`, () => {
    // Separate frames (not concatenated) exercise the client parser across frame
    // boundaries. The terminal `done` re-emits the last turn (matches the server),
    // so the client appends only on `turn`.
    return new HttpResponse(
      sseStream([grillFrame("turn", mockTurn), grillFrame("done", mockTurn)]),
      { headers: { "Content-Type": "text/event-stream" } },
    );
  }),
  http.post(`${BASE}/api/applications`, () =>
    HttpResponse.json({
      application_id: "11111111-1111-1111-1111-111111111111",
      company: "Globex",
      job_title: "Staff Engineer",
      jd_text: "",
      tailored_resume_json: "{}",
      status: "applied",
      applied_on: "2026-07-11",
    }),
  ),
  http.post(`${BASE}/api/tailor`, () =>
    HttpResponse.json({
      contact: { name: "Jane Doe", email: "jane@example.com", phone: "", location: "Berlin", links: [] },
      summary: "Staff engineer, distributed systems.",
      skills: ["Python", "Kubernetes"],
      experience: [
        { title: "Senior Engineer", org: "Acme", dates: "2022–now", bullets: ["Cut p95 latency 40%"] },
      ],
      education: [],
    }),
  ),
  http.post(`${BASE}/api/master-resume`, () =>
    HttpResponse.json({
      contact: { name: "Jane Doe", email: "jane@example.com", phone: "", location: "Berlin", links: [] },
      summary: "Staff engineer.",
      skills: [], // skills are JD-aligned in the tailored pass only
      experience: [
        {
          title: "Senior Engineer",
          org: "Acme",
          dates: "2022–now",
          bullets: ["Cut p95 latency 40%", "Shipped billing v2"],
        },
      ],
      education: [{ title: "BSc Computer Science", org: "MIT", dates: "2016–2020", bullets: [] }],
    }),
  ),
  http.post(`${BASE}/api/resume/:fmt`, () =>
    HttpResponse.text("JANE DOE\nSummary…", {
      headers: { "Content-Type": "text/markdown" },
    }),
  ),
  http.put(`${BASE}/api/preferences`, async ({ request }) => {
    const body = (await request.json()) as Partial<SessionPreferences>;
    const saved: SessionPreferences = {
      target_roles: body.target_roles ?? [],
      dealbreakers: body.dealbreakers ?? [],
      nice_to_haves: body.nice_to_haves ?? [],
      contract_version: "2.8.0",
    };
    return HttpResponse.json(saved);
  }),
];
