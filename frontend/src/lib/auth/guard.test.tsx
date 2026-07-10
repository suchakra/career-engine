import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RedirectIfAuthed, RequireAuth } from "@/lib/auth/guard";
import { renderWithProviders } from "@/test/utils";

// Mock Firebase-backed auth with a controllable test double (no network).
const mockUseAuth = vi.fn();
vi.mock("@/lib/auth/context", () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock the App Router navigation hooks used by the guards.
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  usePathname: () => "/dashboard",
}));

describe("auth-guarded routing", () => {
  beforeEach(() => {
    replace.mockClear();
  });

  it("hides protected content and redirects to /login when unauthenticated", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    renderWithProviders(
      <RequireAuth>
        <p>Protected dashboard</p>
      </RequireAuth>,
    );
    expect(screen.queryByText("Protected dashboard")).not.toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("renders protected content when authenticated", () => {
    mockUseAuth.mockReturnValue({ user: { uid: "u1", email: "jane@example.com" }, loading: false });
    renderWithProviders(
      <RequireAuth>
        <p>Protected dashboard</p>
      </RequireAuth>,
    );
    expect(screen.getByText("Protected dashboard")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows the public login content to an unauthenticated visitor", () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false });
    renderWithProviders(
      <RedirectIfAuthed>
        <p>Sign in with Google</p>
      </RedirectIfAuthed>,
    );
    expect(screen.getByText("Sign in with Google")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("redirects an authenticated visitor away from login", () => {
    mockUseAuth.mockReturnValue({ user: { uid: "u1", email: "jane@example.com" }, loading: false });
    renderWithProviders(
      <RedirectIfAuthed>
        <p>Sign in with Google</p>
      </RedirectIfAuthed>,
    );
    expect(screen.queryByText("Sign in with Google")).not.toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/dashboard");
  });
});
