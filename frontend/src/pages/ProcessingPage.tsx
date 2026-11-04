import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type OrderOut, type OrderStatus } from "../api/client";
import { PaymentStep } from "../components/PaymentStep";
import { Button, ErrorBox, Panel, Spinner } from "../components/ui";

const STEPS = ["Esperando pago", "Verificando pago", "Emitiendo factura electrónica", "Listo"] as const;

function stepIndex(s: OrderStatus): number {
  switch (s) {
    case "created":
    case "awaiting_payment":
      return 0;
    case "paid":
      return 1;
    case "invoicing":
    case "invoice_failed":
      return 2;
    case "completed":
      return 3;
    default:
      return 0;
  }
}

const TERMINAL: OrderStatus[] = ["completed", "payment_expired", "payment_failed"];

/** Backoff: 2s al inicio, crece hasta 10s mientras se espera el pago. */
function pollInterval(order: OrderOut | undefined, polls: number): number | false {
  if (!order) return 2000;
  if (TERMINAL.includes(order.status)) return false;
  if (order.status === "paid" || order.status === "invoicing") return 1500;
  if (order.status === "invoice_failed") return 15000;
  return Math.min(10000, 2000 + polls * 500);
}

export function Stepper({ current, failed }: { current: number; failed: boolean }) {
  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Progreso de la compra">
      {STEPS.map((label, i) => {
        const done = i < current || (i === current && current === STEPS.length - 1);
        const active = i === current && !done;
        return (
          <li
            key={label}
            aria-current={active ? "step" : undefined}
            className={`rounded-none border px-3 py-2 text-xs sm:text-sm ${
              done
                ? "border-ok/50 bg-ok/10 text-ok"
                : active
                  ? failed
                    ? "border-warn/60 bg-warn/10 text-warn"
                    : "border-brand bg-brand/10 text-navy"
                  : "border-line text-muted"
            }`}
          >
            <span className="mr-1 font-mono">{done ? "✓" : i + 1}</span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}

function statusMessage(o: OrderOut): string {
  switch (o.status) {
    case "awaiting_payment":
      return "Esperando la confirmación de tu pago.";
    case "paid":
      return "¡Pago confirmado! Verificando con Factus Pay…";
    case "invoicing":
      return "Emitiendo tu factura electrónica ante la DIAN…";
    case "invoice_failed":
      return "Tu pago está confirmado. La factura está pendiente y la reintentaremos automáticamente.";
    case "completed":
      return "¡Listo! Tu compra está completa.";
    case "payment_expired":
      return "El código QR venció sin recibir el pago.";
    case "payment_failed":
      return o.error ?? "El pago no se pudo completar.";
    default:
      return "Procesando…";
  }
}

export function ProcessingPage() {
  const { orderId = "" } = useParams();
  const navigate = useNavigate();
  const polls = useRef(0);
  const config = useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });
  const q = useQuery({
    queryKey: ["order", orderId],
    queryFn: ({ signal }) => {
      polls.current += 1;
      return api.order(orderId, signal); // TanStack cancela con signal al desmontar
    },
    refetchInterval: (query) => pollInterval(query.state.data, polls.current),
    staleTime: 0,
  });
  const retry = useMutation({ mutationFn: () => api.retryInvoice(orderId), onSuccess: () => void q.refetch() });
  const qc = useQueryClient();
  // Reintenta el pago de ESTA orden: misma orden, nuevo QR (o "pagada" si el cobro anterior
  // terminó pagándose). El sondeo se reanuda desde el intervalo corto.
  const retryPay = useMutation({
    mutationFn: () => api.retryPayment(orderId),
    onSuccess: (updated) => {
      polls.current = 0;
      qc.setQueryData(["order", orderId], updated);
      void qc.invalidateQueries({ queryKey: ["my-orders"] });
    },
  });

  useEffect(() => {
    if (q.data?.status === "completed") {
      const t = setTimeout(() => navigate(`/ordenes/${orderId}/listo`, { replace: true }), 1200);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [q.data?.status, navigate, orderId]);

  if (q.isPending) return <Spinner label="Cargando tu orden…" />;
  if (q.isError) return <ErrorBox message={q.error.message} onRetry={() => void q.refetch()} />;
  const o = q.data;
  const failed = o.status === "invoice_failed" || o.status === "payment_failed" || o.status === "payment_expired";

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <p className="text-sm text-muted">Orden {o.reference_code}</p>
        <h1 className="text-5xl leading-[0.9] text-brand">{o.event_name}</h1>
      </div>
      <Stepper current={stepIndex(o.status)} failed={failed} />
      <p aria-live="polite" role="status" className={failed ? "text-warn" : "text-navy"}>
        {statusMessage(o)}
      </p>

      {o.status === "awaiting_payment" && (
        <Panel>
          <PaymentStep order={o} fakePayments={config.data?.fake_payments ?? false} onChanged={() => void q.refetch()} />
        </Panel>
      )}

      {(o.status === "paid" || o.status === "invoicing") && <Spinner label="Esto toma unos segundos" />}

      {o.status === "invoice_failed" && o.error && (
        <p className="rounded-none bg-warn/10 px-3 py-2 text-xs text-warn">
          <strong>Motivo: </strong>
          {o.error}
        </p>
      )}

      {o.status === "invoice_failed" && (
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => retry.mutate()} disabled={retry.isPending}>
            Reintentar factura ahora
          </Button>
          <Link to={`/ordenes/${o.id}/listo`} className="self-center underline">
            Ver mi boleto
          </Link>
        </div>
      )}

      {(o.status === "payment_expired" || o.status === "payment_failed") && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => retryPay.mutate()} disabled={retryPay.isPending}>
              {retryPay.isPending ? <Spinner label="Generando nuevo QR…" /> : "Reintentar pago"}
            </Button>
            <Link to="/" className="self-center text-brand-mid underline">
              Buscar otros eventos
            </Link>
          </div>
          <p className="text-xs text-muted">
            Se genera un nuevo QR para esta misma orden; no se crea una compra nueva.
          </p>
          {retryPay.isError && <ErrorBox message={retryPay.error.message} />}
        </div>
      )}
    </div>
  );
}
