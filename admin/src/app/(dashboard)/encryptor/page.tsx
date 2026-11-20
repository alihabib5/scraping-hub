import { requireAdmin } from "@/lib/session";

import Encryptor from "./Encryptor";

export const metadata = { title: "Encryptor" };

export default async function EncryptorPage() {
  await requireAdmin();
  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="font-display text-3xl text-ink-900">Encryptor</h1>
        <p className="mt-1.5 max-w-3xl text-sm text-ink-500">
          Make the encrypted <code className="text-ink-700">credentials.shc</code> the installed app reads its portal logins
          from. Use it after a portal password changes, then load the file on each PC with Update credentials.
        </p>
      </header>
      <Encryptor />
    </div>
  );
}
