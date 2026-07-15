import { RotateCcw } from 'lucide-react';
import { availableTags } from '../../mocks/data';
import type { SearchFilters } from '../../types';
import { hasActiveFilters } from '../../utils/searchParams';
import { Button } from '../../components/ui/Button';

interface FiltersPanelProps {
  filters: SearchFilters;
  onChange: (filters: SearchFilters) => void;
}

const filterTags = availableTags.filter((tag) =>
  [
    'python',
    'asyncio',
    'pandas',
    'django',
    'fastapi',
    'numpy',
    'requests',
    'sqlalchemy',
    'pytest',
  ].includes(tag.slug),
);

export function FiltersPanel({ filters, onChange }: FiltersPanelProps) {
  const toggleTag = (slug: string) => {
    onChange({
      ...filters,
      tags: filters.tags.includes(slug)
        ? filters.tags.filter((tag) => tag !== slug)
        : [...filters.tags, slug],
    });
  };

  return (
    <div className="space-y-5">
      <fieldset>
        <legend className="mb-2 text-xs font-medium text-muted">Теги</legend>
        <div className="space-y-1">
          {filterTags.map((tag) => (
            <label
              key={tag.slug}
              className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-xs text-muted transition hover:bg-elevated hover:text-ink"
            >
              <input
                type="checkbox"
                checked={filters.tags.includes(tag.slug)}
                onChange={() => toggleTag(tag.slug)}
                className="size-3.5 rounded border-line bg-canvas accent-indigo-500"
              />
              {tag.name}
              <span className="ml-auto font-mono text-[10px] text-muted/70">
                {tag.slug === 'python' ? '22' : 2 + (tag.slug.length % 7)}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="block text-xs font-medium text-muted">
        Минимальный рейтинг
        <select
          value={filters.minScore}
          onChange={(event) => onChange({ ...filters, minScore: Number(event.target.value) })}
          className="mt-2 h-9 w-full rounded-lg border border-line bg-elevated px-2.5 text-xs text-ink"
        >
          <option value={0}>Любой</option>
          <option value={10}>10 и выше</option>
          <option value={50}>50 и выше</option>
          <option value={100}>100 и выше</option>
        </select>
      </label>

      <div className="space-y-2">
        <label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-muted">
          <input
            type="checkbox"
            checked={filters.acceptedOnly}
            onChange={(event) => onChange({ ...filters, acceptedOnly: event.target.checked })}
            className="mt-1 size-3.5 rounded border-line bg-canvas accent-indigo-500"
          />
          Только с принятым ответом
        </label>
        <label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-muted">
          <input
            type="checkbox"
            checked={filters.hasCodeOnly}
            onChange={(event) => onChange({ ...filters, hasCodeOnly: event.target.checked })}
            className="mt-1 size-3.5 rounded border-line bg-canvas accent-indigo-500"
          />
          Только с кодом
        </label>
      </div>

      <label className="block text-xs font-medium text-muted">
        Сортировка
        <select
          value={filters.sort}
          onChange={(event) =>
            onChange({
              ...filters,
              sort: event.target.value as SearchFilters['sort'],
            })
          }
          className="mt-2 h-9 w-full rounded-lg border border-line bg-elevated px-2.5 text-xs text-ink"
        >
          <option value="relevance">По релевантности</option>
          <option value="date">По дате</option>
          <option value="score">По рейтингу</option>
        </select>
      </label>

      <Button
        variant="ghost"
        size="sm"
        className="w-full"
        disabled={!hasActiveFilters(filters)}
        onClick={() =>
          onChange({
            tags: [],
            minScore: 0,
            acceptedOnly: false,
            hasCodeOnly: false,
            sort: 'relevance',
          })
        }
      >
        <RotateCcw className="size-3.5" aria-hidden="true" />
        Сбросить фильтры
      </Button>
    </div>
  );
}
