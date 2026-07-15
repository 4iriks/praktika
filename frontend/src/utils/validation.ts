export const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface PasswordChecks {
  minLength: boolean;
  lowercase: boolean;
  uppercase: boolean;
  digit: boolean;
}

export function getPasswordChecks(password: string): PasswordChecks {
  return {
    minLength: password.length >= 8,
    lowercase: /[a-zа-яё]/u.test(password),
    uppercase: /[A-ZА-ЯЁ]/u.test(password),
    digit: /\d/u.test(password),
  };
}

export function isStrongPassword(password: string): boolean {
  return Object.values(getPasswordChecks(password)).every(Boolean);
}

export function normalizeEmail(email: string): string {
  return email.trim().toLocaleLowerCase('ru-RU');
}
