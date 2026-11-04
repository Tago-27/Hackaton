export const CURRENCIES = ["COP", "USD", "EUR", "GBP", "JPY"] as const;
export type Currency = (typeof CURRENCIES)[number];

const ZERO_DECIMALS = new Set<string>(["COP", "JPY"]);

/** Solo para mostrar: el backend calcula todo con Decimal y envía montos como texto. */
export function formatMoney(amount: string | null | undefined, currency: string): string {
  if (amount == null) return "—";
  const digits = ZERO_DECIMALS.has(currency) ? 0 : 2;
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(amount));
}

export function formatEventDate(iso: string | null | undefined): string {
  if (!iso) return "Fecha por confirmar";
  const hasTime = iso.includes("T");
  const d = new Date(hasTime ? iso : `${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-CO", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    ...(hasTime ? { hour: "numeric", minute: "2-digit" } : {}),
  }).format(d);
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(iso),
  );
}

/** Algoritmo de Luhn para validar números de tarjeta (solo modo demo, nunca se envían). */
export function luhnValid(value: string): boolean {
  const digits = value.replace(/\D/g, "");
  if (digits.length < 12 || digits.length > 19) return false;
  let sum = 0;
  let double = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let n = Number(digits[i]);
    if (double) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    sum += n;
    double = !double;
  }
  return sum % 10 === 0;
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/** Partes de la fecha para el bloque de fecha de la lista de conciertos. */
export function eventDateParts(iso: string | null | undefined): {
  day: string;
  month: string;
  short: string;
  detail: string;
} | null {
  if (!iso) return null;
  const hasTime = iso.includes("T");
  const d = new Date(hasTime ? iso : `${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  const fmt = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("es-CO", o).format(d);
  return {
    day: fmt({ day: "2-digit" }),
    month: fmt({ month: "short" }).replace(".", ""),
    // "jue, 26 jul" (como "Thu, Jul 26" en la plantilla)
    short: fmt({ weekday: "short", day: "numeric", month: "short" }).replace(/\./g, ""),
    // "miércoles, 4 de noviembre de 2026 · 1:00 p. m."
    detail: [
      fmt({ weekday: "long", day: "numeric", month: "long", year: "numeric" }),
      hasTime ? fmt({ hour: "numeric", minute: "2-digit" }) : "",
    ]
      .filter(Boolean)
      .join(" · "),
  };
}
