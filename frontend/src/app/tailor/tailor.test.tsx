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
