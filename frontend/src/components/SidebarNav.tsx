"use client";

import {
  LayoutDashboard,
  FolderGit2,
  MessagesSquare,
  Briefcase,
  FileText,
  Settings,
  Mail,
  GraduationCap,
  Scale,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ComponentType } from "react";

import { isFeatureEnabled, type Feature } from "@/lib/flags";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  /** When set, the item renders only if the feature is enabled (ARCHITECTURE §17). */
  feature?: Feature;
}

interface NavGroup {
  /** Group heading; null renders an ungrouped top-level item. */
  heading: string | null;
  items: NavItem[];
}

/**
 * Nav (PHASE10_UI_MOCKUP.md §3): Dashboard · BUILD(Portfolio, Grill) ·
 * APPLY(Jobs, Tailor) · Settings. The PREPARE group is the open-core seam
 * (ARCHITECTURE §17 / AD-17.3): its items are feature-flagged and hidden until a
 * build enables them, so a premium/private layer lights them up without a core edit.
 */
const NAV: NavGroup[] = [
  { heading: null, items: [{ href: "/dashboard", label: "Dashboard", Icon: LayoutDashboard }] },
  {
    heading: "BUILD",
    items: [
      { href: "/portfolio", label: "Portfolio", Icon: FolderGit2 },
      { href: "/grill", label: "Grill", Icon: MessagesSquare },
    ],
  },
  {
    heading: "APPLY",
    items: [
      { href: "/jobs", label: "Jobs", Icon: Briefcase },
      { href: "/tailor", label: "Tailor", Icon: FileText },
      { href: "/outreach", label: "Outreach", Icon: Mail, feature: "outreach" },
    ],
  },
  {
    heading: "PREPARE",
    items: [
      { href: "/interview", label: "Interview", Icon: GraduationCap, feature: "interview" },
      { href: "/salary", label: "Salary", Icon: Scale, feature: "salary" },
    ],
  },
  { heading: null, items: [{ href: "/settings", label: "Settings", Icon: Settings }] },
];

export function SidebarNav(): JSX.Element {
  const pathname = usePathname();
  // Drop feature-flagged items that aren't enabled, then any group left empty
  // (so the PREPARE heading never renders alone in the OSS build).
  const groups = NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.feature || isFeatureEnabled(item.feature)),
  })).filter((group) => group.items.length > 0);

  return (
    <nav aria-label="Primary" className="flex flex-col gap-4">
      {groups.map((group, i) => (
        <div key={group.heading ?? `top-${i}`} className="flex flex-col gap-1">
          {group.heading && (
            <p className="px-3 pt-2 text-xs font-semibold uppercase tracking-wide text-muted">
              {group.heading}
            </p>
          )}
          {group.items.map(({ href, label, Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-tap items-center gap-3 rounded-card px-3 text-sm",
                  active
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-text hover:bg-card",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
