import type { BackgroundJob, JobStage } from '../types';

const stages: readonly JobStage[] = [
  'PREPARING',
  'CRAWLING',
  'CLEANING',
  'DEDUPLICATING',
  'CHUNKING',
  'EMBEDDING',
  'INDEXING_BM25',
  'INDEXING_VECTOR',
  'FINALIZING',
];

export function materializeJob(job: BackgroundJob, clock = Date.now()): BackgroundJob {
  if (job.status === 'COMPLETED' || job.status === 'FAILED' || job.status === 'CANCELLED') {
    return { ...job };
  }

  const queuedUntil = Date.parse(job.createdAt) + 2_000;
  if (job.status === 'QUEUED' && clock < queuedUntil) return { ...job };

  const startedAt = job.startedAt ?? new Date(queuedUntil).toISOString();
  const elapsed = Math.max(0, clock - Date.parse(startedAt));
  const planned = Math.max(1_000, job.plannedDurationMs);
  const progress = Math.min(100, Math.floor((elapsed / planned) * 100));
  const processedItems = Math.min(job.totalItems, Math.floor((job.totalItems * progress) / 100));

  if (progress >= 100) {
    return {
      ...job,
      status: 'COMPLETED',
      stage: 'FINALIZING',
      progress: 100,
      processedItems: job.totalItems,
      startedAt,
      finishedAt: new Date(Date.parse(startedAt) + planned).toISOString(),
      durationMs: planned,
      cancellable: false,
    };
  }

  const stageIndex = Math.min(stages.length - 1, Math.floor((progress / 100) * stages.length));
  return {
    ...job,
    status: 'RUNNING',
    stage: stages[stageIndex] ?? 'PREPARING',
    progress,
    processedItems,
    startedAt,
  };
}

export function hasActiveJob(jobs: readonly BackgroundJob[]): boolean {
  return jobs.some((job) => job.status === 'QUEUED' || job.status === 'RUNNING');
}
