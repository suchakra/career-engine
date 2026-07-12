import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ProfileForm } from "@/components/forms/ProfileForm";
import { server } from "@/test/msw/server";
import { makeTestQueryClient, renderWithProviders } from "@/test/utils";

const BASE = "http://localhost:8080";
const PROFILE_KEY = ["profile"] as const;

/**
 * A stateful fake server for the profile resource. The ['profile'] key is now a REAL
 * query (GET /api/profile), so `onSettled`'s invalidate refetches it — the cache always
 * reconciles to whatever the server holds. Asserting the cache therefore only means
 * something if the GET reflects what the write did, which is what this gives us.
 */
function fakeProfileServer(stored: Record<string, unknown>, { failWrite = false } = {}): void {
  server.use(
    http.get(`${BASE}/api/profile`, () => HttpResponse.json(stored)),
    http.post(`${BASE}/api/profile`, async ({ request }) => {
      if (failWrite) return new HttpResponse(null, { status: 500 });
      stored = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(stored);
    }),
  );
}

describe("ProfileForm optimistic write", () => {
  it("happy path: writes through and the cache settles on the persisted value", async () => {
    fakeProfileServer({ name: "Original", email: "a@b.com", location: "Berlin", links: [] });

    const user = userEvent.setup();
    const client = makeTestQueryClient();
    renderWithProviders(<ProfileForm />, { client });
    await screen.findByDisplayValue("Original");

    const nameField = screen.getByLabelText("Full name");
    await user.clear(nameField);
    await user.type(nameField, "Jane Doe");
    await user.click(screen.getByRole("button", { name: /save/i }));

    // onSuccess surfaced a success toast, and the cache reconciles to the stored value.
    expect(await screen.findByText(/profile saved/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(client.getQueryData(PROFILE_KEY)).toMatchObject({ name: "Jane Doe" }),
    );
  });

  it("rollback: the failed edit never sticks and a Toast is surfaced", async () => {
    fakeProfileServer({ name: "Original", email: "a@b.com", location: "Berlin", links: [] }, {
      failWrite: true,
    });

    const user = userEvent.setup();
    const client = makeTestQueryClient();
    renderWithProviders(<ProfileForm />, { client });
    await screen.findByDisplayValue("Original");

    const nameField = screen.getByLabelText("Full name");
    await user.clear(nameField);
    await user.type(nameField, "New Name");
    await user.click(screen.getByRole("button", { name: /save/i }));

    // onError rolled the optimistic patch back and raised an error toast; the cache
    // ends on the server's unchanged value, never the edit that failed.
    expect(await screen.findByText(/changes were reverted/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(client.getQueryData(PROFILE_KEY)).toMatchObject({ name: "Original" }),
    );
  });
});

describe("ProfileForm hydration", () => {
  it("hydrates the fields from the persisted profile", async () => {
    // Before GET /api/profile existed, the form mounted empty on every visit — so a
    // saved profile looked like it had never persisted at all.
    renderWithProviders(<ProfileForm />);

    expect(await screen.findByDisplayValue("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Remote · UK")).toBeInTheDocument();
  });

  it("keeps Save disabled when the profile can't be read (data-loss prevention)", async () => {
    // Saving on top of a profile we never loaded would post a partial body, and the
    // store's full-document write would blank email/phone/links.
    server.use(
      http.get(`${BASE}/api/profile`, () => new HttpResponse(null, { status: 500 })),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProfileForm />);

    await user.type(screen.getByLabelText("Full name"), "Jane Doe");
    // Dirty, not pending — yet Save stays disabled because there is nothing to merge into.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /save/i })).toBeDisabled(),
    );
  });

  it("preserves fields it does not edit (the store does a full-document write)", async () => {
    let posted: Record<string, unknown> | null = null;
    server.use(
      http.post(`${BASE}/api/profile`, async ({ request }) => {
        posted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(posted);
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProfileForm />);
    await screen.findByDisplayValue("Ada Lovelace");

    const nameField = screen.getByLabelText("Full name");
    await user.clear(nameField);
    await user.type(nameField, "Ada L.");
    await user.click(screen.getByRole("button", { name: /save/i }));

    // The edited fields change; email/phone/links ride along untouched instead of
    // being blanked back to their server defaults.
    await waitFor(() =>
      expect(posted).toMatchObject({
        name: "Ada L.",
        location: "Remote · UK",
        email: "ada@example.com",
        phone: "+1 555 0100",
        links: ["https://github.com/ada"],
      }),
    );
  });
});
