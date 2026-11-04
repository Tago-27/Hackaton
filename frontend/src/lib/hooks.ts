import { createContext, useContext, useEffect, useState } from "react";
import type { Currency } from "./format";

export function useDebounced<T>(value: T, ms = 400): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

const KEY = "tm.displayCurrency";

export function readStoredCurrency(): Currency {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "COP" || v === "USD" || v === "EUR" || v === "GBP" || v === "JPY") return v;
  } catch {
    /* almacenamiento no disponible */
  }
  return "COP";
}

export function storeCurrency(c: Currency): void {
  try {
    localStorage.setItem(KEY, c);
  } catch {
    /* almacenamiento no disponible */
  }
}

export const CurrencyContext = createContext<{
  currency: Currency;
  setCurrency: (c: Currency) => void;
}>({ currency: "COP", setCurrency: () => undefined });

export const useCurrency = () => useContext(CurrencyContext);
