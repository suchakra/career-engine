import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { GrillContent } from "@/app/grill/GrillContent";
import { grillFrame, sseStream } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/utils";

const BASE = "http://localhost:8080";

describe("Grill streaming", () => {
  it("seeds the session, streams a turn, and renders the server banner", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GrillContent />);

    await user.type(screen.getByLabelText("Career history"), "I led the platform team at Acme.");
    await user.click(screen.getByRole("button", { name: /start grilling/i }));

    // The streamed assistant turn appears in the transcript…
    expect(
      await screen.findByText(/put a number on that improvement/i),
    ).toBeInTheDocument();
    // …and the "currently grilling" banner is the server's label (never re-derived).
    expect(screen.getByText(/currently grilling: senior engineer — acme/i)).toBeInTheDocument();
    // Back at a question, the composer is available again.
    expect(screen.getByLabelText("Your answer")).toBeInTheDocument();
  });

  it("seeds the grill from an uploaded résumé", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GrillContent />);

    const file = new File([new Uint8Array([1, 2, 3])], "resume.pdf", {
      type: "application/pdf",
    });
    await user.upload(screen.getByLabelText("Résumé file"), file);

    // The upload seeds the session → the streamed opening question appears.
    expect(
      await screen.findByText(/put a number on that improvement/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/uploaded résumé: resume.pdf/i)).toBeInTheDocument();
  });

  it("surfaces a mid-stream error frame without crashing", async () => {
    server.use(
      http.get(`${BASE}/api/grill/stream`, () => {
        const body = grillFrame("error", {
          message: "The model is busy.",
          rate_limited: true,
        });
        return new HttpResponse(sseStream([body]), {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<GrillContent />);

    await user.type(screen.getByLabelText("Career history"), "seed");
    await user.click(screen.getByRole("button", { name: /start grilling/i }));

    await waitFor(() =>
      expect(screen.getByText(/the model is busy/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/rate limited/i)).toBeInTheDocument();
  });
});
