import type { components } from "./schema";

type S = components["schemas"];
export type EventOut = S["EventOut"];
export type QuoteOut = S["QuoteOut"];
export type OrderIn = S["OrderIn"];
export type OrderOut = S["OrderOut"];
export type OrderStatus = OrderOut["status"];
export type ConfigOut = S["ConfigOut"];
export type CustomerIn = S["CustomerIn"];
export type UserOut = S["UserOut"];
export type TicketOut = S["TicketOut"];
export type TierCode = S["TierOut"]["code"];

/** Se emite cuando la API responde 401 (sesión vencida): la app vuelve al login. */
export const UNAUTHORIZED_EVENT = "tm:unauthorized";

// Producción (Render): la API se sirve en la misma URL que la página, así que la base es "".
// Desarrollo: Vite corre en :5173 y la API en :8000. VITE_API_BASE_URL permite forzar otra.
export const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length > 0) {
      const first = d[0] as { msg?: string };
      return (first.msg ?? "Datos inválidos").replace(/^Value error, /, "");
    }
  }
  return status >= 500 ? "El servicio no está disponible. Intenta de nuevo." : `Error ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, {
      ...init,
      credentials: "include", // cookie de sesión httpOnly
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "No hay conexión con el servidor.");
  }
  const body: unknown = await res.json().catch(() => null);
  if (res.status === 401 && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) throw new ApiError(res.status, detailMessage(body, res.status));
  return body as T;
}

export const api = {
  me: () => request<UserOut>("/auth/me"),
  login: (email: string, password: string) =>
    request<UserOut>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (name: string, email: string, password: string) =>
    request<UserOut>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }),
  logout: () => request<null>("/auth/logout", { method: "POST" }),
  myOrders: () => request<OrderOut[]>("/orders"),
  config: () => request<ConfigOut>("/config"),
  searchEvents: (params: { artist?: string; city?: string; country?: string }, signal?: AbortSignal) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
    return request<S["EventSearchOut"]>(`/events?${q.toString()}`, { signal });
  },
  event: (id: string, signal?: AbortSignal) =>
    request<EventOut>(`/events/${encodeURIComponent(id)}`, { signal }),
  quote: (event_id: string, quantity: number, tier: TierCode = "general") =>
    request<QuoteOut>("/quotes", {
      method: "POST",
      body: JSON.stringify({ event_id, quantity, tier }),
    }),
  createOrder: (body: OrderIn, idempotencyKey: string) =>
    request<OrderOut>("/orders", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  order: (id: string, signal?: AbortSignal) =>
    request<OrderOut>(`/orders/${encodeURIComponent(id)}`, { signal }),
  retryPayment: (id: string) =>
    request<OrderOut>(`/orders/${encodeURIComponent(id)}/retry-payment`, { method: "POST" }),
  retryInvoice: (id: string) =>
    request<OrderOut>(`/orders/${encodeURIComponent(id)}/retry-invoice`, { method: "POST" }),
  simulatePayment: (id: string, ok: boolean) =>
    request<unknown>(`/dev/orders/${encodeURIComponent(id)}/simulate-payment?ok=${ok}`, {
      method: "POST",
    }),
};

/** Descarga un archivo como blob (la autenticación con Factus queda en el servidor). */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, { credentials: "include" });
  } catch {
    throw new ApiError(0, "No hay conexión con el servidor.");
  }
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    throw new ApiError(res.status, detailMessage(body, res.status));
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="?([^";]+)"?/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
