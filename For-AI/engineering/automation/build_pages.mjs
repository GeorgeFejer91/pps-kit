#!/usr/bin/env node
/** Assemble the ignored GitHub Pages artifact from canonical product inputs. */

import { cp, lstat, mkdir, readFile, rm, stat } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";


const scriptPath = fileURLToPath(import.meta.url);
const scriptDir = dirname(scriptPath);
const root = resolve(scriptDir, "../../..");
const website = join(root, "website");
const designerFrontend = join(root, "apps", "designer", "frontend");
const designerCompiled = join(designerFrontend, "compiled");
const runnerCompiled = join(root, "apps", "runner", "compiled");
const resources = join(root, "packages", "pps-resources");
const companionAssets = ["companion.js", "text-layout.js", "style.css"];
const companionVendorFiles = [
  "LICENSE-MPL-2.0.txt",
  "NOTICE.md",
  "vdoninja-sdk.js",
  "vdoninja-sdk.min.js",
];
const companionVendorRoot = join("vendor", "vdoninja", "1.5.5");
const companionResources = [
  ...companionAssets.map((asset) => `../assets/${asset}`),
  "../vendor/vdoninja/1.5.5/vdoninja-sdk.min.js",
].sort();
const canonicalOutput = join(root, "dist", "pages");

async function prepareOutput(output) {
  const resolved = resolve(output);
  const existing = await lstat(resolved).catch((error) => {
    if (error.code === "ENOENT") return null;
    throw error;
  });
  if (existing && resolved !== canonicalOutput) {
    throw new Error("A custom Pages output must be a new directory; existing files are preserved.");
  }
  // Windows junctions are symbolic links to Node. Check every ancestor before
  // replacing the one owned artifact directory or writing a fresh custom one.
  for (let path = resolved; ; path = dirname(path)) {
    const details = await lstat(path).catch((error) => {
      if (error.code === "ENOENT") return null;
      throw error;
    });
    if (details?.isSymbolicLink()) throw new Error("Pages output cannot traverse a symbolic link or junction.");
    if (dirname(path) === path) break;
  }
  if (existing) {
    if (!existing.isDirectory()) throw new Error("The canonical Pages output must be a directory.");
    await rm(resolved, { recursive: true });
  }
  await mkdir(resolved, { recursive: true });
  return resolved;
}

async function requireFile(path, label) {
  const details = await stat(path).catch(() => null);
  if (!details?.isFile()) throw new Error(`Missing ${label}: ${path}`);
}

async function copyVerified(source, destination, label) {
  const existing = await stat(destination).catch(() => null);
  if (existing) throw new Error(`${label} collides with another Pages input: ${destination}`);
  await mkdir(dirname(destination), { recursive: true });
  await cp(source, destination);
  const [sourceBytes, destinationBytes] = await Promise.all([
    readFile(source),
    readFile(destination),
  ]);
  if (!sourceBytes.equals(destinationBytes)) {
    throw new Error(`${label} changed while staging Pages: ${destination}`);
  }
}

function referencedCompanionResources(html) {
  const scripts = [...html.matchAll(/<script\b[^>]*\bsrc=(["'])(.*?)\1/gu)]
    .map((match) => match[2]);
  const links = [...html.matchAll(/<link\b[^>]*\bhref=(["'])(.*?)\1/gu)]
    .map((match) => match[2]);
  return [...scripts, ...links].sort();
}

export async function assemblePages(output = canonicalOutput) {
  const resolvedOutput = resolve(output);
  const companionIndex = join(runnerCompiled, "companion", "index.html");

  await requireFile(join(designerCompiled, "index.html"), "compiled Designer frontend");
  await requireFile(companionIndex, "compiled Runner companion");
  await requireFile(join(website, "CNAME"), "tracked Pages CNAME");
  for (const asset of companionAssets) {
    await requireFile(join(runnerCompiled, "assets", asset), `compiled Runner companion asset ${asset}`);
  }
  for (const file of companionVendorFiles) {
    await requireFile(join(runnerCompiled, companionVendorRoot, file), `compiled VDO.Ninja file ${file}`);
  }

  const cname = (await readFile(join(website, "CNAME"), "utf8")).trim();
  if (cname !== "ppskit.qzz.io") throw new Error(`Unexpected CNAME: ${cname}`);

  const companionHtml = await readFile(companionIndex, "utf8");
  const referencedResources = referencedCompanionResources(companionHtml);
  if (JSON.stringify(referencedResources) !== JSON.stringify(companionResources)) {
    throw new Error(
      `Runner companion resource allowlist drift: expected ${companionResources.join(", ")}; found ${referencedResources.join(", ")}`,
    );
  }

  await prepareOutput(resolvedOutput);
  await cp(website, resolvedOutput, { recursive: true });
  await cp(designerCompiled, join(resolvedOutput, "app"), { recursive: true });
  await cp(join(designerFrontend, "pps_toolkit_icon.png"), join(resolvedOutput, "app", "pps_toolkit_icon.png"));
  await cp(join(resources, "assets", "preloads"), join(resolvedOutput, "assets", "preloads"), { recursive: true });
  await cp(join(resources, "study_templates"), join(resolvedOutput, "study_templates"), { recursive: true });

  await copyVerified(
    companionIndex,
    join(resolvedOutput, "experiment-runner", "index.html"),
    "Runner companion HTML",
  );
  for (const asset of companionAssets) {
    await copyVerified(
      join(runnerCompiled, "assets", asset),
      join(resolvedOutput, "assets", asset),
      `Runner companion asset ${asset}`,
    );
  }
  for (const file of companionVendorFiles) {
    await copyVerified(
      join(runnerCompiled, companionVendorRoot, file),
      join(resolvedOutput, companionVendorRoot, file),
      `VDO.Ninja 1.5.5 file ${file}`,
    );
  }

  const forbidden = [
    join(resolvedOutput, "For-AI"),
    join(resolvedOutput, "participant_data"),
    join(resolvedOutput, "generated_outputs"),
    join(resolvedOutput, "assets", "desktop.js"),
  ];
  for (const path of forbidden) {
    const details = await stat(path).catch(() => null);
    if (details) throw new Error(`Forbidden Pages content: ${path}`);
  }

  return resolvedOutput;
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath.toLowerCase() === resolve(scriptPath).toLowerCase()) {
  const output = await assemblePages(process.argv[2]);
  process.stdout.write(`${output}\n`);
}
