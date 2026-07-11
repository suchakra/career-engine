import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardContent } from "@/app/dashboard/DashboardContent";
import { mockDashboard } from "@/test/msw/handlers";
import { renderWithProviders } from "@/test/utils";

describe("Dashboard read view", () => {
  it("renders live data from the mocked /api/dashboard endpoint", async () => {
    renderWithProviders(<DashboardContent />);

    // Progress meter + application count come from the mocked DashboardResponse.
    expect(await screen.findByText(mockDashboard.progress_meter)).toBeInTheDocument();
    expect(screen.getByText(String(mockDashboard.application_count))).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/haven't grilled in 6 days/i)).toBeInTheDocument(),
    );
  });

  it("prompts to set up a key on first run (no key resolved)", async () => {
    // Default MSW GET /api/key → { has_key: false } → the pre-flight key card shows.
    renderWithProviders(<DashboardContent />);
    expect(await screen.findByText(/set up your gemini key/i)).toBeInTheDocument();
  });
});
