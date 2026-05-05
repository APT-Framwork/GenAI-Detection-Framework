// -----------------------------------------------------------------------------
// hunt-grammar.ts — client-side mirror of the server parser in
// apps/api/src/strix_api/services/hunt_service.py:parse_query.
//
// Both parsers MUST produce the same Token[] for a given input. Keep them
// in sync — the server parser is authoritative; this one drives autocomplete
// and pill rendering. Documented in docs/hunt-grammar.md.
// -----------------------------------------------------------------------------

export type HuntField = "host" | "user" | "technique" | "time" | "text";
export type HuntOp = "eq" | "contains";

export interface HuntToken {
  field: HuntField;
  op: HuntOp;
  value: string;
  /** Source span in the original query string — for the underline UI. */
  start: number;
  end: number;
}

export interface ParsedHunt {
  tokens: HuntToken[];
  errors: string[];
}

const TOKEN_RE =
  /(?<field>host|user|technique|time):(?:"(?<qval>[^"]*)"|(?<val>[^\s"]+))/gi;

const DURATION_RE = /^(\d+)\s*([smhd])$/i;
const TECHNIQUE_RE = /^T\d{4}(\.\d{3})?$/;

export function parseHunt(q: string): ParsedHunt {
  const tokens: HuntToken[] = [];
  const errors: string[] = [];
  if (!q || !q.trim()) return { tokens, errors };

  const textChunks: { text: string; start: number; end: number }[] = [];
  let cursor = 0;

  // Non-global iteration via exec loop so we get accurate indices.
  const re = new RegExp(TOKEN_RE.source, "gi");
  let m: RegExpExecArray | null;
  while ((m = re.exec(q)) !== null) {
    if (m.index > cursor) {
      const chunk = q.slice(cursor, m.index).trim();
      if (chunk) {
        textChunks.push({ text: chunk, start: cursor, end: m.index });
      }
    }
    cursor = m.index + m[0].length;

    const field = (m.groups?.field ?? "").toLowerCase() as HuntField;
    const value = (m.groups?.qval ?? m.groups?.val ?? "").trim();
    if (!value) {
      errors.push(`empty value for \`${field}:\``);
      continue;
    }

    let finalValue = value;
    if (field === "time") {
      if (!DURATION_RE.test(value) && Number.isNaN(Date.parse(value))) {
        errors.push(`\`time:${value}\` not understood (try 1h, 30m, 24h, 7d, or ISO)`);
        continue;
      }
    }
    if (field === "technique") {
      const up = value.toUpperCase();
      if (!TECHNIQUE_RE.test(up)) {
        errors.push(`\`technique:${value}\` doesn't look like a MITRE id (Txxxx[.yyy])`);
        continue;
      }
      finalValue = up;
    }

    tokens.push({
      field,
      op: "eq",
      value: finalValue,
      start: m.index,
      end: m.index + m[0].length,
    });
  }

  if (cursor < q.length) {
    const tail = q.slice(cursor).trim();
    if (tail) textChunks.push({ text: tail, start: cursor, end: q.length });
  }

  if (textChunks.length > 0) {
    const merged = textChunks.map((c) => c.text).join(" ");
    tokens.push({
      field: "text",
      op: "contains",
      value: merged,
      start: textChunks[0].start,
      end: textChunks[textChunks.length - 1].end,
    });
  }

  return { tokens, errors };
}
