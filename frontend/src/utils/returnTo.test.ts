import { describe, expect, it } from 'vitest';
import { getSafeReturnTo, isSafeReturnTo } from './returnTo';

describe('safe returnTo', () => {
  it('разрешает внутренний путь с query string', () => {
    expect(
      getSafeReturnTo('?returnTo=%2Fsaved%3Ftag%3Dpython', null, '/profile'),
    ).toBe('/saved?tag=python');
  });

  it('отклоняет внешний и protocol-relative адрес', () => {
    expect(isSafeReturnTo('https://evil.example')).toBe(false);
    expect(isSafeReturnTo('//evil.example/path')).toBe(false);
    expect(getSafeReturnTo('?returnTo=%2F%2Fevil.example', null, '/profile')).toBe('/profile');
  });
});
