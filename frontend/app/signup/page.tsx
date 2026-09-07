"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import styles from "../auth.module.css";

function friendly(detail: string) {
  const value = String(detail || "SIGNUP_FAILED").replace(/_/g, " ");
  if (value.includes("EMAIL ALREADY REGISTERED")) return "That email already has an account.";
  if (value.includes("PASSWORD MUST")) return value.charAt(0) + value.slice(1).toLowerCase() + ".";
  return value;
}

export default function SignupPage() {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ display_name: displayName, email, password }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body?.ok !== true) throw new Error(body?.detail || "SIGNUP_FAILED");
      window.location.assign("/");
    } catch (caught: any) {
      setError(friendly(caught?.message || "SIGNUP_FAILED"));
    } finally { setBusy(false); }
  }

  return <main className={styles.authShell}><section className={styles.authCard}>
    <div className={styles.brand}><div className={styles.mark}>F</div><div><b>CLEAR NASDAQ · FIA</b><span>OBSIDIAN TRADER COCKPIT</span></div></div>
    <div className={styles.kicker}>One plan · complete cockpit</div><h1 className={styles.title}>Create account</h1>
    <p className={styles.sub}>The current edition has one membership level only: Full Access. Billing is not fabricated or enabled in this local build.</p>
    <div className={styles.plan}><div><b>FULL ACCESS</b></div><span>All research modules</span></div>
    <form className={styles.form} onSubmit={submit}>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.field}><label>Name</label><input autoComplete="name" minLength={2} maxLength={64} required value={displayName} onChange={(e)=>setDisplayName(e.target.value)} /></div>
      <div className={styles.field}><label>Email</label><input type="email" autoComplete="email" required value={email} onChange={(e)=>setEmail(e.target.value)} /></div>
      <div className={styles.field}><label>Password</label><input type="password" autoComplete="new-password" minLength={10} maxLength={128} required value={password} onChange={(e)=>setPassword(e.target.value)} placeholder="10+ chars, include a letter and number" /></div>
      <button className={styles.submit} disabled={busy}>{busy ? "Creating account…" : "Create Full Access account"}</button>
    </form>
    <div className={styles.footer}>Already registered? <Link href="/login">Sign in</Link></div>
    <div className={styles.truth}>Passwords are stored as scrypt hashes in the local backend database. The session cookie is HttpOnly and SameSite=Strict.</div>
  </section></main>;
}
