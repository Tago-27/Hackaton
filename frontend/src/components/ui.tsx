import type { ReactNode } from "react";
import { CURRENCIES, type Currency } from "../lib/format";
import { useCurrency } from "../lib/hooks";

export function Disclaimer({ text, compact = false }: { text?: string; compact?: boolean }) {
  return (
    <p
      role="note"
      className={`rounded-none border border-bad/40 bg-bad/10 text-bad ${compact ? "px-3 py-2 text-xs" : "px-4 py-3 text-sm"}`}
    >
      <strong className="font-semibold">Aviso: </strong>
      {text ??
        "este boleto digital es de demostración y NO es un boleto oficial de Ticketmaster ni de ningún organizador."}
    </p>
  );
}

export function CurrencySelector() {
  const { currency, setCurrency } = useCurrency();
  return (
    <fieldset className="flex flex-wrap items-center gap-1" aria-label="Moneda de referencia">
      <legend className="sr-only">Moneda de referencia</legend>
      {CURRENCIES.map((c: Currency) => (
        <button
          key={c}
          type="button"
          aria-pressed={currency === c}
          onClick={() => setCurrency(c)}
          className={`rounded-none px-3 py-1 text-xs font-semibold transition ${
            currency === c
              ? "bg-brand text-white"
              : "border border-line text-muted hover:border-brand hover:text-brand"
          }`}
        >
          {c}
        </button>
      ))}
    </fieldset>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-none px-6 py-3 text-xs font-medium uppercase tracking-[0.18em] transition disabled:cursor-not-allowed disabled:opacity-50";
  const styles =
    variant === "primary"
      ? "border border-brand bg-brand text-white hover:border-brand-mid hover:bg-brand-mid"
      : "border border-brand text-brand hover:bg-brand hover:text-white";
  return (
    <button className={`${base} ${styles} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-none border border-bad/40 bg-bad/10 p-4 text-sm text-bad">
      <p>{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 font-semibold underline">
          Reintentar
        </button>
      )}
    </div>
  );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-none border border-line bg-panel p-5 sm:p-6 ${className}`}>
      {children}
    </section>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2" role="status">
      <span className="size-4 animate-spin rounded-full border-2 border-muted border-t-brand" />
      <span>{label}</span>
    </span>
  );
}
