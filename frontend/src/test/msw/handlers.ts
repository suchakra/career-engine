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

/** Default happy-path handlers. Tests override individual routes as needed. */
export const handlers = [
  http.get(`${BASE}/api/me`, () => HttpResponse.json(mockMe)),
  http.get(`${BASE}/api/dashboard`, () => HttpResponse.json(mockDashboard)),
  http.get(`${BASE}/api/portfolio`, () => HttpResponse.json(mockPortfolio)),
  http.get(`${BASE}/api/jobs`, () => HttpResponse.json(mockJobs)),
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
