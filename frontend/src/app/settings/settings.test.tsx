import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { SettingsContent } from "@/app/settings/SettingsContent";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/utils";

const BASE = "http://localhost:8080";

describe("Settings — BYOK key", () => {
  it("shows 'no key', saves one, and reflects the saved state", async () => {
    let saved: string | null = null;
    let hasKey = false;
    server.use(
      http.get(`${BASE}/api/key`, () => HttpResponse.json({ has_key: hasKey })),
      http.post(`${BASE}/api/key`, async ({ request }) => {
        saved = ((await request.json()) as { api_key: string }).api_key;
        hasKey = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<SettingsContent />);

    expect(await screen.findByText(/no key yet/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Gemini API key"), "AIzaSyMYKEY123456");
    await user.click(screen.getByRole("button", { name: /save & use this key/i }));

    // Sent to the API, and the status re-fetches to "using your saved key".
    await waitFor(() => expect(saved).toBe("AIzaSyMYKEY123456"));
    expect(await screen.findByText(/using your saved key/i)).toBeInTheDocument();
  });
});
