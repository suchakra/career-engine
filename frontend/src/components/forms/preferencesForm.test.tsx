import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { PreferencesForm } from "@/components/forms/PreferencesForm";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/utils";

const BASE = "http://localhost:8080";

describe("PreferencesForm hydration", () => {
  it("hydrates the fields from the persisted rubric", async () => {
    // Before GET /api/preferences existed, the form mounted empty on every visit — so a
    // saved rubric looked like it had never persisted at all.
    const user = userEvent.setup();
    renderWithProviders(<PreferencesForm />);
    await user.click(screen.getByRole("button", { name: /job preferences/i })); // expand

    expect(await screen.findByDisplayValue("Staff Engineer")).toBeInTheDocument();
    expect(screen.getByDisplayValue("on-site")).toBeInTheDocument();
  });

  it("preserves fields it does not edit (the store does a full-document write)", async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.put(`${BASE}/api/preferences`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(posted);
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<PreferencesForm />);
    await user.click(screen.getByRole("button", { name: /job preferences/i })); // expand
    await screen.findByDisplayValue("Staff Engineer");

    const roles = screen.getByLabelText("Target roles");
    await user.clear(roles);
    await user.type(roles, "Staff Engineer, Principal Engineer");
    await user.click(screen.getByRole("button", { name: /save/i }));

    // The edited list changes; `nice_to_haves` (which no form edits) rides along
    // instead of being reset to empty on every save.
    await waitFor(() =>
      expect(posted).toMatchObject({
        target_roles: ["Staff Engineer", "Principal Engineer"],
        dealbreakers: ["on-site"],
        nice_to_haves: ["remote-first"],
      }),
    );
  });
});
