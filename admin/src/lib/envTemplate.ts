// The Scraping Hub settings template: server/.env.example, read into the fields the
// Encryptor's form shows. The file decides which settings exist and in what order;
// its blank lines decide the groups. Per-PC settings (the installer writes those on
// each PC) are left out, as make_credentials.py leaves them out.

import { ENV_EXAMPLE } from "@/lib/env-template";
import { NOT_INCLUDED, parseDotenv } from "@/lib/shc1";

export interface TemplateField {
  key: string;
  /** The example's value when it is a real default (true, 300, us-east-1); "" for a placeholder. */
  initial: string;
  /** The example's value when it is a placeholder (your_email_here); a value equal to it counts as not set. */
  placeholder: string;
  secret: boolean;
}

export interface TemplateGroup {
  title: string;
  fields: TemplateField[];
}

/**
 * Whether one of the TEMPLATE's example values only shows the shape of a setting.
 * Used on .env.example alone: a real value is never judged by it (a real address
 * may well contain "example.com"); see TemplateField.placeholder for that.
 */
export function isPlaceholder(value: string): boolean {
  const v = value.trim().replace(/^['"]|['"]$/g, "");
  return (
    !v ||
    /^your[_-]/i.test(v) ||
    /example\.(com|org)/i.test(v) ||
    /yourdomain/i.test(v) ||
    /USER:PASSWORD/.test(v)
  );
}

const SECRET = /PASSWORD|SECRET|API_KEY|ACCESS_KEY/i;

/** "MYFLORIDA_ACC1_USERNAME" -> "MYFLORIDA ACC1": what the keys of one group share. */
function titleFor(keys: string[]): string {
  const parts = keys.map((k) => k.split("_"));
  const shared: string[] = [];
  for (let i = 0; i < Math.min(...parts.map((p) => p.length)) - 1; i++) {
    const word = parts[0][i];
    if (parts.every((p) => p[i] === word)) shared.push(word);
    else break;
  }
  // No prefix shared by every key (e.g. RECIPIENT_EMAILS beside AWS_*): name each kind once.
  const words = shared.length ? [shared.join(" ")] : [...new Set(keys.map((k) => k.split("_")[0]))];
  return words.join(" · ").replace(/^Cal\b/, "CAL");
}

/** The template's settings in file order, grouped where the file leaves a blank line. */
export function templateGroups(text: string = ENV_EXAMPLE): TemplateGroup[] {
  const groups: TemplateField[][] = [[]];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) {
      if (groups.at(-1)!.length) groups.push([]);
      continue;
    }
    if (line.startsWith("#")) continue;
    const parsed = parseDotenv(line);
    const [key] = Object.keys(parsed);
    if (!key || NOT_INCLUDED.has(key.toUpperCase())) continue;
    const example = parsed[key];
    const shape = isPlaceholder(example);
    groups.at(-1)!.push({ key, initial: shape ? "" : example, placeholder: shape ? example : "", secret: SECRET.test(key) });
  }
  return groups.filter((g) => g.length).map((fields) => ({ title: titleFor(fields.map((f) => f.key)), fields }));
}

export const templateFields = (groups: TemplateGroup[]) => new Map(groups.flatMap((g) => g.fields.map((f) => [f.key, f] as const)));

/** A value someone actually set: not empty, and not just the template's own example for that setting. */
export const isSet = (field: TemplateField | undefined, value: string) =>
  !!value.trim() && !(field?.placeholder && value.trim() === field.placeholder);
