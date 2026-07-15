import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Pagination as PaginationValue } from '../../types';
import { Button } from '../../components/ui/Button';

interface PaginationProps {
  value: PaginationValue;
  onPageChange: (page: number) => void;
}

export function Pagination({ value, onPageChange }: PaginationProps) {
  if (value.totalPages <= 1) return null;
  const pages = Array.from(
    { length: Math.min(5, value.totalPages) },
    (_, index) => Math.max(1, Math.min(value.totalPages - 4, value.page - 2)) + index,
  ).filter((page) => page <= value.totalPages);

  return (
    <nav className="flex items-center justify-between gap-3 py-2" aria-label="Страницы результатов">
      <Button
        size="sm"
        variant="secondary"
        disabled={value.page <= 1}
        onClick={() => onPageChange(value.page - 1)}
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        <span className="hidden sm:inline">Назад</span>
      </Button>
      <div className="flex items-center gap-1">
        {pages.map((page) => (
          <Button
            key={page}
            size="icon"
            variant={page === value.page ? 'primary' : 'ghost'}
            className="size-8 text-xs"
            onClick={() => onPageChange(page)}
            aria-label={'Страница ' + page}
            aria-current={page === value.page ? 'page' : undefined}
          >
            {page}
          </Button>
        ))}
      </div>
      <Button
        size="sm"
        variant="secondary"
        disabled={value.page >= value.totalPages}
        onClick={() => onPageChange(value.page + 1)}
      >
        <span className="hidden sm:inline">Дальше</span>
        <ChevronRight className="size-4" aria-hidden="true" />
      </Button>
    </nav>
  );
}
