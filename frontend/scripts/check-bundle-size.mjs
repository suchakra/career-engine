#!/usr/bin/env node
// Bundle-size budget gate (AD-16.8 / §8 open-item #3).
//
// After `next build`, this reads the App Router build manifests and sums the
// gzipped size of every JS chunk each route pulls on first load — the same
// "First Load JS" notion Next prints. It fails (exit 1) if any route exceeds the
// budget, so a careless dependency can't silently bloat the shell.
//
// Budget is generous by design (the shell today is ~90–125 kB First Load); it
// exists to catch regressions, not to micro-optimize. Override with BUDGET_KB.

import { gzipSync } from "node:zlib";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const NEXT_DIR = join(process.cwd(), ".next");
const BUDGET_KB = Number(process.env.BUDGET_KB ?? "250");

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (err) {
    console.error(`✗ Could not read ${path}. Did you run \`next build\` first?`);
    console.error(String(err));
    process.exit(2);
  }
}

/** Gzipped byte size of a built chunk on disk (0 if it's not a static asset). */
function gzipSize(file) {
  const abs = join(NEXT_DIR, file);
  try {
    statSync(abs);
  } catch {
    return 0; // non-file entries (e.g. inlined runtime) contribute nothing.
  }
  return gzipSync(readFileSync(abs)).length;
}

const appManifest = readJson(join(NEXT_DIR, "app-build-manifest.json"));
const buildManifest = readJson(join(NEXT_DIR, "build-manifest.json"));

// Shared chunks loaded on every route (framework, main, webpack runtime).
const shared = buildManifest.rootMainFiles ?? [];

const rows = Object.entries(appManifest.pages).map(([route, files]) => {
  const all = new Set([...shared, ...files].filter((f) => f.endsWith(".js")));
  const bytes = [...all].reduce((sum, f) => sum + gzipSize(f), 0);
  return { route, kb: bytes / 1024 };
});

rows.sort((a, b) => b.kb - a.kb);

let failed = false;
console.log(`\nFirst Load JS budget: ${BUDGET_KB} kB (gzip)\n`);
for (const { route, kb } of rows) {
  const over = kb > BUDGET_KB;
  failed ||= over;
  const mark = over ? "✗" : "✓";
  console.log(`  ${mark} ${route.padEnd(28)} ${kb.toFixed(1).padStart(7)} kB`);
}
console.log("");

if (failed) {
  console.error(`✗ One or more routes exceed the ${BUDGET_KB} kB First Load JS budget.`);
  process.exit(1);
}
console.log("✓ All routes within the First Load JS budget.");
