import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PortfolioContent } from "@/app/portfolio/PortfolioContent";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/utils";

const BASE = "http://localhost:8080";

// The entry actions navigate to /grill via next/navigation's router.
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("Portfolio actions (parity P4b)", () => {
  it("grills a chosen entry, then routes to /grill", async () => {
    let grilled: string | null = null;
    server.use(
      http.post(`${BASE}/api/experience/:id/grill`, ({ params }) => {
        grilled = String(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<PortfolioContent />);
    await screen.findByText(/Senior Engineer — Acme/i);

    await user.click(screen.getByRole("button", { name: /grill me about this/i }));

    await waitFor(() => expect(grilled).toBe("entry-1"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/grill"));
  });

  it("toggles the pin (highlight) on an entry", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/experience/:id/highlight`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<PortfolioContent />);
    // entry-1 is highlighted in the fixture → button reads "★ Pinned"; clicking unpins.
    await user.click(await screen.findByRole("button", { name: /pinned/i }));

    await waitFor(() => expect(body).toEqual({ highlighted: false }));
  });

  it("deletes a STAR story", async () => {
    let deleted: string | null = null;
    server.use(
      http.delete(`${BASE}/api/story/:id`, ({ params }) => {
        deleted = String(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<PortfolioContent />);
    await user.click(
      await screen.findByRole("button", { name: /delete story: latency spikes/i }),
    );

    await waitFor(() => expect(deleted).toBe("story-1"));
  });
});

describe("Master résumé (parity P4c)", () => {
  // jsdom implements neither URL.createObjectURL nor anchor downloads — assign mocks
  // directly (spyOn needs an existing property) and restore them afterwards.
  const origUrl = { createObjectURL: URL.createObjectURL, revokeObjectURL: URL.revokeObjectURL };
  afterEach(() => {
    Object.assign(URL, origUrl);
    vi.restoreAllMocks();
  });

  it("builds the master résumé, previews it, then exports it", async () => {
    const createObjectURL = vi.fn(() => "blob:x");
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const exported: string[] = [];
    server.use(
      http.post(`${BASE}/api/resume/:fmt`, ({ params }) => {
        exported.push(String(params.fmt));
        return HttpResponse.text("md", { headers: { "Content-Type": "text/markdown" } });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<PortfolioContent />);

    await user.click(await screen.findByRole("button", { name: /build master résumé/i }));

    // The preview renders every validated achievement the server assembled.
    expect(await screen.findByText(/Shipped billing v2/i)).toBeInTheDocument();
    expect(screen.getByText(/BSc Computer Science/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "PDF" }));
    await waitFor(() => expect(exported).toContain("pdf"));
    expect(createObjectURL).toHaveBeenCalled();
  });

  it("surfaces an error when the build fails", async () => {
    server.use(
      http.post(`${BASE}/api/master-resume`, () => new HttpResponse(null, { status: 500 })),
    );
    const user = userEvent.setup();
    renderWithProviders(<PortfolioContent />);

    await user.click(await screen.findByRole("button", { name: /build master résumé/i }));

    expect(await screen.findByText(/couldn't build your master résumé/i)).toBeInTheDocument();
  });
});
