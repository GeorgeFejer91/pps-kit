#!/usr/bin/env node
/** Assemble the ignored GitHub Pages artifact from canonical product inputs. */

import { cp, mkdir, readFile, rm, stat } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";


const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDir, "../../..");
const website = join(root, "website");
const frontend = join(root, "apps", "designer", "frontend");
const compiled = join(frontend, "compiled");
const resources = join(root, "packages", "pps-resources");
const output = resolve(process.argv[2] || join(root, "dist", "pages"));

async function requireFile(path, label) {
  const details = await stat(path).catch(() => null);
  if (!details?.isFile()) throw new Error(`Missing ${label}: ${path}`);
}

await requireFile(join(compiled, "index.html"), "compiled Designer frontend");
await requireFile(join(website, "CNAME"), "tracked Pages CNAME");
const cname = (await readFile(join(website, "CNAME"), "utf8")).trim();
if (cname !== "ppskit.qzz.io") throw new Error(`Unexpected CNAME: ${cname}`);

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(website, output, { recursive: true });
await cp(compiled, join(output, "app"), { recursive: true });
await cp(join(frontend, "pps_toolkit_icon.png"), join(output, "app", "pps_toolkit_icon.png"));
await cp(join(resources, "assets", "preloads"), join(output, "assets", "preloads"), { recursive: true });
await cp(join(resources, "study_templates"), join(output, "study_templates"), { recursive: true });

const forbidden = [
  join(output, "For-AI"),
  join(output, "participant_data"),
  join(output, "generated_outputs"),
];
for (const path of forbidden) {
  const details = await stat(path).catch(() => null);
  if (details) throw new Error(`Forbidden Pages content: ${path}`);
}

process.stdout.write(`${output}\n`);
