import { Link } from "react-router-dom";
import type { EventOut } from "../api/client";
import { eventDateParts, formatMoney } from "../lib/format";
import { useCurrency } from "../lib/hooks";

export function EventImage({ src, alt, className }: { src: string | null; alt: string; className: string }) {
  if (!src) {
    return (
      <div
        aria-hidden="true"
        className={`${className} flex items-center justify-center bg-gradient-to-br from-brand via-brand-mid to-brand-2 text-4xl text-white`}
      >
        ♪
      </div>
    );
  }
  return <img src={src} alt={alt} loading="lazy" className={`${className} object-cover`} />;
}

/** Tarjeta de concierto: imagen, título, "fecha | lugar" y botón con borde. */
export function EventCard({ event }: { event: EventOut }) {
  const { currency } = useCurrency();
  const date = eventDateParts(event.date);
  const href = `/eventos/${encodeURIComponent(event.id)}`;
  const place = [event.venue, event.city].filter(Boolean).join(", ");

  return (
    <li className="group flex flex-col">
      <Link to={href} tabIndex={-1} aria-hidden="true" className="block overflow-hidden">
        <EventImage
          src={event.image_url}
          alt=""
          className="aspect-[4/3] w-full transition duration-700 group-hover:scale-105"
        />
      </Link>
      <h3 className="mt-5 text-lg font-medium leading-snug text-navy">
        <Link to={href} className="hover:text-brand-mid">
          {event.name}
        </Link>
      </h3>
      <p className="mt-1 text-sm font-light text-muted">
        {date ? `${date.short}` : "Fecha por confirmar"}
        {place && (
          <>
            <span className="mx-2 text-line" aria-hidden="true">
              |
            </span>
            {place}
          </>
        )}
      </p>
      <p className="mt-1 text-sm text-navy">
        <span className="text-muted">Desde </span>
        {formatMoney(event.display_prices[currency], currency)}
        {currency !== "COP" && <span className="text-xs text-muted"> · referencia</span>}
      </p>
      <Link
        to={href}
        className="mt-5 inline-flex w-40 items-center justify-center border border-navy px-4 py-2.5 text-sm text-navy transition hover:bg-brand hover:text-white"
      >
        Comprar boletos
      </Link>
    </li>
  );
}

/** Misma forma que la tarjeta real para evitar saltos de layout. */
export function EventCardSkeleton() {
  return (
    <li aria-hidden="true" className="flex flex-col">
      <div className="aspect-[4/3] w-full animate-pulse bg-line/70" />
      <div className="mt-5 h-5 w-4/5 animate-pulse bg-line" />
      <div className="mt-2 h-4 w-3/5 animate-pulse bg-line" />
      <div className="mt-2 h-4 w-24 animate-pulse bg-line" />
      <div className="mt-5 h-10 w-40 animate-pulse bg-line" />
    </li>
  );
}
