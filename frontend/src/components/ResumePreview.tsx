import type { RoleBlock, StructuredResume } from "@/lib/api/models";

function contactLine(r: StructuredResume): string {
  const c = r.contact;
  return [c.email, c.phone, c.location, ...(c.links ?? [])].filter(Boolean).join(" · ");
}

function Roles({ roles }: { roles: RoleBlock[] }): JSX.Element {
  return (
    <>
      {roles.map((role) => (
        <div key={`${role.title}|${role.org}|${role.dates}`} className="mb-3">
          <p className="text-sm font-medium">
            {role.title}
            {role.org ? ` — ${role.org}` : ""}
            {role.dates ? <span className="text-muted"> · {role.dates}</span> : null}
          </p>
          <ul className="ml-4 list-disc text-sm text-muted">
            {(role.bullets ?? []).map((b, j) => (
              <li key={`${b}-${j}`}>{b}</li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}

/**
 * A lightweight React preview of the tailored résumé (§4.5). The exact export
 * bytes still come from the server renderers behind `POST /api/resume/{fmt}`; this
 * is the on-screen approximation.
 */
export function ResumePreview({ resume }: { resume: StructuredResume }): JSX.Element {
  // The generated types mark list fields optional (server defaults them to []).
  const skills = resume.skills ?? [];
  const experience = resume.experience ?? [];
  const education = resume.education ?? [];
  return (
    <div className="rounded-card border border-border bg-card p-5 text-text">
      <h2 className="text-lg font-semibold">{resume.contact.name || "Your résumé"}</h2>
      {contactLine(resume) && (
        <p className="mb-3 text-xs text-muted">{contactLine(resume)}</p>
      )}
      {resume.summary && (
        <section className="mb-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Summary</h3>
          <p className="text-sm">{resume.summary}</p>
        </section>
      )}
      {skills.length > 0 && (
        <section className="mb-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Skills</h3>
          <p className="text-sm">{skills.join(" · ")}</p>
        </section>
      )}
      {experience.length > 0 && (
        <section className="mb-3">
          <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted">
            Experience
          </h3>
          <Roles roles={experience} />
        </section>
      )}
      {education.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted">
            Education
          </h3>
          <Roles roles={education} />
        </section>
      )}
    </div>
  );
}
