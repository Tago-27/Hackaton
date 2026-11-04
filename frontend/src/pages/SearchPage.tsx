import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { EventCard, EventCardSkeleton, EventImage } from "../components/EventCard";
import { CurrencySelector, ErrorBox } from "../components/ui";
import { useDebounced } from "../lib/hooks";

const COUNTRIES = [
  ["", "Todos los países"],
  ["CO", "Colombia"],
  ["US", "Estados Unidos"],
  ["MX", "México"],
  ["ES", "España"],
  ["GB", "Reino Unido"],
  ["JP", "Japón"],
  ["AR", "Argentina"],
  ["BR", "Brasil"],
  ["CL", "Chile"],
] as const;

const input =
  "w-full border-0 border-b border-line bg-transparent px-0 py-3 text-base font-light text-navy placeholder:text-muted/70 focus:border-brand focus:outline-none focus:ring-0";

const STEPS = [
  ["01", "Elige tu concierto", "Busca por artista, ciudad o país y compara el precio en cinco monedas."],
  ["02", "Paga en pesos", "Escanea el QR Bre-B desde la app de tu banco. El cobro siempre es en COP."],
  [
    "03",
    "Recibe todo al instante",
    "Tus boletos en PDF, uno por página, y tu factura electrónica validada ante la DIAN.",
  ],
] as const;

export function SearchPage() {
  const [artist, setArtist] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const params = useDebounced({ artist: artist.trim(), city: city.trim(), country });

  const q = useQuery({
    queryKey: ["events", params],
    queryFn: ({ signal }) => api.searchEvents(params, signal),
  });
  // La portada usa la imagen del primer concierto de la búsqueda inicial (sin filtros).
  const hero = useQuery({
    queryKey: ["events", { artist: "", city: "", country: "" }],
    queryFn: ({ signal }) => api.searchEvents({}, signal),
    staleTime: 5 * 60_000,
  });
  const heroImage = hero.data?.items.find((e) => e.image_url)?.image_url ?? null;

  return (
    <>
      {/* Portada: imagen a la izquierda, título gigante a la derecha */}
      <section className="mx-auto grid max-w-7xl items-center gap-10 px-4 pb-16 pt-6 md:grid-cols-[1.15fr_1fr] md:pb-24">
        <div className="relative overflow-hidden bg-panel">
          {heroImage ? (
            <img src={heroImage} alt="" aria-hidden="true" className="aspect-[4/5] w-full object-cover md:aspect-[5/6]" />
          ) : (
            <EventImage src={null} alt="" className="aspect-[4/5] w-full md:aspect-[5/6]" />
          )}
        </div>
        <div className="flex flex-col">
          <h1 className="text-[clamp(5rem,14vw,11rem)] leading-[0.82] text-brand">
            Turismo
            <br />
            Musical
          </h1>
          <p className="mt-8 max-w-md text-lg font-light leading-relaxed text-navy">
            Conciertos alrededor del mundo, precios en cinco monedas y pago en pesos con QR Bre-B.
          </p>
          <a
            href="#temporada"
            className="mt-10 inline-flex w-fit items-center gap-2 font-medium text-navy hover:text-brand-mid"
          >
            Ver conciertos <span aria-hidden="true">›</span>
          </a>
        </div>
      </section>

      {/* Bloque de color sólido */}
      <section className="bg-brand text-white">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-20 md:grid-cols-[1.4fr_1fr] md:py-28">
          <h2 className="text-[clamp(3.5rem,9vw,7.5rem)] leading-[0.85] text-white">
            Una armonía entre viaje y música
          </h2>
          <div className="flex flex-col justify-end gap-5 font-light leading-relaxed text-pastel">
            <p>
              Reunimos conciertos de todo el mundo en un solo lugar para que planees tu próximo viaje
              alrededor de la música que amas.
            </p>
            <p>
              Compara precios en USD, EUR, GBP y JPY como referencia y paga siempre en pesos
              colombianos, con factura electrónica válida ante la DIAN.
            </p>
            <a href="#como-funciona" className="mt-2 inline-flex w-fit items-center gap-2 font-medium text-white hover:text-brand-2">
              Cómo funciona <span aria-hidden="true">›</span>
            </a>
          </div>
        </div>
      </section>

      {/* Temporada de conciertos */}
      <section id="temporada" className="scroll-mt-24 py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-4">
          <div className="grid gap-6 md:grid-cols-[1.4fr_1fr] md:items-end">
            <h2 className="text-[clamp(3.5rem,8vw,6.5rem)] leading-[0.85] text-brand">
              Temporada de conciertos
            </h2>
            <p className="font-light leading-relaxed text-muted">
              Encuentra el concierto perfecto para tu próximo viaje. Filtra por artista, ciudad o
              país.
            </p>
          </div>

          <form
            role="search"
            onSubmit={(e) => e.preventDefault()}
            className="mt-12 grid gap-6 sm:grid-cols-3"
          >
            <label className="flex flex-col">
              <span className="eyebrow text-muted">Artista o evento</span>
              <input
                className={input}
                value={artist}
                onChange={(e) => setArtist(e.target.value)}
                placeholder="Shakira, Coldplay…"
                autoComplete="off"
              />
            </label>
            <label className="flex flex-col">
              <span className="eyebrow text-muted">Ciudad</span>
              <input
                className={input}
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Bogotá, Madrid…"
                autoComplete="off"
              />
            </label>
            <label className="flex flex-col">
              <span className="eyebrow text-muted">País</span>
              <select className={input} value={country} onChange={(e) => setCountry(e.target.value)}>
                {COUNTRIES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </form>

          <div className="mt-14" aria-live="polite" aria-busy={q.isFetching}>
            <h3 className="sr-only">Resultados</h3>
            {q.isError ? (
              <ErrorBox message={q.error.message} onRetry={() => void q.refetch()} />
            ) : q.isPending ? (
              <ul className="grid gap-x-8 gap-y-14 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 6 }, (_, i) => (
                  <EventCardSkeleton key={i} />
                ))}
              </ul>
            ) : q.data.items.length === 0 ? (
              <div className="border-y border-line py-16 text-center">
                <p className="font-display text-5xl uppercase text-brand">No encontramos conciertos</p>
                <p className="mt-2 font-light text-muted">Prueba con otro artista, ciudad o país.</p>
              </div>
            ) : (
              <>
                <div className="mb-8 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
                  <p className="eyebrow text-muted">{q.data.items.length} conciertos</p>
                  <div className="flex items-center gap-3">
                    <span className="eyebrow text-muted">Ver precios en</span>
                    <CurrencySelector />
                  </div>
                </div>
                <ul className="grid gap-x-8 gap-y-14 sm:grid-cols-2 lg:grid-cols-3">
                  {q.data.items.map((ev) => (
                    <EventCard key={ev.id} event={ev} />
                  ))}
                </ul>
              </>
            )}
          </div>
        </div>
      </section>

      {/* Cómo funciona */}
      <section id="como-funciona" className="scroll-mt-24 bg-panel py-20 md:py-28">
        <div className="mx-auto max-w-7xl px-4">
          <h2 className="text-[clamp(3.5rem,8vw,6.5rem)] leading-[0.85] text-brand">Cómo funciona</h2>
          <ol className="mt-14 grid gap-10 md:grid-cols-3">
            {STEPS.map(([n, title, text]) => (
              <li key={n} className="border-t border-brand pt-6">
                <p className="font-display text-6xl text-brand-mid">{n}</p>
                <p className="mt-3 text-lg font-medium text-navy">{title}</p>
                <p className="mt-2 font-light leading-relaxed text-muted">{text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </>
  );
}
