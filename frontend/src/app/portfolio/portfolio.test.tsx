import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

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
