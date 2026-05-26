import { z } from 'zod'
import { PAUSE_TIERS, BEAT_ROLES, STEP_TYPES, CALL_DIRECTIONS } from '../constants/prosody'

export const BeatSchema = z.object({
  text: z.string().min(1),
  pause_after: z.enum(PAUSE_TIERS).default('none'),
  role: z.enum(BEAT_ROLES).default('agent'),
})

export const VariantSchema = z.object({
  id: z.string(),
  beats: z.array(BeatSchema).min(1),
})

export const IntentExampleSchema = z.object({
  text: z.string(),
  slots: z.record(z.string()).optional(),
})

export const TransitionSchema = z.object({
  when: z.string(),
  goto: z.string(),
})

export const StepSchema = z.object({
  id: z.string().regex(/^[a-z][a-z0-9_]*$/, 'Step id must be snake_case'),
  type: z.enum(STEP_TYPES),
  variants: z.array(VariantSchema).min(1),
  reprompt_variants: z.array(VariantSchema).min(3).optional(),
  transitions: z.array(TransitionSchema).optional(),
  fallback_goto: z.string().optional(),
  max_no_match: z.number().int().positive().default(3),
})

export const IntentCatalogSchema = z.object({
  intent: z.string(),
  examples: z.array(IntentExampleSchema).min(1),
  slots: z.array(z.string()).optional(),
})

export const CallScriptSchema = z.object({
  id: z.string().uuid(),
  version: z.string().regex(/^\d+\.\d+\.\d+$/),
  campaign_id: z.string().uuid(),
  direction: z.enum(CALL_DIRECTIONS),
  voice_profile: z.string(),
  entry_step: z.string(),
  steps: z.array(StepSchema).min(1),
  intents: z.array(IntentCatalogSchema).optional(),
})

export type Beat = z.infer<typeof BeatSchema>
export type Variant = z.infer<typeof VariantSchema>
export type Step = z.infer<typeof StepSchema>
export type CallScript = z.infer<typeof CallScriptSchema>
