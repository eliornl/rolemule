export function debounce<T extends (...args: never[]) => void>(
  fn: T,
  wait: number,
): (...args: Parameters<T>) => void {
  let timer = 0;
  return (...args: Parameters<T>) => {
    clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

export function parseSalaryDigits(
  value: string | number | null | undefined,
): number {
  const digits = String(value ?? '').replace(/[^\d]/g, '');
  if (!digits) return 0;
  const n = Number(digits);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
}

export function readSalaryField(el: HTMLInputElement | null | undefined): number {
  if (!el) return 0;
  return parseSalaryDigits(el.value);
}

export function formatDateForInput(dateStr: string | null | undefined): string {
  if (!dateStr) return '';

  if (typeof dateStr === 'string' && dateStr.toLowerCase() === 'present') {
    return '';
  }

  if (/^\d{4}-\d{2}$/.test(dateStr)) return dateStr;
  if (/^\d{4}$/.test(dateStr)) return `${dateStr}-01`;

  try {
    const date = new Date(dateStr);
    if (!isNaN(date.getTime())) {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      return `${year}-${month}`;
    }
  } catch (e) {
    console.warn('Could not parse date:', dateStr);
  }

  return '';
}

export function isValidUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

export function sanitizeText(text: string | null | undefined): string {
  if (!text) return String(text ?? '');
  return text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
}
