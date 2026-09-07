"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import styles from "../auth.module.css";

function friendly(detail: string) {
  const value = String(detail || "LOGIN_FAILED").replace(/_/g, " ");
  if (value.includes("INVALID CREDENTIALS")) return "Email or password is incorrect.";
  if (value.includes("TEMPORARILY LOCKED")) return "Too many failed attempts. Try again in about 10 minutes.";
  return value;
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok || body?.ok !== true) throw new Error(body?.detail || "LOGIN_FAILED");
      window.location.assign("/");
    } catch (caught: any) {
      setError(friendly(caught?.message || "LOGIN_FAILED"));
    } finally { setBusy(false); }
  }

  return <main className={styles.authShell}><section className={styles.authCard}>
    <div className={styles.brand}><div className={styles.mark}>F</div><div><b>CLEAR NASDAQ · FIA</b><span>OBSIDIAN TRADER COCKPIT</span></div></div>
    <div className={styles.kicker}>Member access</div><h1 className={styles.title}>Welcome back</h1>
    <p className={styles.sub}>Sign in to the live research cockpit. Data remains fail-closed when the FIA truth gate is not ready.</p>
    <div className={styles.plan}><div><b>FULL ACCESS</b></div><span>Single membership tier</span></div>
    <form className={styles.form} onSubmit={submit}>
      {error && <div className={styles.error}>{error}</div>}
      <div className={styles.field}><label>Email</label><input type="email" autoComplete="email" required value={email} onChange={(e)=>setEmail(e.target.value)} /></div>
      <div className={styles.field}><label>Password</label><input type="password" autoComplete="current-password" required value={password} onChange={(e)=>setPassword(e.target.value)} /></div>
      <button className={styles.submit} disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
    <div className={styles.footer}>New member? <Link href="/signup">Create Full Access account</Link></div>
    <div className={styles.truth}>Research software only. No broker execution controls are enabled.</div>
  </section></main>;
}
