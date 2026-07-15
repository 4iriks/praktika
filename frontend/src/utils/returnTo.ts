export function isSafeReturnTo(value: string | null | undefined): value is string {
  return Boolean(
    value &&
      value.startsWith('/') &&
      !value.startsWith('//') &&
      !value.startsWith('/\\') &&
      !value.includes('\0'),
  );
}

export function getSafeReturnTo(search: string, state: unknown, fallback: string): string {
  const fromQuery = new URLSearchParams(search).get('returnTo');
  if (isSafeReturnTo(fromQuery)) return fromQuery;

  if (
    typeof state === 'object' &&
    state !== null &&
    'from' in state &&
    typeof state.from === 'string' &&
    isSafeReturnTo(state.from)
  ) {
    return state.from;
  }
  return fallback;
}

export function loginUrl(returnTo: string): string {
  const safe = isSafeReturnTo(returnTo) ? returnTo : '/';
  return '/login?returnTo=' + encodeURIComponent(safe);
}

export function registerUrl(returnTo: string): string {
  const safe = isSafeReturnTo(returnTo) ? returnTo : '/profile';
  return '/register?returnTo=' + encodeURIComponent(safe);
}
