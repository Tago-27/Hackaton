import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { api } from "../api/client";
import { Button, ErrorBox, Spinner } from "../components/ui";
import { useMe, useSetMe } from "../lib/auth";

const loginSchema = z.object({
  email: z.string().trim().email("Correo inválido"),
  password: z.string().min(1, "Ingresa tu contraseña"),
});
const registerSchema = z.object({
  name: z.string().trim().min(3, "Ingresa tu nombre completo"),
  email: z.string().trim().email("Correo inválido"),
  password: z.string().min(8, "Mínimo 8 caracteres"),
});
type Values = { name?: string; email: string; password: string };

const field =
  "w-full rounded-none border border-line bg-ink px-4 py-3 text-sm focus:border-brand-mid focus:outline-none aria-[invalid=true]:border-bad";

/** Solo rutas internas: evita redirecciones abiertas a otros sitios. */
function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const [sp] = useSearchParams();
  const next = safeNext(sp.get("next"));
  const navigate = useNavigate();
  const setMe = useSetMe();
  const { user, loading } = useMe();
  const isLogin = mode === "login";

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Values>({ resolver: zodResolver(isLogin ? loginSchema : registerSchema) });

  const submit = useMutation({
    mutationFn: (v: Values) =>
      isLogin ? api.login(v.email, v.password) : api.register(v.name ?? "", v.email, v.password),
    onSuccess: (u) => {
      setMe(u);
      navigate(next, { replace: true });
    },
  });

  if (loading) return <Spinner label="Cargando…" />;
  if (user) return <Navigate to={next} replace />;

  const err = (name: keyof Values) =>
    errors[name] ? (
      <p id={`${name}-error`} className="mt-1 text-xs text-bad">
        {errors[name]?.message}
      </p>
    ) : null;
  const aria = (name: keyof Values) => ({
    "aria-invalid": errors[name] ? true : undefined,
    "aria-describedby": errors[name] ? `${name}-error` : undefined,
  });
  const other = `${isLogin ? "/registro" : "/ingresar"}${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`;

  return (
    <div className="mx-auto grid max-w-4xl overflow-hidden rounded-none border border-line bg-ink shadow-sm md:grid-cols-2">
      <section className="flex flex-col justify-between gap-6 bg-brand p-8 text-white">
        <div>
          <p className="text-3xl" aria-hidden="true">
            ♫
          </p>
          <h1 className="mt-3 text-6xl leading-[0.9]">
            Viaja por la música.
            <br />
            <span className="text-brand-2">Paga en pesos.</span>
          </h1>
          <p className="mt-3 text-sm text-pastel">
            Conciertos en todo el mundo, precios en cinco monedas, pago con QR Bre-B y factura
            electrónica al instante.
          </p>
        </div>
        <p className="text-xs text-pastel/80">
          Demo de hackatón. Los boletos generados no son oficiales.
        </p>
      </section>

      <section className="p-8">
        <h2 className="text-5xl leading-none text-brand">{isLogin ? "Inicia sesión" : "Crea tu cuenta"}</h2>
        <p className="mt-1 text-sm text-muted">
          {isLogin ? "Necesitas una cuenta para ver eventos y comprar." : "Toma menos de un minuto."}
        </p>
        <form
          noValidate
          className="mt-6 flex flex-col gap-4"
          onSubmit={handleSubmit((v) => {
            if (!submit.isPending) submit.mutate(v);
          })}
        >
          {!isLogin && (
            <label className="text-sm">
              <span className="mb-1 block text-muted">Nombre completo</span>
              <input className={field} autoComplete="name" {...register("name")} {...aria("name")} />
              {err("name")}
            </label>
          )}
          <label className="text-sm">
            <span className="mb-1 block text-muted">Correo electrónico</span>
            <input
              className={field}
              type="email"
              autoComplete="email"
              {...register("email")}
              {...aria("email")}
            />
            {err("email")}
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-muted">Contraseña</span>
            <input
              className={field}
              type="password"
              autoComplete={isLogin ? "current-password" : "new-password"}
              {...register("password")}
              {...aria("password")}
            />
            {err("password")}
          </label>
          {submit.isError && <ErrorBox message={submit.error.message} />}
          <Button type="submit" disabled={submit.isPending}>
            {submit.isPending ? (
              <Spinner label={isLogin ? "Ingresando…" : "Creando cuenta…"} />
            ) : isLogin ? (
              "Ingresar"
            ) : (
              "Crear cuenta"
            )}
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-muted">
          {isLogin ? "¿No tienes cuenta? " : "¿Ya tienes cuenta? "}
          <Link to={other} className="font-semibold text-brand-mid underline">
            {isLogin ? "Regístrate" : "Inicia sesión"}
          </Link>
        </p>
      </section>
    </div>
  );
}
