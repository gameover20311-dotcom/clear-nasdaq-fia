import { NextResponse } from "next/server";

export const BACKEND = process.env.FIA_BACKEND_URL || "http://127.0.0.1:8001";
export const SESSION_COOKIE = "fia_session";
export const SESSION_MAX_AGE = 7 * 24 * 60 * 60;

export function setSessionCookie(response: NextResponse, token: string, maxAge = SESSION_MAX_AGE) {
  response.cookies.set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.FIA_COOKIE_SECURE === "1",
    path: "/",
    maxAge: Math.max(60, Math.min(maxAge, SESSION_MAX_AGE)),
  });
}

export function clearSessionCookie(response: NextResponse) {
  response.cookies.set({
    name: SESSION_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.FIA_COOKIE_SECURE === "1",
    path: "/",
    maxAge: 0,
  });
}

export async function parseBackendResponse(response: Response) {
  const body = await response.json().catch(() => ({}));
  return { body, ok: response.ok };
}
