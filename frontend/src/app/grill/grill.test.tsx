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

    await user.type(await screen.findByLabelText("Career history"), "I led the platform team at Acme.");
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
    await user.upload(await screen.findByLabelText("Résumé file"), file);

    // The upload seeds the session → the streamed opening question appears.
    expect(
      await screen.findByText(/put a number on that improvement/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/uploaded résumé: resume.pdf/i)).toBeInTheDocument();
  });

  it("shows progress WHILE the résumé is being parsed, not just after", async () => {
    // The parse is a slow vision call. Previously `streaming` only flipped inside
    // runStream(), so for its whole duration the user stared at a dead screen showing
    // just the upload bubble — with no sign anything was happening.
    let release!: () => void;
    const parsed = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post(`${BASE}/api/grill/resume`, async () => {
        await parsed;
        return HttpResponse.json({
          phase: "grilling",
          frontier_label: "Senior Engineer — Acme",
          awaiting: "question",
        });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<GrillContent />);

    const file = new File([new Uint8Array([1, 2, 3])], "resume.pdf", {
      type: "application/pdf",
    });
    await user.upload(await screen.findByLabelText("Résumé file"), file);

    // Still parsing (the handler hasn't returned) — the progress indicator is up.
    expect(await screen.findByRole("status")).toHaveTextContent(/typing/i);

    release();
    // …and the stream still lands the opening question afterwards.
    expect(
      await screen.findByText(/put a number on that improvement/i),
    ).toBeInTheDocument();
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

    await user.type(await screen.findByLabelText("Career history"), "seed");
    await user.click(screen.getByRole("button", { name: /start grilling/i }));

    await waitFor(() =>
      expect(screen.getByText(/the model is busy/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/rate limited/i)).toBeInTheDocument();
  });

  it("RESUMES an existing session instead of showing the upload card", async () => {
    // The bug: /grill decided what to render from in-memory state, so a fresh page load
    // always showed "Start grilling" — stranding anyone with a live session, including a
    // user who had just clicked "Grill me about this" in the Portfolio.
    server.use(
      http.get(`${BASE}/api/grill`, () =>
        HttpResponse.json({
          has_session: true,
          phase: "grilling",
          frontier_label: "Senior Engineer — Acme",
          awaiting: "question",
          current_question: "What did that migration actually save?",
          checkpoint_summary: "",
        }),
      ),
    );

    renderWithProviders(<GrillContent />);

    // The pending question is rehydrated from persisted state — no re-ask, no model call…
    expect(
      await screen.findByText(/what did that migration actually save\?/i),
    ).toBeInTheDocument();
    // …the server's banner shows…
    expect(screen.getByText(/currently grilling: senior engineer — acme/i)).toBeInTheDocument();
    // …the composer is ready, and the start card is GONE.
    expect(screen.getByLabelText("Your answer")).toBeInTheDocument();
    expect(screen.queryByLabelText("Résumé file")).not.toBeInTheDocument();
  });
});
