import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { JobsContent } from "@/app/jobs/JobsContent";
import { mockJobs } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/utils";

const BASE = "http://localhost:8080";

describe("Jobs — Find jobs", () => {
  it("runs discovery and shows the fresh matches", async () => {
    // Start with no matches.
    server.use(
      http.get(`${BASE}/api/jobs`, () =>
        HttpResponse.json({ ...mockJobs, accepted: [], is_empty: true, ran: false }),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<JobsContent />);

    expect(await screen.findByText(/no job matches yet/i)).toBeInTheDocument();

    // Find jobs → POST /api/jobs/discover (default handler returns mockJobs).
    await user.click(screen.getByRole("button", { name: /find jobs/i }));

    // The fresh accepted match renders (from the discovery result).
    expect(await screen.findByText(/staff engineer — globex/i)).toBeInTheDocument();
  });
});
