/**
 * Live admin metrics stream for cookie-authenticated admin sessions.
 * Uses same-origin SSE so raw admin JWTs never enter JavaScript.
 */

export type AdminMetricsStreamHandlers = {
  onOpen?: () => void;
  onMessage: (payload: unknown) => void;
  onError?: () => void;
};

export function connectAdminMetricsStream(handlers: AdminMetricsStreamHandlers): () => void {
  if (typeof window === 'undefined') return () => {};

  let es: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;

  const scheduleRetry = () => {
    if (stopped) return;
    handlers.onError?.();
    retryTimer = setTimeout(connect, 5000);
  };

  const connect = () => {
    if (stopped) return;
    // Browser admin sessions are cookie-only; never recover or transport a raw
    // JWT through JavaScript. EventSource sends same-origin HttpOnly cookies.
    es = new EventSource('/api/admin/metrics/stream');
    es.onopen = () => handlers.onOpen?.();
    es.onmessage = (ev) => {
      try {
        handlers.onMessage(JSON.parse(ev.data));
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      es?.close();
      es = null;
      scheduleRetry();
    };
  };

  connect();

  return () => {
    stopped = true;
    clearTimeout(retryTimer);
    es?.close();
  };
}
