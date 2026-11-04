import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type OrderOut, type OrderStatus } from "../api/client";
import { ErrorBox, Spinner } from "../components/ui";
import { formatDateTime, formatMoney } from "../lib/format";

const LABEL: Record<OrderStatus, [string, string]> = {
  created: ["Creada", "bg-pastel text-brand"],
  awaiting_payment: ["Esperando pago", "bg-pastel text-brand"],
  paid: ["Pagada", "bg-ok/10 text-ok"],
  invoicing: ["Emitiendo factura", "bg-pastel text-brand"],
  completed: ["Completada", "bg-ok/10 text-ok"],
  payment_expired: ["QR vencido", "bg-line text-muted"],
  payment_failed: ["Pago fallido", "bg-bad/10 text-bad"],
  invoice_failed: ["Factura pendiente", "bg-warn/10 text-warn"],
};

function target(o: OrderOut): string {
  return ["completed", "invoicing", "invoice_failed", "paid"].includes(o.status)
    ? `/ordenes/${o.id}/listo`
    : `/ordenes/${o.id}`;
}

export function MyOrdersPage() {
  const q = useQuery({ queryKey: ["my-orders"], queryFn: api.myOrders, staleTime: 0 });
  if (q.isPending) return <Spinner label="Cargando tus compras…" />;
  if (q.isError) return <ErrorBox message={q.error.message} onRetry={() => void q.refetch()} />;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <h1 className="text-6xl leading-none text-brand">Mis compras</h1>
      {q.data.length === 0 ? (
        <div className="rounded-none border border-dashed border-line p-10 text-center text-muted">
          <p className="font-semibold text-navy">Aún no tienes compras</p>
          <Link to="/" className="mt-2 inline-block text-brand-mid underline">
            Buscar eventos
          </Link>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {q.data.map((o) => {
            const [label, cls] = LABEL[o.status];
            return (
              <li key={o.id}>
                <Link
                  to={target(o)}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-none border border-line bg-panel p-4 transition hover:border-brand-mid"
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{o.event_name}</p>
                    <p className="text-xs text-muted">
                      {o.reference_code} · {o.quantity} boleto{o.quantity > 1 ? "s" : ""} {o.ticket_tier} ·{" "}
                      {formatDateTime(o.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-semibold">{formatMoney(o.total_cop, "COP")}</span>
                    <span className={`rounded-none px-3 py-1 text-xs font-semibold ${cls}`}>{label}</span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
