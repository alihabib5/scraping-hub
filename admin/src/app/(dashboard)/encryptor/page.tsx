import { WebGenerator } from "@/components/encrypter/WebGenerator";
import { requireAdmin } from "@/lib/session";

export const metadata = { title: "Encryptor" };

export default async function EncryptorPage() {
  await requireAdmin();
  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="font-display text-[2rem] leading-tight text-ink-900">Encryptor</h1>
        <p className="mt-2 max-w-3xl text-sm text-ink-500">
          The Encrypter&apos;s .SHC Key Generator. Make a bot <code className="text-ink-700">license.shc</code>, or the Windows
          app&apos;s <code className="text-ink-700">credentials.shc</code> after a portal password changes. Everything is encrypted
          in this browser; nothing is uploaded.
        </p>
      </header>
      <div className="mt-8 max-w-[44rem]">
        <WebGenerator />
      </div>
    </div>
  );
}
