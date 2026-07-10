import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ProfileForm } from "@/components/forms/ProfileForm";
import { server } from "@/test/msw/server";
import { makeTestQueryClient, renderWithProviders } from "@/test/utils";

const BASE = "http://localhost:8080";
const PROFILE_KEY = ["profile"] as const;

describe("ProfileForm optimistic write", () => {
  it("happy path: patches the cache optimistically and confirms on success", async () => {
    const user = userEvent.setup();
    const client = makeTestQueryClient();
    renderWithProviders(<ProfileForm />, { client });

    await user.type(screen.getByLabelText("Full name"), "Jane Doe");
    await user.click(screen.getByRole("button", { name: /save/i }));

    // onMutate patched the ['profile'] cache with the submitted value.
    await waitFor(() =>
      expect(client.getQueryData(PROFILE_KEY)).toMatchObject({ name: "Jane Doe" }),
    );
    // onSuccess surfaced a success toast.
    expect(await screen.findByText(/profile saved/i)).toBeInTheDocument();
  });

  it("rollback: reverts the cache and surfaces a Toast when the server 500s", async () => {
    server.use(
      http.post(`${BASE}/api/profile`, () => new HttpResponse(null, { status: 500 })),
    );

    const user = userEvent.setup();
    const client = makeTestQueryClient();
    // Seed a known prior value so we can assert the rollback restores it.
    client.setQueryData(PROFILE_KEY, { name: "Original" });
    renderWithProviders(<ProfileForm />, { client });

    await user.type(screen.getByLabelText("Full name"), "New Name");
    await user.click(screen.getByRole("button", { name: /save/i }));

    // onError rolled the cache back to the snapshot and raised an error toast.
    expect(await screen.findByText(/changes were reverted/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(client.getQueryData(PROFILE_KEY)).toMatchObject({ name: "Original" }),
    );
  });
});
