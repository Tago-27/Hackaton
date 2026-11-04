import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type OrderOut } from "../api/client";
import { formatMoney, luhnValid } from "../lib/format";
import { useNow } from "../lib/hooks";
import { Button, ErrorBox } from "./ui";

const MODE = import.meta.env.VITE_PAYMENT_MODE === "card" ? "card" : "qr";

/** Paso de pago intercambiable: VITE_PAYMENT_MODE=qr|card. */
export function PaymentStep({ order, fakePayments, onChanged }: {
  order: OrderOut;
  fakePayments: boolean;
  onChanged: () => void;
}) {
  return MODE === "card" ? (
    <CardPayment order={order} fakePayments={fakePayments} onChanged={onChanged} />
  ) : (
    <QrPayment order={order} fakePayments={fakePayments} onChanged={onChanged} />
  );
}

function Countdown({ expiresAt }: { expiresAt: string | null }) {
  const now = useNow();
  if (!expiresAt) return null;
  const left = Math.max(0, Math.floor((new Date(expiresAt).getTime() - now) / 1000));
  const mm = String(Math.floor(left / 60)).padStart(2, "0");
  const ss = String(left % 60).padStart(2, "0");
  return (
    <p className={`text-sm ${left < 60 ? "text-warn" : "text-muted"}`}>
      {left > 0 ? (
        <>
          El QR vence en <span className="font-mono tabular-nums">{mm}:{ss}</span>
        </>
      ) : (
        "El QR venció. Verificando estado…"
      )}
    </p>
  );
}

function DemoSimulator({ orderId, onChanged }: { orderId: string; onChanged: () => void }) {
  const sim = useMutation({
    mutationFn: (ok: boolean) => api.simulatePayment(orderId, ok),
    onSuccess: onChanged,
  });
  return (
    <div className="rounded-none border border-dashed border-brand-mid/50 p-3 text-xs">
      <p className="mb-2 text-brand-mid">Modo demo (pagos simulados, sin dinero real)</p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" className="!px-3 !py-2" onClick={() => sim.mutate(true)} disabled={sim.isPending}>
          Simular pago exitoso
        </Button>
        <Button type="button" variant="ghost" className="!px-3 !py-2" onClick={() => sim.mutate(false)} disabled={sim.isPending}>
          Simular pago fallido
        </Button>
      </div>
    </div>
  );
}

function QrPayment({ order, fakePayments, onChanged }: { order: OrderOut; fakePayments: boolean; onChanged: () => void }) {
  const [copied, setCopied] = useState(false);
  const { qr, breb_key, expires_at } = order.payment;
  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <p className="text-sm text-muted">
        Escanea el QR desde la app de tu banco (Bre-B) y paga{" "}
        <strong className="text-navy">{formatMoney(order.total_cop, "COP")}</strong>
      </p>
      {qr ? (
        <img
          src={qr}
          alt={`Código QR para pagar ${formatMoney(order.total_cop, "COP")} con Bre-B`}
          className="size-56 rounded-none bg-white p-2 [image-rendering:pixelated]"
        />
      ) : (
        <div className="flex size-56 items-center justify-center rounded-none border border-line text-muted">QR no disponible</div>
      )}
      {breb_key && (
        <div className="flex flex-wrap items-center justify-center gap-2 text-sm">
          <span className="text-muted">Llave Bre-B:</span>
          <code className="rounded bg-ink px-2 py-1">{breb_key}</code>
          <button
            type="button"
            className="text-brand underline"
            onClick={() => {
              void navigator.clipboard?.writeText(breb_key).then(() => setCopied(true));
            }}
          >
            {copied ? "¡Copiada!" : "Copiar"}
          </button>
        </div>
      )}
      <Countdown expiresAt={expires_at} />
      {fakePayments && <DemoSimulator orderId={order.id} onChanged={onChanged} />}
    </div>
  );
}

function CardPayment({ order, fakePayments, onChanged }: { order: OrderOut; fakePayments: boolean; onChanged: () => void }) {
  // Los datos de tarjeta viven solo en este componente: nunca se registran, guardan ni envían.
  const [number, setNumber] = useState("");
  const [exp, setExp] = useState("");
  const [cvc, setCvc] = useState("");
  const [error, setError] = useState<string | null>(null);
  const sim = useMutation({ mutationFn: () => api.simulatePayment(order.id, true), onSuccess: onChanged });

  const validate = (): string | null => {
    if (!luhnValid(number)) return "Número de tarjeta inválido";
    const m = /^(\d{2})\/(\d{2})$/.exec(exp);
    if (!m) return "Vencimiento con formato MM/AA";
    const month = Number(m[1]);
    const year = 2000 + Number(m[2]);
    const now = new Date();
    if (month < 1 || month > 12 || year < now.getFullYear() || (year === now.getFullYear() && month < now.getMonth() + 1))
      return "La tarjeta está vencida";
    if (!/^\d{3,4}$/.test(cvc)) return "CVC inválido";
    return null;
  };

  const f = "w-full rounded-none border border-line bg-ink px-4 py-3 text-sm";
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const v = validate();
        setError(v);
        if (!v && fakePayments) sim.mutate();
      }}
    >
      <p role="note" className="rounded-none bg-warn/10 px-3 py-2 text-xs text-warn">
        TODO: el cobro real con tarjeta requiere un proveedor con tokenización compatible con PCI.
        Factus Pay no cubre este flujo; este formulario es solo de demostración.
      </p>
      <label className="text-sm">
        <span className="mb-1 block text-muted">Número de tarjeta</span>
        <input className={f} inputMode="numeric" autoComplete="cc-number" value={number} onChange={(e) => setNumber(e.target.value)} />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-muted">Vence (MM/AA)</span>
          <input className={f} autoComplete="cc-exp" value={exp} onChange={(e) => setExp(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted">CVC</span>
          <input className={f} inputMode="numeric" autoComplete="cc-csc" value={cvc} onChange={(e) => setCvc(e.target.value)} />
        </label>
      </div>
      {error && <ErrorBox message={error} />}
      {!fakePayments && !error && sim.isIdle && (
        <p className="text-xs text-muted">Con pagos reales, usa el modo QR (VITE_PAYMENT_MODE=qr).</p>
      )}
      <Button type="submit" disabled={sim.isPending}>
        Pagar {formatMoney(order.total_cop, "COP")}
      </Button>
    </form>
  );
}
