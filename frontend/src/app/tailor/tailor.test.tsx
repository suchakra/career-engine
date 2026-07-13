import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TailorContent } from "@/app/tailor/TailorContent";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/utils";

const BASE = "http://localhost:8080";

// Capture the original (jsdom-absent) URL methods so we can restore them and not
// leak the assigned mocks into later tests.
const _origUrl = {
  createObjectURL: URL.createObjectURL,
  revokeObjectURL: URL.revokeObjectURL,
};
afterEach(() => {
  Object.assign(URL, _origUrl);
  vi.restoreAllMocks();
});

describe("Tailor", () => {
  it("tailors a JD into a previewed résumé, then exports", async () => {
    // jsdom implements neither URL.createObjectURL nor anchor downloads — assign
    // mocks directly (spyOn needs an existing property) and stub the anchor click.
    const createObjectURL = vi.fn(() => "blob:x");
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
    const clicked: string[] = [];
    let exportCalled = false;
    server.use(
      http.post(`${BASE}/api/resume/:fmt`, ({ params }) => {
        exportCalled = true;
        clicked.push(String(params.fmt));
        return HttpResponse.text("md", { headers: { "Content-Type": "text/markdown" } });
      }),
    );
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const user = userEvent.setup();
    renderWithProviders(<TailorContent />);

    await user.type(screen.getByLabelText("Job description"), "We need a Staff Engineer.");
    await user.click(screen.getByRole("button", { name: /tailor my résumé/i }));

    // The preview renders the server's tailored résumé.
    expect(await screen.findByText(/staff engineer, distributed systems/i)).toBeInTheDocument();
    expect(screen.getByText(/Cut p95 latency 40%/i)).toBeInTheDocument();

    // Exporting hits POST /api/resume/{fmt} and triggers a download.
    await user.click(screen.getByRole("button", { name: "PDF" }));
    await waitFor(() => expect(exportCalled).toBe(true));
    expect(clicked).toContain("pdf");
    expect(createObjectURL).toHaveBeenCalled();
  });

  it("tracks the tailored résumé as an application", async () => {
    let tracked: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/applications`, async ({ request }) => {
        tracked = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ company: "Globex", job_title: "Staff Engineer" });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<TailorContent />);
    await user.type(screen.getByLabelText("Job description"), "We need a Staff Engineer.");
    await user.click(screen.getByRole("button", { name: /tailor my résumé/i }));
    await screen.findByText(/staff engineer, distributed systems/i);

    await user.type(screen.getByLabelText("Company"), "Globex");
    await user.type(screen.getByLabelText("Role"), "Staff Engineer");
    await user.click(screen.getByRole("button", { name: /save as tracked application/i }));

    await waitFor(() =>
      expect(tracked).toMatchObject({ company: "Globex", job_title: "Staff Engineer" }),
    );
  });

  // ── CQ-6b: editing the preview, and what the edit MEANS ──────────────────

  async function tailorAndEdit(user: ReturnType<typeof userEvent.setup>, text: string) {
    renderWithProviders(<TailorContent />);
    await user.type(screen.getByLabelText("Job description"), "We need a Staff Engineer.");
    await user.click(screen.getByRole("button", { name: /tailor my résumé/i }));
    await screen.findByText(/staff engineer, distributed systems/i);

    await user.click(screen.getByRole("button", { name: /Cut p95 latency 40%/i }));
    const box = screen.getByLabelText("Edit this line");
    await user.clear(box);
    await user.type(box, text);
  }

  it("EXPORTS the edited text, not the original — 'this résumé only'", async () => {
    // THE bug this design had to dodge: `exportResume` serializes the résumé held in
    // `useTailor`. If an edit lived in the preview component's own state, the user would edit
    // a line, watch it change on screen, hit PDF — and download the résumé WITHOUT the edit.
    // Asserting "no store writes" would not have caught it; asserting the BODY does.
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    let exported: { experience?: { bullets?: { text: string }[] }[] } | null = null;
    let storeWrites = 0;
    server.use(
      http.post(`${BASE}/api/resume/:fmt`, async ({ request }) => {
        exported = (await request.json()) as typeof exported;
        return HttpResponse.text("md", { headers: { "Content-Type": "text/markdown" } });
      }),
      http.post(`${BASE}/api/experience/:id/bullet`, () => {
        storeWrites += 1;
        return HttpResponse.json({ bullet_id: "b-1" }, { status: 201 });
      }),
      http.patch(`${BASE}/api/experience/:id/bullet`, () => {
        storeWrites += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    await tailorAndEdit(user, "Cut p95 latency 40% on Acme's stack");
    // "This résumé only" is the DEFAULT — overwriting the portfolio is never preselected.
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.click(screen.getByRole("button", { name: "PDF" }));

    await waitFor(() => expect(exported).not.toBeNull());
    expect(exported!.experience![0].bullets![0].text).toBe("Cut p95 latency 40% on Acme's stack");
    expect(storeWrites).toBe(0); // the portfolio was NOT touched
  });

  it("OVERWRITE persists the line, and can be undone", async () => {
    // Overwrite is destructive — the old wording is gone from the store — so a user who
    // rewords a line for one job and regrets it must have a way back.
    const posted: Record<string, unknown>[] = [];
    let deleted = false;
    server.use(
      http.post(`${BASE}/api/experience/:id/bullet`, async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ bullet_id: "b-1" }, { status: 201 });
      }),
      http.delete(`${BASE}/api/experience/:id/bullet/:bulletId`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    await tailorAndEdit(user, "Rebuilt the latency path, cutting p95 40%");
    await user.click(
      screen.getByRole("radio", { name: /replace this line in my portfolio/i }),
    );
    await user.click(screen.getByRole("button", { name: "Save" }));

    // The fixture line is story-backed (no bullet yet), so it persists a bullet that SPEAKS
    // FOR that story — otherwise the story keeps rendering its raw grill text and the résumé
    // gains a duplicate.
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({
      text: "Rebuilt the latency path, cutting p95 40%",
      derived_from_story_id: "story-1",
    });

    await user.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("surfaces an error when tailoring fails", async () => {
    server.use(
      http.post(`${BASE}/api/tailor`, () => new HttpResponse(null, { status: 409 })),
    );
    const user = userEvent.setup();
    renderWithProviders(<TailorContent />);

    await user.type(screen.getByLabelText("Job description"), "JD");
    await user.click(screen.getByRole("button", { name: /tailor my résumé/i }));

    expect(await screen.findByText(/couldn't tailor your résumé/i)).toBeInTheDocument();
  });
});
