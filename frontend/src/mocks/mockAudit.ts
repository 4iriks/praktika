import type {
  AuditAction,
  AuditEntityType,
  AuditEvent,
  AuditOutcome,
  JsonObject,
  User,
} from '../types';
import { mockStorageKeys, readArray, writeJson } from './mockStorage';

export interface AuditInput {
  actor?: User;
  action: AuditAction;
  entityType: AuditEntityType;
  entityId: string;
  entityLabel: string;
  outcome?: AuditOutcome;
  batchId?: string;
  summary: string;
  before?: JsonObject;
  after?: JsonObject;
  metadata?: JsonObject;
  errorCode?: AuditEvent['errorCode'];
}

function makeId(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  return `${prefix}-${random}`;
}

function isAuditEvent(value: unknown): value is AuditEvent {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'action' in value &&
    typeof value.action === 'string' &&
    'entityType' in value &&
    typeof value.entityType === 'string' &&
    'createdAt' in value &&
    typeof value.createdAt === 'string' &&
    'requestId' in value &&
    typeof value.requestId === 'string'
  );
}

export function readAuditEvents(): AuditEvent[] {
  return readArray(window.localStorage, mockStorageKeys.audit, isAuditEvent);
}

export function appendAudit(input: AuditInput): AuditEvent {
  const events = readAuditEvents();
  const event: AuditEvent = {
    id: makeId('audit'),
    actorUserId: input.actor?.id,
    actorName: input.actor?.displayName ?? 'Система',
    actorRole: input.actor?.role,
    action: input.action,
    entityType: input.entityType,
    entityId: input.entityId,
    entityLabel: input.entityLabel,
    outcome: input.outcome ?? 'SUCCESS',
    ipAddress: '127.0.0.1',
    requestId: makeId('req'),
    batchId: input.batchId,
    createdAt: new Date().toISOString(),
    summary: input.summary,
    before: input.before,
    after: input.after,
    metadata: input.metadata,
    errorCode: input.errorCode,
  };
  events.push(event);
  writeJson(window.localStorage, mockStorageKeys.audit, events);
  return event;
}
