"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { approve, checkSignIn, normalEmail, remove } from "@/lib/accounts";
import { adminEmails } from "@/lib/env";
import { endSession, requireAdmin, startSession } from "@/lib/session";

export interface SignInState {
  error: string;
  email: string; // React clears the form after an action; this puts the typed email back
}

export async function signIn(_: SignInState | null, form: FormData): Promise<SignInState> {
  const email = normalEmail(form.get("email"));
  // One answer for every failure, so the form does not reveal who is an admin.
  const refused = { error: "That email and password don't match an administrator.", email };
  if (!adminEmails().has(email)) return refused;
  const result = await checkSignIn(email, form.get("password"));
  if (result?.status !== "approved") return refused;
  await startSession(email);
  redirect("/");
}

export async function signOut() {
  await endSession();
  redirect("/login");
}

export async function approveAccount(form: FormData) {
  await approve(String(form.get("email")), await requireAdmin());
  revalidatePath("/");
}

export async function removeAccount(form: FormData) {
  const admin = await requireAdmin();
  const email = normalEmail(form.get("email"));
  if (email !== admin) await remove(email); // an admin cannot remove their own account and lock themselves out
  revalidatePath("/");
}
