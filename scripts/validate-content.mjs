#!/usr/bin/env node
/**
 * Pre-build content validation.
 * Catches schema violations before Astro runs, giving clear error messages
 * instead of cryptic build failures on Cloudflare.
 */

import { readFileSync, readdirSync } from "fs";
import { join, resolve } from "path";

const ROOT = resolve(import.meta.dirname, "..");

const DIGEST_CATEGORIES = new Set([
  "Shutdown", "Censorship", "Arrest", "Policy", "Data", "Surveillance", "Other",
]);

const ARTICLE_CATEGORIES = new Set([
  "Censorship & Shutdowns",
  "VPN & Security",
  "ISP & Broadband",
  "Mobile & Data Plans",
  "Telecom & Infrastructure",
  "Digital Services",
  "Policy & Regulation",
]);

function parseFrontmatter(content, filepath) {
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) return null;
  const fm = {};
  for (const line of match[1].split("\n")) {
    const kv = line.match(/^(\w[\w-]*):\s*(.*)/);
    if (kv) fm[kv[1].trim()] = kv[2].trim();
  }
  return fm;
}

function parseTagsFromRaw(content) {
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) return null;
  const block = match[1];
  const tagsMatch = block.match(/^tags:\s*\n((?:[ \t]+-[^\n]*\n?)*)/m);
  if (!tagsMatch) {
    // Check if tags is inline (e.g., "tags: []")
    const inlineMatch = block.match(/^tags:\s*\[([^\]]*)\]/m);
    if (inlineMatch) return inlineMatch[1].trim() === "" ? [] : [inlineMatch[1]];
    return null; // bare "tags:" with no value = null
  }
  return tagsMatch[1].trim().length > 0 ? ["ok"] : [];
}

function walkMdx(dir) {
  try {
    return readdirSync(dir, { withFileTypes: true })
      .flatMap((e) =>
        e.isDirectory()
          ? walkMdx(join(dir, e.name))
          : e.name.endsWith(".mdx") || e.name.endsWith(".md")
          ? [join(dir, e.name)]
          : []
      );
  } catch {
    return [];
  }
}

let errors = 0;

function check(filepath, fm, rawContent) {
  const rel = filepath.replace(ROOT + "/", "");

  // Validate digest collection
  if (filepath.includes("/content/digest/")) {
    const cat = fm.category?.replace(/^"|"$/g, "");
    if (!cat || !DIGEST_CATEGORIES.has(cat)) {
      console.error(`\n❌ ${rel}`);
      console.error(`   category: "${cat}" is not a valid digest category`);
      console.error(`   Valid: ${[...DIGEST_CATEGORIES].join(" | ")}`);
      errors++;
    }
    const tags = parseTagsFromRaw(rawContent);
    if (tags === null) {
      console.error(`\n❌ ${rel}`);
      console.error(`   tags: is null (bare key with no value) — must be an array`);
      console.error(`   Fix: add "tags: []" or list items under "tags:"`);
      errors++;
    }
    return;
  }

  // Validate articles collection
  if (filepath.includes("/content/articles/")) {
    const tags = parseTagsFromRaw(rawContent);
    if (tags === null) {
      console.error(`\n❌ ${rel}`);
      console.error(`   tags: is null — must be an array`);
      errors++;
    }
  }
}

const contentDir = join(ROOT, "src/content");
const files = walkMdx(contentDir);

for (const filepath of files) {
  const raw = readFileSync(filepath, "utf8");
  const fm = parseFrontmatter(raw, filepath);
  if (fm) check(filepath, fm, raw);
}

if (errors > 0) {
  console.error(`\n✗ Content validation failed: ${errors} error(s). Fix before building.\n`);
  process.exit(1);
} else {
  console.log(`✓ Content validation passed (${files.length} files checked)`);
}
