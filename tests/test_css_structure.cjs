"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.resolve(__dirname, "..");
const PAGE_ROOT = path.join(ROOT, "pages");
const pairs = new Map([["(", ")"], ["[", "]"], ["{", "}"]]);
const closing = new Set(pairs.values());

function walk(directory) {
  return fs.readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const fullPath = path.join(directory, entry.name);
    return entry.isDirectory() ? walk(fullPath) : [fullPath];
  });
}

function checkStructure(source, label) {
  const issues = [];
  const stack = [];
  let index = 0;
  let line = 1;
  let column = 1;

  function advance(end) {
    while (index < end) {
      if (source[index++] === "\n") {
        line += 1;
        column = 1;
      } else {
        column += 1;
      }
    }
  }

  while (index < source.length) {
    const char = source[index];
    const next = source[index + 1];

    if (char === "/" && next === "*") {
      const end = source.indexOf("*/", index + 2);
      if (end < 0) {
        issues.push(`${label}:${line}:${column}: unterminated comment`);
        break;
      }
      advance(end + 2);
      continue;
    }

    if (char === "\"" || char === "'") {
      const quote = char;
      const startLine = line;
      const startColumn = column;
      advance(index + 1);
      let closed = false;
      while (index < source.length) {
        if (source[index] === "\\") {
          advance(Math.min(source.length, index + 2));
          continue;
        }
        if (source[index] === quote) {
          advance(index + 1);
          closed = true;
          break;
        }
        advance(index + 1);
      }
      if (!closed) {
        issues.push(`${label}:${startLine}:${startColumn}: unterminated string`);
        break;
      }
      continue;
    }

    if (char === "\\") {
      if (index + 1 >= source.length) {
        issues.push(`${label}:${line}:${column}: trailing escape`);
        break;
      }
      advance(index + 2);
      continue;
    }

    if (pairs.has(char)) {
      stack.push({close: pairs.get(char), char, line, column});
    } else if (closing.has(char)) {
      const top = stack.at(-1);
      if (!top || top.close !== char) {
        issues.push(`${label}:${line}:${column}: unexpected ${char}`);
      } else {
        stack.pop();
      }
    }
    advance(index + 1);
  }

  for (const item of stack) {
    issues.push(`${label}:${item.line}:${item.column}: unclosed ${item.char}, expected ${item.close}`);
  }
  return issues;
}

test("page styles and embedded HTML previews have balanced CSS structure", () => {
  const pageFiles = walk(PAGE_ROOT);
  const cssFiles = pageFiles.filter(file => file.endsWith(".css"));
  const htmlFiles = pageFiles.filter(file => file.endsWith(".html"));
  const templateFiles = fs.readdirSync(path.join(ROOT, "tools"))
    .filter(name => name.endsWith(".tpl.html"))
    .map(name => path.join(ROOT, "tools", name));
  const issues = [];

  for (const file of cssFiles) {
    issues.push(...checkStructure(fs.readFileSync(file, "utf8"), path.relative(ROOT, file)));
  }
  for (const file of [...htmlFiles, ...templateFiles]) {
    const html = fs.readFileSync(file, "utf8");
    let styleIndex = 0;
    for (const match of html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style\s*>/gi)) {
      styleIndex += 1;
      issues.push(...checkStructure(
        match[1],
        `${path.relative(ROOT, file)}:style-${styleIndex}`,
      ));
    }
  }

  assert.deepStrictEqual(issues, [], issues.join("\n"));
});
