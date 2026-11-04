import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { EventImage } from "../components/EventCard";
import { Button, ErrorBox, Panel, Spinner } from "../components/ui";
import { CURRENCIES, formatDateTime, formatEventDate, formatMoney } from "../lib/format";
import { useCurrency } from "../lib/hooks";

export function EventPage() {
  const { eventId = "" } = useParams();
  const navigate = useNavigate();
  const { currency } = useCurrency();
  const [qty, setQty] = useState(1);
  const [tierCode, setTierCode] = useState("general");
  const q = useQuery({ queryKey: ["event", eventId], queryFn: ({ signal }) => api.event(eventId, signal) });

  if (q.isPending) return <Spinner label="Cargando evento…" />;
  if (q.isError) return <ErrorBox message={q.error.message} onRetry={() => void q.refetch()} />;
  const ev = q.data;
  const tier = ev.tiers.find((t) => t.code === tierCode) ?? ev.tiers[0];
  if (!tier) return <ErrorBox message="Este concierto no tiene localidades disponibles." />;
  const totalCop = String(Number(tier.unit_price_cop) * qty);

  return (
    <article className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
      <div className="flex flex-col gap-5">
        <Link to="/" className="eyebrow text-muted hover:text-brand">
          ← Volver a conciertos
        </Link>
        <EventImage src={ev.image_url} alt={ev.name} className="aspect-[16/9] w-full" />
        <div>
          <p className="eyebrow text-brand-mid">{formatEventDate(ev.date)}</p>
          <h1 className="mt-2 text-5xl leading-[0.9] text-brand sm:text-7xl">{ev.name}</h1>
          {ev.artist && <p className="mt-2 text-lg font-light text-muted">{ev.artist}</p>}
        </div>
        <dl className="grid grid-cols-2 border-t border-line text-sm sm:grid-cols-4">
          {[
            ["Recinto", ev.venue],
            ["Ciudad", ev.city],
            ["País", ev.country],
            ["ID del evento", ev.id],
          ].map(([k, v]) => (
            <div key={k} className="border-b border-line py-3 pr-3">
              <dt className="eyebrow text-muted">{k}</dt>
              <dd className="mt-1 break-words">{v ?? "—"}</dd>
            </div>
          ))}
        </dl>
      </div>

      <Panel className="flex h-fit flex-col gap-5 lg:sticky lg:top-24">
        <h2 className="text-4xl text-brand">Elige tu localidad</h2>

        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">Localidad</legend>
          {ev.tiers.map((t) => {
            const selected = t.code === tier.code;
            return (
              <label
                key={t.code}
                className={`flex cursor-pointer items-center justify-between gap-3 border px-4 py-3 transition ${
                  selected ? "border-brand bg-ink" : "border-line hover:border-brand-mid"
                }`}
              >
                <span className="flex items-center gap-3">
                  <input
                    type="radio"
                    name="tier"
                    value={t.code}
                    checked={selected}
                    onChange={() => setTierCode(t.code)}
                    className="size-4 accent-brand"
                  />
                  <span className="font-medium uppercase tracking-wide">{t.label}</span>
                </span>
                <span className="text-right">
                  <span className="block font-medium">{formatMoney(t.display_prices[currency], currency)}</span>
                  {currency !== "COP" && (
                    <span className="block text-xs text-muted">{formatMoney(t.unit_price_cop, "COP")}</span>
                  )}
                </span>
              </label>
            );
          })}
        </fieldset>

        <p className="text-xs text-muted">
          {ev.is_demo_price
            ? "Precio de demostración (catálogo propio): Ticketmaster no publica precio para este concierto."
            : `Precio General basado en el valor publicado por Ticketmaster${
                ev.original_price && ev.original_currency
                  ? ` (desde ${formatMoney(ev.original_price, ev.original_currency)})`
                  : ""
              }.`}
        </p>

        <details className="text-sm">
          <summary className="eyebrow cursor-pointer text-muted">
            Equivalencias de {tier.label}
          </summary>
          <table className="mt-2 w-full">
            <caption className="sr-only">Equivalencias referenciales</caption>
            <tbody>
              {CURRENCIES.map((c) => (
                <tr key={c} className={c === currency ? "text-navy" : "text-muted"}>
                  <th scope="row" className="py-1 text-left font-medium">
                    {c}
                  </th>
                  <td className="py-1 text-right tabular-nums">{formatMoney(tier.display_prices[c], c)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>

        <label className="flex items-center justify-between gap-3 text-sm">
          <span className="eyebrow text-muted">Cantidad</span>
          <select
            value={qty}
            onChange={(e) => setQty(Number(e.target.value))}
            className="border border-line bg-ink px-3 py-2"
          >
            {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <div className="flex items-baseline justify-between border-t border-line pt-4">
          <span className="text-muted">
            Total · {qty} × {tier.label}
          </span>
          <strong className="text-2xl font-medium">{formatMoney(totalCop, "COP")}</strong>
        </div>
        <p className="bg-pastel px-3 py-2 text-xs text-brand-mid">
          El cobro y la factura son siempre en pesos colombianos (COP). Tasas de referencia
          actualizadas el {formatDateTime(ev.rates.updated_at)}.
        </p>
        <Button
          onClick={() =>
            navigate(`/checkout/${encodeURIComponent(ev.id)}?qty=${qty}&tier=${encodeURIComponent(tier.code)}`)
          }
        >
          Comprar boletos
        </Button>
      </Panel>
    </article>
  );
}
