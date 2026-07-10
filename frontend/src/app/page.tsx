import { redirect } from "next/navigation";

/** The bare root simply routes into the app; guards decide login vs dashboard. */
export default function RootPage(): never {
  redirect("/dashboard");
}
