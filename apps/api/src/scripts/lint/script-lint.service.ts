import { Injectable } from '@nestjs/common'

export interface LintError {
  code: string
  message: string
  severity: 'error' | 'warning'
  field?: string
}

export interface LintResult {
  valid: boolean
  errors: LintError[]
  warnings: LintError[]
}

const SNAKE_CASE_RE = /^[a-z][a-z0-9_]*$/

type RawStep = Record<string, unknown>

@Injectable()
export class ScriptLintService {
  lint(body: Record<string, unknown>): LintResult {
    const errors: LintError[] = []
    const warnings: LintError[] = []

    const steps = (body['steps'] as RawStep[]) ?? []
    const entryStep = body['entry_step'] as string | undefined

    const stepIds = new Set(steps.map((s) => s['id'] as string))
    const stepMap = new Map(steps.map((s) => [s['id'] as string, s]))

    // L001: Step id must be snake_case
    for (const step of steps) {
      const id = step['id'] as string
      if (!SNAKE_CASE_RE.test(id)) {
        errors.push({
          code: 'L001',
          severity: 'error',
          message: `Step id '${id}' must be snake_case (lowercase letters, digits, underscores, starts with letter)`,
          field: `steps[${id}].id`,
        })
      }
    }

    // L002: entry_step must exist in steps
    if (entryStep && !stepIds.has(entryStep)) {
      errors.push({
        code: 'L002',
        severity: 'error',
        message: `entry_step '${entryStep}' does not exist in steps`,
        field: 'entry_step',
      })
    }

    // L003: All transition.goto must point to existing step
    for (const step of steps) {
      const transitions = (step['transitions'] as RawStep[]) ?? []
      for (const t of transitions) {
        const goto = t['goto'] as string
        if (!stepIds.has(goto)) {
          errors.push({
            code: 'L003',
            severity: 'error',
            message: `Transition goto '${goto}' in step '${step['id'] as string}' does not exist`,
            field: `steps[${step['id'] as string}].transitions`,
          })
        }
      }
    }

    // L004: fallback_goto (if present) must point to existing step
    for (const step of steps) {
      const fallbackGoto = step['fallback_goto'] as string | undefined
      if (fallbackGoto && !stepIds.has(fallbackGoto)) {
        errors.push({
          code: 'L004',
          severity: 'error',
          message: `fallback_goto '${fallbackGoto}' in step '${step['id'] as string}' does not exist`,
          field: `steps[${step['id'] as string}].fallback_goto`,
        })
      }
    }

    // L005: speak_listen step must have reprompt_variants with ≥3 variants
    for (const step of steps) {
      if (step['type'] === 'speak_listen') {
        const reprompts = (step['reprompt_variants'] as unknown[]) ?? []
        if (reprompts.length < 3) {
          errors.push({
            code: 'L005',
            severity: 'error',
            message: `speak_listen step '${step['id'] as string}' must have ≥3 reprompt_variants (found ${reprompts.length})`,
            field: `steps[${step['id'] as string}].reprompt_variants`,
          })
        }
      }
    }

    // L006: No unreachable steps (BFS from entry_step)
    if (entryStep && stepIds.has(entryStep)) {
      const reachable = new Set<string>()
      const queue = [entryStep]
      while (queue.length) {
        const current = queue.shift()!
        if (reachable.has(current)) continue
        reachable.add(current)
        const step = stepMap.get(current)
        if (!step) continue
        for (const t of (step['transitions'] as RawStep[]) ?? []) {
          const g = t['goto'] as string
          if (!reachable.has(g) && stepIds.has(g)) queue.push(g)
        }
        const fb = step['fallback_goto'] as string | undefined
        if (fb && !reachable.has(fb) && stepIds.has(fb)) queue.push(fb)
      }
      for (const step of steps) {
        const id = step['id'] as string
        if (!reachable.has(id)) {
          errors.push({
            code: 'L006',
            severity: 'error',
            message: `Step '${id}' is unreachable from entry_step '${entryStep}'`,
            field: `steps[${id}]`,
          })
        }
      }
    }

    // L007: handoff steps should have data.reason (warning — schema extension pending)
    for (const step of steps) {
      if (step['type'] === 'handoff') {
        const data = step['data'] as Record<string, unknown> | undefined
        if (!data?.['reason']) {
          warnings.push({
            code: 'L007',
            severity: 'warning',
            message: `handoff step '${step['id'] as string}' should declare a reason in step.data.reason`,
            field: `steps[${step['id'] as string}].data.reason`,
          })
        }
      }
    }

    // L008: Total steps ≤ 50
    if (steps.length > 50) {
      errors.push({
        code: 'L008',
        severity: 'error',
        message: `Total steps (${steps.length}) exceeds maximum of 50 per campaign`,
        field: 'steps',
      })
    }

    return { valid: errors.length === 0, errors, warnings }
  }
}
