// The sign-in screen: Sign in, or request an account. window.scrapingHub comes from preload.js.
const $ = (id) => document.getElementById(id);
const hub = window.scrapingHub;
const MIN_PASSWORD = 8; // as the engine requires (server/app/core/accounts.py)
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

async function showSetupIfNoAccounts() {
  $("setup").hidden = (await hub.accountCount()) > 0;
}

// -- tabs -------------------------------------------------------------------

const tabs = [$("tab-signin"), $("tab-signup")];

function show(which) {
  for (const tab of tabs) {
    const on = tab.id === `tab-${which}`;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    $(tab.getAttribute("aria-controls")).hidden = !on;
  }
  $("requested").hidden = true;
  (which === "signin" ? $("in-email") : $("up-name")).focus();
}

tabs.forEach((tab, i) => {
  tab.addEventListener("click", () => show(tab.id.slice(4)));
  tab.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const next = tabs[(i + 1) % tabs.length];
    show(next.id.slice(4));
    next.focus();
  });
});

function busy(button, on, label) {
  button.disabled = on;
  button.textContent = label;
}

// -- sign in ----------------------------------------------------------------

$("signin").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = $("in-email").value.trim();
  const password = $("in-password").value;
  if (!email || !password) {
    $("in-error").textContent = "Enter your email and password.";
    (email ? $("in-password") : $("in-email")).focus();
    return;
  }
  $("in-error").textContent = "";
  busy($("in-submit"), true, "Signing in…");
  const r = await hub.signIn(email, password);
  // On success the app loads the console in this window; only failures land here.
  if (!r.ok) {
    $("in-error").textContent = r.message;
    $("in-password").value = "";
    $("in-password").focus();
    busy($("in-submit"), false, "Sign in");
  }
});

$("load").addEventListener("click", async () => {
  const r = await hub.updateCredentials();
  if (r.code !== "cancelled") $("in-error").textContent = r.ok ? "" : r.message || "";
  await showSetupIfNoAccounts();
});

// -- create account ---------------------------------------------------------

function mark(input, bad) {
  input.setAttribute("aria-invalid", String(bad));
}

function confirmHint() {
  const p = $("up-password").value, c = $("up-confirm").value;
  const mismatch = c.length > 0 && p !== c;
  $("up-confirm-hint").textContent = mismatch ? "The passwords don't match." : "";
  $("up-confirm-hint").classList.toggle("bad", mismatch);
  mark($("up-confirm"), mismatch);
}
$("up-confirm").addEventListener("input", confirmHint);
$("up-password").addEventListener("input", () => {
  mark($("up-password"), false);
  $("up-password-hint").classList.remove("bad");
  if ($("up-confirm").value) confirmHint();
});
for (const id of ["up-name", "up-email"]) $(id).addEventListener("input", () => mark($(id), false));

/** The first problem with the form, as [input, message], or null when it can be sent. */
function problem() {
  const name = $("up-name").value.trim();
  if (name.length < 2) return [$("up-name"), "Enter a display name of at least 2 characters."];
  if (!EMAIL.test($("up-email").value.trim())) return [$("up-email"), "Enter a valid email address."];
  if ($("up-password").value.length < MIN_PASSWORD) {
    $("up-password-hint").classList.add("bad");
    return [$("up-password"), `Use a password of at least ${MIN_PASSWORD} characters.`];
  }
  if ($("up-password").value !== $("up-confirm").value) return [$("up-confirm"), "The passwords don't match."];
  return null;
}

$("signup").addEventListener("submit", async (e) => {
  e.preventDefault();
  const found = problem();
  if (found) {
    const [input, message] = found;
    mark(input, true);
    $("up-error").textContent = message;
    input.focus();
    return;
  }
  $("up-error").textContent = "";
  busy($("up-submit"), true, "Sending request…");
  const email = $("up-email").value.trim();
  const r = await hub.signUp($("up-name").value.trim(), email, $("up-password").value);
  busy($("up-submit"), false, "Request account");
  if (!r.ok) {
    $("up-error").textContent = r.message;
    return;
  }
  $("signup").reset();
  $("signup").hidden = true;
  $("requested-email").textContent = email.toLowerCase();
  $("requested").hidden = false;
  $("back").focus();
  $("in-email").value = email.toLowerCase();
});

$("back").addEventListener("click", () => {
  show("signin");
  $("in-password").focus();
});

showSetupIfNoAccounts();
