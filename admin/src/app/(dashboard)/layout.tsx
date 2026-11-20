import Sidebar from "@/components/Sidebar";
import { accountName, countPending } from "@/lib/accounts";
import { requireAdmin } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const admin = await requireAdmin();
  const [name, pending] = await Promise.all([accountName(admin), countPending()]);
  return (
    <div className="min-h-screen md:flex">
      <Sidebar admin={admin} name={name} pending={pending} />
      <main className="min-w-0 flex-1 px-4 pb-16 pt-8 sm:px-8 md:pt-10">{children}</main>
    </div>
  );
}
