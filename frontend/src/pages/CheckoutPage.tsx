import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { ApiError, api, type ConfigOut, type TierCode } from "../api/client";
import { Button, Disclaimer, ErrorBox, Panel, Spinner } from "../components/ui";
import { useMe } from "../lib/auth";
import { formatMoney, newIdempotencyKey } from "../lib/format";

function buildSchema(config: ConfigOut) {
  const types = new Map(config.document_types.map((d) => [d.code, d]));
  return z
    .object({
      doc_type: z.string().min(1, "Selecciona el tipo de documento"),
      doc_number: z.string().trim().min(3, "Ingresa el número de documento"),
      names: z.string().trim().min(3, "Ingresa nombres y apellidos"),
      email: z.string().trim().email("Correo inválido"),
      address: z.string().trim().max(300).optional(),
      country: z.string().optional(),
      municipality: z.string().optional(),
      data_consent: z.literal(true, {
        errorMap: () => ({ message: "Debes autorizar el tratamiento de datos para continuar" }),
      }),
    })
    .superRefine((v, ctx) => {
      if (v.country === "CO" && !v.municipality) {
        ctx.addIssue({
          code: "custom",
          path: ["municipality"],
          message: "Selecciona tu municipio (obligatorio para Colombia)",
        });
      }
      const t = types.get(v.doc_type);
      if (t && !new RegExp(t.pattern).test(v.doc_number)) {
        ctx.addIssue({
          code: "custom",
          path: ["doc_number"],
          message:
            t.code === "41"
              ? "El pasaporte debe ser alfanumérico (5 a 20 caracteres)"
              : `${t.label}: solo números`,
        });
      }
    });
}
type FormValues = z.infer<ReturnType<typeof buildSchema>>;

const COUNTRIES = [
  ["", "Prefiero no indicarlo"],
  ["CO", "Colombia"],
  ["US", "Estados Unidos"],
  ["MX", "México"],
  ["ES", "España"],
  ["AR", "Argentina"],
  ["BR", "Brasil"],
  ["CL", "Chile"],
  ["PE", "Perú"],
  ["EC", "Ecuador"],
  ["CA", "Canadá"],
  ["GB", "Reino Unido"],
  ["FR", "Francia"],
  ["DE", "Alemania"],
  ["IT", "Italia"],
  ["JP", "Japón"],
] as const;

const field =
  "w-full rounded-none border border-line bg-ink px-4 py-3 text-sm focus:border-brand focus:outline-none aria-[invalid=true]:border-bad";

export function CheckoutPage() {
  const { eventId = "" } = useParams();
  const [sp] = useSearchParams();
  const qty = Math.min(10, Math.max(1, Number(sp.get("qty")) || 1));
  const tierParam = sp.get("tier");
  const tier: TierCode =
    tierParam === "preferencial" || tierParam === "vip" ? tierParam : "general";
  const config = useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });
  const quote = useQuery({
    queryKey: ["quote", eventId, qty, tier],
    queryFn: () => api.quote(eventId, qty, tier),
    retry: false,
  });

  if (config.isPending || quote.isPending) return <Spinner label="Preparando tu compra…" />;
  if (config.isError) return <ErrorBox message={config.error.message} onRetry={() => void config.refetch()} />;
  if (quote.isError)
    return (
      <div className="flex flex-col gap-3">
        <ErrorBox message={quote.error.message} />
        <Link to={`/eventos/${encodeURIComponent(eventId)}`} className="underline">
          Volver al evento
        </Link>
      </div>
    );

  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <CheckoutForm config={config.data} eventId={eventId} qty={qty} tier={tier} />
      <Panel className="flex h-fit flex-col gap-3">
        <h2 className="text-3xl text-brand">Resumen</h2>
        <p className="text-sm text-muted">
          {qty} × {quote.data.tier_label} · {formatMoney(quote.data.unit_price_cop, "COP")}
        </p>
        <p className="flex items-baseline justify-between border-t border-line pt-3">
          <span>Total en COP</span>
          <strong className="text-2xl">{formatMoney(quote.data.total_cop, "COP")}</strong>
        </p>
        <ul className="text-xs text-muted">
          {(["USD", "EUR", "GBP", "JPY"] as const).map((c) => (
            <li key={c}>≈ {formatMoney(quote.data.references[c], c)} (referencia)</li>
          ))}
        </ul>
        <Disclaimer compact text={config.data.disclaimer} />
      </Panel>
    </div>
  );
}

