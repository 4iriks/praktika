import { Check, Circle, LoaderCircle } from 'lucide-react';
import type { RagStage } from '../../types';
import { cn } from '../../utils/cn';

const stages: Array<{ value: RagStage; label: string }> = [
  { value: 'validating', label: 'Проверка' },
  { value: 'searching', label: 'Поиск кандидатов' },
  { value: 'fusing', label: 'Гибридное объединение' },
  { value: 'reranking', label: 'Переранжирование' },
  { value: 'selecting_sources', label: 'Выбор источников' },
  { value: 'generating', label: 'Генерация ответа' },
  { value: 'validating_citations', label: 'Проверка цитат' },
  { value: 'saving', label: 'Сохранение' },
];

export function RagProgress({ stage }: { stage: RagStage }) {
  const activeIndex =
    stage === 'complete' || stage === 'completed'
      ? stages.length
      : stages.findIndex((item) => item.value === stage);

  return (
    <div className="grid gap-2 border-b border-line bg-elevated/25 px-4 py-3 sm:grid-cols-4 sm:px-6 xl:grid-cols-8">
      {stages.map((item, index) => {
        const complete = index < activeIndex || stage === 'complete' || stage === 'completed';
        const active = index === activeIndex;
        return (
          <div key={item.value} className="flex items-center gap-2">
            <span
              className={cn(
                'grid size-5 shrink-0 place-items-center rounded-full border',
                complete && 'border-success/30 bg-success/10 text-success',
                active && 'border-info/30 bg-info/10 text-info',
                !complete && !active && 'border-line text-muted/60',
              )}
            >
              {complete ? (
                <Check className="size-3" aria-hidden="true" />
              ) : active ? (
                <LoaderCircle className="size-3 animate-spin" aria-hidden="true" />
              ) : (
                <Circle className="size-2" aria-hidden="true" />
              )}
            </span>
            <span
              className={cn(
                'text-[10px] leading-4',
                complete || active ? 'text-ink' : 'text-muted',
              )}
            >
              {item.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
