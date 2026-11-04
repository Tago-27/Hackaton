import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, downloadFile, type OrderOut } from "../api/client";
import { Button, Disclaimer, ErrorBox, Panel, Spinner } from "../components/ui";
import { formatEventDate, formatMoney } from "../lib/format";

function InvoicePanel({ o }: { o: OrderOut }) {
  const qc = useQueryClient();
  const retry = useMutation({
    mutationFn: () => api.retryInvoice(o.id),
    onSuccess: (updated) => qc.setQueryData(["order", o.id], updated),
  });
  const dl = useMutation({
    mutationFn: ({ path, name }: { path: string; name: string }) => downloadFile(path, name),
  });

  return (
    <Panel className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-3xl text-brand">Factura electrónica</h2>
        {o.invoice.available ? (
          <span className="rounded-none bg-ok/10 px-3 py-1 text-xs font-semibold text-ok">
            Emitida · {o.invoice.number}
          </span>
        ) : o.status === "invoice_failed" ? (
          <span className="rounded-none bg-warn/10 px-3 py-1 text-xs font-semibold text-warn">
            Pendiente
          </span>
        ) : (
          <span className="rounded-none bg-pastel px-3 py-1 text-xs font-semibold text-brand">
            Emitiendo…
          </span>
        )}
      </div>

      {o.invoice.available ? (
        <div className="flex flex-wrap gap-3">
          <Button
            disabled={dl.isPending}
            onClick={() => dl.mutate({ path: `/orders/${o.id}/invoice?format=pdf`, name: "factura.pdf" })}
          >
            Descargar factura PDF
          </Button>
          <Button
            variant="ghost"
            disabled={dl.isPending}
            onClick={() => dl.mutate({ path: `/orders/${o.id}/invoice?format=xml`, name: "factura.xml" })}
          >
            Descargar XML
          </Button>
        </div>
      ) : o.status === "invoice_failed" ? (
        <div className="flex flex-col gap-3" role="status">
          <p className="text-sm text-muted">
            Tu pago está confirmado y tus boletos son válidos para la demo. La factura no se pudo
            emitir todavía; se reintenta automáticamente, o puedes reintentar ahora.
          </p>
          {o.error && (
            <p className="rounded-none bg-warn/10 px-3 py-2 text-xs text-warn">
              <strong>Motivo: </strong>
              {o.error}
            </p>
          )}
          <Button className="self-start" onClick={() => retry.mutate()} disabled={retry.isPending}>
            {retry.isPending ? <Spinner label="Reintentando…" /> : "Reintentar factura"}
          </Button>
          {retry.isError && <ErrorBox message={retry.error.message} />}
        </div>
      ) : (
        <p className="text-sm text-muted" aria-live="polite">
          Estamos emitiendo tu factura ante la DIAN; los botones aparecerán en unos segundos.
        </p>
      )}
      {dl.isError && (
        <ErrorBox message={dl.error.message} onRetry={() => dl.variables && dl.mutate(dl.variables)} />
      )}
    </Panel>
  );
}

export function ConfirmationPage() {
  const { orderId = "" } = useParams();
  const q = useQuery({
    queryKey: ["order", orderId],
    queryFn: ({ signal }) => api.order(orderId, signal),
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      if (s === "completed") return false;
      return s === "invoice_failed" ? 15000 : 4000;
    },
  });
  const dlTickets = useMutation({
    mutationFn: () => downloadFile(`/orders/${orderId}/ticket`, "boletos.pdf"),
  });

  if (q.isPending) return <Spinner label="Cargando tus boletos…" />;
  if (q.isError) return <ErrorBox message={q.error.message} onRetry={() => void q.refetch()} />;
  const o = q.data;
  const ticketReady = ["completed", "invoicing", "invoice_failed", "paid"].includes(o.status);
  if (!ticketReady) {
    return (
      <p>
        Esta orden aún no está pagada.{" "}
        <Link className="text-brand-mid underline" to={`/ordenes/${o.id}`}>
          Ver estado
        </Link>
      </p>
    );
  }
  const place = [o.event_venue, o.event_city].filter(Boolean).join(" · ");

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <p className="text-sm font-semibold text-ok">Pago confirmado</p>
        <h1 className="text-6xl leading-none text-brand">¡Tu compra está lista!</h1>
        <p className="mt-1 text-sm text-muted">
          Orden {o.reference_code} · {o.quantity} boleto{o.quantity > 1 ? "s" : ""} {o.ticket_tier} ·{" "}
          {formatMoney(o.total_cop, "COP")}
        </p>
      </div>

      <section className="flex flex-col gap-3" aria-labelledby="tickets-title">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="tickets-title" className="text-3xl text-brand">
            Tus boletos
          </h2>
          <Button variant="ghost" onClick={() => dlTickets.mutate()} disabled={dlTickets.isPending}>
            {dlTickets.isPending ? (
              <Spinner label="Generando…" />
            ) : (
              `Descargar boletos (PDF, ${o.quantity} pág.)`
            )}
          </Button>
        </div>
        {dlTickets.isError && <ErrorBox message={dlTickets.error.message} />}
        <ul className="grid gap-3 sm:grid-cols-2">
          {o.tickets.map((t) => (
            <li key={t.code}>
              <article
                aria-label={`Boleto ${t.number} de ${t.of}`}
                className="overflow-hidden rounded-none border border-pastel-strong bg-ink shadow-sm"
              >
                <div className="bg-bad px-3 py-1 text-center text-[10px] font-bold uppercase tracking-wide text-white">
                  Boleto de demostración · No oficial
                </div>
                <div className="bg-brand px-4 py-3 text-white">
                  <p className="text-xs text-brand-2">
                    Boleto {t.number} de {t.of}
                  </p>
                  <p className="line-clamp-2 font-bold">{o.event_name}</p>
                </div>
                <div className="flex flex-col gap-1 bg-pastel/60 px-4 py-3 text-sm">
                  <p>{formatEventDate(o.event_date)}</p>
                  {place && <p className="text-muted">{place}</p>}
                  <p className="text-muted">Localidad: {o.ticket_tier}</p>
                  <p className="text-muted">Titular: {o.customer_names}</p>
                  <p className="mt-2 rounded-none border border-dashed border-brand-2 bg-ink px-2 py-1 text-center font-mono text-sm font-bold tracking-wider text-brand">
                    {t.code}
                  </p>
                </div>
              </article>
            </li>
          ))}
        </ul>
      </section>

      <InvoicePanel o={o} />
      <Disclaimer text={o.disclaimer} />

      <div className="flex flex-wrap gap-4 text-sm">
        <Link to="/mis-compras" className="text-brand-mid underline">
          Ver mis compras
        </Link>
        <Link to="/" className="text-brand-mid underline">
          Buscar más eventos
        </Link>
      </div>
    </div>
  );
}
