import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError, UNAUTHORIZED_EVENT, api, type UserOut } from "../api/client";
import { Spinner } from "../components/ui";

const ME = ["me"] as const;

/** Usuario actual: null si no hay sesión, undefined mientras carga. */
export function useMe(): { user: UserOut | null | undefined; loading: boolean } {
  const q = useQuery({
    queryKey: ME,
    queryFn: async () => {
      try {
        return await api.me();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
  return { user: q.data, loading: q.isPending };
}

export function useSetMe() {
  const qc = useQueryClient();
  return useCallback(
    (user: UserOut | null) => {
      qc.setQueryData(ME, user);
      // Al cambiar de usuario no deben quedar datos del anterior en caché.
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    },
    [qc],
  );
}

/** Si cualquier llamada a la API recibe 401, se cierra la sesión local y se vuelve al login. */
export function useUnauthorizedListener() {
  const setMe = useSetMe();
  useEffect(() => {
    const onUnauthorized = () => setMe(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [setMe]);
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useMe();
  const location = useLocation();
  if (loading) {
    return (
      <div className="py-20 text-center">
        <Spinner label="Verificando tu sesión…" />
      </div>
    );
  }
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/ingresar?next=${next}`} replace />;
  }
  return <>{children}</>;
}
