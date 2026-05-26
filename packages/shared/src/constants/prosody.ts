export const PAUSE_TIERS = ['none', 'micro', 'short', 'breath', 'medium', 'long', 'turn'] as const

export type PauseTier = (typeof PAUSE_TIERS)[number]

export const PAUSE_DURATION_MS: Record<PauseTier, number> = {
  none: 0,
  micro: 80,
  short: 150,
  breath: 250,
  medium: 400,
  long: 700,
  turn: 1000,
}

export const BEAT_ROLES = ['agent', 'system', 'silent'] as const
export type BeatRole = (typeof BEAT_ROLES)[number]

export const STEP_TYPES = ['speak', 'speak_listen', 'hold', 'handoff', 'hangup'] as const
export type StepType = (typeof STEP_TYPES)[number]

export const CALL_DIRECTIONS = ['inbound', 'outbound'] as const
export type CallDirection = (typeof CALL_DIRECTIONS)[number]
