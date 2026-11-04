import { useMutation } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api/client";
import { CurrencySelector } from "./components/ui";
import { RequireAuth, useMe, useSetMe, useUnauthorizedListener } from "./lib/auth";
import type { Currency } from "./lib/format";
import { CurrencyContext, readStoredCurrency, storeCurrency } from "./lib/hooks";
import { AuthPage } from "./pages/AuthPage";
import { CheckoutPage } from "./pages/CheckoutPage";
import { ConfirmationPage } from "./pages/ConfirmationPage";
import { EventPage } from "./pages/EventPage";
import { MyOrdersPage } from "./pages/MyOrdersPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { SearchPage } from "./pages/SearchPage";

function UserMenu({ onDark }: { onDark: boolean }) {
  const { user } = useMe();
  const setMe = useSetMe();
  const navigate = useNavigate();
  const logout = useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      setMe(null);
      navigate("/ingresar", { replace: true });
    },
  });
  if (!user) return null;
  const idle = onDark ? "text-white/80 hover:text-white" : "text-muted hover:text-brand";
  const active = onDark ? "text-white border-b border-white" : "text-brand border-b border-brand";
  const link = ({ isActive }: { isActive: boolean }) =>
    `eyebrow py-1 transition ${isActive ? active : `${idle} border-b border-transparent`}`;
  return (
    <nav className="flex flex-wrap items-center gap-x-6 gap-y-2" aria-label="Principal">
      <NavLink to="/" end className={link}>
        Conciertos
      </NavLink>
      <NavLink to="/mis-compras" className={link}>
        Mis compras
      </NavLink>
      <span className={`eyebrow hidden sm:inline ${onDark ? "text-white/60" : "text-muted"}`} title={user.email}>
        {user.name.split(" ")[0]}
      </span>
      <button
        type="button"
        onClick={() => logout.mutate()}
        disabled={logout.isPending}
        className={`eyebrow border px-4 py-2 transition ${
          onDark
            ? "border-white/70 text-white hover:bg-white hover:text-brand"
            : "border-brand text-brand hover:bg-brand hover:text-white"
        }`}
      >
        Salir
      </button>
    </nav>
  );
}

const Protected = ({ children }: { children: ReactNode }) => <RequireAuth>{children}</RequireAuth>;

export function App() {
  useUnauthorizedListener();
  const { user } = useMe();
  const { pathname } = useLocation();
  const [currency, setCurrencyState] = useState<Currency>(readStoredCurrency);
  const ctx = useMemo(
    () => ({
      currency,
      setCurrency: (c: Currency) => {
        setCurrencyState(c);
        storeCurrency(c);
      },
    }),
    [currency],
  );
  // La portada usa todo el ancho; el resto de páginas va en un contenedor centrado.
  const isHome = pathname === "/" && Boolean(user);

  return (
    <CurrencyContext.Provider value={ctx}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-brand focus:px-3 focus:py-2 focus:text-white"
      >
        Saltar al contenido
      </a>
      <header className="sticky top-0 z-40 bg-ink/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-5">
          <Link to="/" className="font-display text-4xl uppercase leading-none text-brand">
            Turismo Musical
          </Link>
          <div className="flex flex-wrap items-center gap-6">
            {user && !isHome && <CurrencySelector />}
            <UserMenu onDark={false} />
          </div>
        </div>
      </header>
      <main id="main" className={isHome ? "" : "mx-auto max-w-6xl px-4 py-10 sm:py-14"}>
        <Routes>
          <Route path="/ingresar" element={<AuthPage mode="login" />} />
          <Route path="/registro" element={<AuthPage mode="register" />} />
          <Route path="/" element={<Protected><SearchPage /></Protected>} />
          <Route path="/eventos/:eventId" element={<Protected><EventPage /></Protected>} />
          <Route path="/checkout/:eventId" element={<Protected><CheckoutPage /></Protected>} />
          <Route path="/mis-compras" element={<Protected><MyOrdersPage /></Protected>} />
          <Route path="/ordenes/:orderId" element={<Protected><ProcessingPage /></Protected>} />
          <Route
            path="/ordenes/:orderId/listo"
            element={<Protected><ConfirmationPage /></Protected>}
          />
          <Route
            path="*"
            element={
              <p>
                Página no encontrada.{" "}
                <Link to="/" className="text-brand-mid underline">
                  Volver al inicio
                </Link>
              </p>
            }
          />
        </Routes>
      </main>
      <footer className="bg-brand text-white">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 md:grid-cols-[1.5fr_1fr_1fr]">
          <div>
            <p className="font-display text-5xl uppercase leading-none">Turismo Musical</p>
            <p className="mt-3 max-w-sm text-sm font-light text-pastel">
              Demo de compra de boletos. Cobro en COP con Factus Pay y factura electrónica con
              Factus (DIAN).
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <p className="eyebrow text-brand-2">Navegación</p>
            <Link to="/" className="eyebrow text-white/80 hover:text-white">
              Conciertos
            </Link>
            <Link to="/mis-compras" className="eyebrow text-white/80 hover:text-white">
              Mis compras
            </Link>
          </div>
          <div className="flex flex-col gap-2">
            <p className="eyebrow text-brand-2">Aviso</p>
            <p className="text-sm font-light text-pastel">
              Los boletos generados son de demostración y no son oficiales de Ticketmaster ni de
              ningún organizador.
            </p>
          </div>
        </div>
        <div className="border-t border-white/15">
          <p className="mx-auto max-w-7xl px-4 py-5 text-xs font-light text-white/60">
            © 2026 Turismo Musical · Proyecto de hackatón
          </p>
        </div>
      </footer>
    </CurrencyContext.Provider>
  );
}