function CheckoutForm({
  config,
  eventId,
  qty,
  tier,
}: {
  config: ConfigOut;
  eventId: string;
  qty: number;
  tier: TierCode;
}) {
  const { user } = useMe();
  const navigate = useNavigate();
  const idemKey = useRef(newIdempotencyKey());
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(buildSchema(config)),
    defaultValues: {
      doc_type: config.document_types[0]?.code ?? "13",
      names: user?.name ?? "",
      email: user?.email ?? "",
    },
  });

  const create = useMutation({
    mutationFn: (v: FormValues) =>
      api.createOrder(
        {
          event_id: eventId,
          quantity: qty,
          tier,
          data_consent: true,
          customer: {
            doc_type: v.doc_type,
            doc_number: v.doc_number.trim(),
            names: v.names.trim(),
            email: v.email.trim(),
            address: v.address || null,
            country: v.country || null,
            municipality: v.country === "CO" ? v.municipality || null : null,
          },
        },
        idemKey.current,
      ),
    onSuccess: (order) => navigate(`/ordenes/${order.id}`),
    onError: (e) => {
      // Un error de validación no creó nada: el siguiente intento usa una llave nueva.
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) idemKey.current = newIdempotencyKey();
    },
  });

  const isColombia = watch("country") === "CO";

  const err = (name: keyof FormValues) =>
    errors[name] ? (
      <p id={`${name}-error`} className="mt-1 text-xs text-bad">
        {errors[name]?.message}
      </p>
    ) : null;
  const aria = (name: keyof FormValues) => ({
    "aria-invalid": errors[name] ? true : undefined,
    "aria-describedby": errors[name] ? `${name}-error` : undefined,
  });

  return (
    <Panel>
      <form
        noValidate
        onSubmit={handleSubmit((v) => {
          if (!create.isPending) create.mutate(v);
        })}
        className="flex flex-col gap-4"
      >
        <h1 className="text-5xl leading-none text-brand">Datos para la factura electrónica</h1>
        <div className="grid gap-4 sm:grid-cols-[1fr_1.4fr]">
          <label className="text-sm">
            <span className="mb-1 block text-muted">Tipo de documento *</span>
            <select className={field} {...register("doc_type")} {...aria("doc_type")}>
              {config.document_types.map((d) => (
                <option key={d.code} value={d.code}>
                  {d.label}
                </option>
              ))}
            </select>
            {err("doc_type")}
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted">Número de documento *</span>
            <input className={field} autoComplete="off" {...register("doc_number")} {...aria("doc_number")} />
            {err("doc_number")}
          </label>
        </div>
        <label className="text-sm">
          <span className="mb-1 block text-muted">Nombres y apellidos *</span>
          <input className={field} autoComplete="name" {...register("names")} {...aria("names")} />
          {err("names")}
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted">Correo electrónico *</span>
          <input className={field} type="email" autoComplete="email" {...register("email")} {...aria("email")} />
          {err("email")}
        </label>
        <div className="grid gap-4 sm:grid-cols-[1.6fr_1fr]">
          <label className="text-sm">
            <span className="mb-1 block text-muted">Dirección (opcional)</span>
            <input className={field} autoComplete="street-address" {...register("address")} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted">País (opcional)</span>
            <select className={field} {...register("country")} {...aria("country")}>
              {COUNTRIES.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
            {err("country")}
          </label>
        </div>
        {isColombia && (
          <label className="text-sm">
            <span className="mb-1 block text-muted">Municipio *</span>
            <select className={field} {...register("municipality")} {...aria("municipality")}>
              <option value="">Selecciona tu municipio</option>
              {config.municipalities.map((m) => (
                <option key={m.code} value={m.code}>
                  {m.name}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-xs text-muted">
              La DIAN lo exige en la factura de clientes en Colombia.
            </span>
            {err("municipality")}
          </label>
        )}

        <div className="rounded-none border border-line p-4 text-xs text-muted">
          <p>
            Usaremos tu tipo y número de documento, nombre y correo únicamente para emitir la factura
            electrónica ante la DIAN y enviarte la confirmación de compra. No guardamos datos de pago.
            {/* PENDIENTE: el texto legal definitivo debe validarlo el equipo responsable. */}
          </p>
          <label className="mt-3 flex items-start gap-3 text-sm text-navy">
            <input type="checkbox" className="mt-1 size-4 accent-brand" {...register("data_consent")} {...aria("data_consent")} />
            <span>Autorizo el tratamiento de mis datos personales para fines de facturación. *</span>
          </label>
          {err("data_consent")}
        </div>

        {create.isError && <ErrorBox message={create.error.message} />}
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? <Spinner label="Creando tu orden…" /> : "Continuar al pago"}
        </Button>
      </form>
    </Panel>
  );
}
