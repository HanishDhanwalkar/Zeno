/**
 * Permission gate. Python asks Node before every tool call; this module
 * classifies each call so safe ones auto-approve and risky ones prompt.
 */

import path from "node:path";

export type Verdict = "allow" | "prompt" | "deny";

export interface Classification {
  verdict: Verdict;
  reason: string;
}

/** Commands that warrant a confirmation prompt. */
const DANGEROUS_BASH: { re: RegExp; reason: string }[] = [
  { re: /\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\b/i, reason: "recursive force delete (rm -rf)" },
  { re: /\bsudo\b/i, reason: "privilege escalation (sudo)" },
  { re: /\bchmod\s+(-R\s+)?0?777\b/i, reason: "world-writable permissions (chmod 777)" },
  { re: /\bmkfs\b/i, reason: "filesystem format (mkfs)" },
  { re: /\bdd\s+if=/i, reason: "raw disk write (dd)" },
  { re: />\s*\/dev\/(sd|nvme|disk)/i, reason: "write to raw disk device" },
  { re: /:\(\)\s*\{.*\};:/, reason: "fork bomb" },
  { re: /\bformat\s+[a-z]:/i, reason: "drive format (Windows)" },
  { re: /\b(rmdir|rd)\s+\/s\b/i, reason: "recursive directory delete (Windows)" },
  { re: /\bdel\s+\/[sq]/i, reason: "recursive/quiet delete (Windows)" },
  { re: /\bgit\s+push\b.*--force\b/i, reason: "force push" },
  { re: /\bcurl\b.*\|\s*(sh|bash)\b/i, reason: "pipe remote script to shell" },
];

const SECRET_FILE = /(^|[\\/])\.env(\.|$)|\.secret(s)?($|\.)|id_rsa|\.pem$|\.key$/i;

function isInside(root: string, target: string): boolean {
  const rel = path.relative(root, target);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

export function classify(
  name: string,
  args: Record<string, unknown>,
  projectRoot: string,
): Classification {
  if (name === "read") return { verdict: "allow", reason: "read is safe" };

  if (name === "bash") {
    const cmd = String(args.command ?? "");
    for (const { re, reason } of DANGEROUS_BASH) {
      if (re.test(cmd)) return { verdict: "prompt", reason };
    }
    return { verdict: "allow", reason: "no dangerous pattern detected" };
  }

  if (name === "write" || name === "edit") {
    const p = String(args.path ?? "");
    if (SECRET_FILE.test(p)) {
      return { verdict: "prompt", reason: "writing to a secret/credentials file" };
    }
    const resolved = path.resolve(projectRoot, p);
    if (!isInside(projectRoot, resolved)) {
      return { verdict: "prompt", reason: "writing outside the project root" };
    }
    return { verdict: "allow", reason: "within project root" };
  }

  return { verdict: "prompt", reason: `unknown tool '${name}'` };
}
