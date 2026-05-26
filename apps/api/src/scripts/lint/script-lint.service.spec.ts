import { ScriptLintService } from './script-lint.service'

const VALID_SCRIPT = {
  id: '00000000-0000-0000-0000-000000000001',
  version: '1.0.0',
  campaign_id: '00000000-0000-0000-0000-000000000010',
  direction: 'inbound',
  voice_profile: 'linh_clone_v1',
  entry_step: 'greeting',
  steps: [
    {
      id: 'greeting',
      type: 'speak_listen',
      variants: [{ id: 'v1', beats: [{ text: 'Xin chào', pause_after: 'turn' }] }],
      reprompt_variants: [
        { id: 'r1', beats: [{ text: 'Bạn cần hỗ trợ gì?', pause_after: 'turn' }] },
        { id: 'r2', beats: [{ text: 'Tôi vẫn đang nghe', pause_after: 'turn' }] },
        { id: 'r3', beats: [{ text: 'Tôi chuyển sang nhân viên', pause_after: 'turn' }] },
      ],
      transitions: [{ when: "intent == 'done'", goto: 'farewell' }],
      fallback_goto: 'farewell',
      max_no_match: 3,
    },
    {
      id: 'farewell',
      type: 'speak',
      variants: [{ id: 'v1', beats: [{ text: 'Tạm biệt', pause_after: 'long' }] }],
    },
  ],
}

describe('ScriptLintService', () => {
  let svc: ScriptLintService

  beforeEach(() => {
    svc = new ScriptLintService()
  })

  test('valid script passes all rules', () => {
    const result = svc.lint(VALID_SCRIPT)
    expect(result.valid).toBe(true)
    expect(result.errors).toHaveLength(0)
  })

  test('L001: rejects invalid step id (not snake_case)', () => {
    const script = {
      ...VALID_SCRIPT,
      steps: [{ ...VALID_SCRIPT.steps[0], id: 'Invalid-Step' }, VALID_SCRIPT.steps[1]],
    }
    const result = svc.lint(script)
    expect(result.errors.some((e) => e.code === 'L001')).toBe(true)
  })

  test('L001: rejects step id starting with digit', () => {
    const script = {
      ...VALID_SCRIPT,
      steps: [{ ...VALID_SCRIPT.steps[0], id: '1greeting' }, VALID_SCRIPT.steps[1]],
    }
    const result = svc.lint(script)
    expect(result.errors.some((e) => e.code === 'L001')).toBe(true)
  })

  test('L002: entry_step not in steps', () => {
    const result = svc.lint({ ...VALID_SCRIPT, entry_step: 'nonexistent' })
    expect(result.errors.some((e) => e.code === 'L002')).toBe(true)
  })

  test('L003: transition goto not in steps', () => {
    const modifiedStep = {
      ...VALID_SCRIPT.steps[0],
      transitions: [{ when: "intent == 'done'", goto: 'ghost_step' }],
    }
    const result = svc.lint({ ...VALID_SCRIPT, steps: [modifiedStep, VALID_SCRIPT.steps[1]] })
    expect(result.errors.some((e) => e.code === 'L003')).toBe(true)
  })

  test('L004: fallback_goto not in steps', () => {
    const modifiedStep = { ...VALID_SCRIPT.steps[0], fallback_goto: 'ghost_step' }
    const result = svc.lint({ ...VALID_SCRIPT, steps: [modifiedStep, VALID_SCRIPT.steps[1]] })
    expect(result.errors.some((e) => e.code === 'L004')).toBe(true)
  })

  test('L005: speak_listen with fewer than 3 reprompt_variants', () => {
    const modifiedStep = {
      ...VALID_SCRIPT.steps[0],
      reprompt_variants: [{ id: 'r1', beats: [{ text: 'Chỉ một', pause_after: 'turn' }] }],
    }
    const result = svc.lint({ ...VALID_SCRIPT, steps: [modifiedStep, VALID_SCRIPT.steps[1]] })
    expect(result.errors.some((e) => e.code === 'L005')).toBe(true)
  })

  test('L005: speak_listen with zero reprompt_variants', () => {
    const modifiedStep = { ...VALID_SCRIPT.steps[0], reprompt_variants: [] }
    const result = svc.lint({ ...VALID_SCRIPT, steps: [modifiedStep, VALID_SCRIPT.steps[1]] })
    expect(result.errors.some((e) => e.code === 'L005')).toBe(true)
  })

  test('L006: detects unreachable step', () => {
    const orphan = {
      id: 'orphan_step',
      type: 'speak',
      variants: [{ id: 'v1', beats: [{ text: 'Orphan', pause_after: 'long' }] }],
    }
    const result = svc.lint({ ...VALID_SCRIPT, steps: [...VALID_SCRIPT.steps, orphan] })
    expect(result.errors.some((e) => e.code === 'L006')).toBe(true)
  })

  test('L006: step reachable only via fallback_goto is not flagged', () => {
    const fallbackTarget = {
      id: 'staff',
      type: 'handoff',
      variants: [{ id: 'v1', beats: [{ text: 'Chuyển', pause_after: 'turn' }] }],
      data: { reason: 'escalation' },
    }
    const modifiedGreeting = {
      ...VALID_SCRIPT.steps[0],
      fallback_goto: 'staff',
    }
    const result = svc.lint({
      ...VALID_SCRIPT,
      steps: [modifiedGreeting, VALID_SCRIPT.steps[1], fallbackTarget],
    })
    expect(result.errors.some((e) => e.code === 'L006')).toBe(false)
  })

  test('L007: warns about handoff without data.reason', () => {
    const handoffStep = {
      id: 'staff_transfer',
      type: 'handoff',
      variants: [{ id: 'v1', beats: [{ text: 'Chuyển', pause_after: 'turn' }] }],
    }
    const greeting = { ...VALID_SCRIPT.steps[0], fallback_goto: 'staff_transfer', transitions: [{ when: "intent == 'done'", goto: 'farewell' }] }
    const result = svc.lint({
      ...VALID_SCRIPT,
      steps: [greeting, VALID_SCRIPT.steps[1], handoffStep],
    })
    expect(result.warnings.some((w) => w.code === 'L007')).toBe(true)
  })

  test('L007: no warning when handoff has data.reason', () => {
    const handoffStep = {
      id: 'staff_transfer',
      type: 'handoff',
      variants: [{ id: 'v1', beats: [{ text: 'Chuyển', pause_after: 'turn' }] }],
      data: { reason: 'user_escalation' },
    }
    const greeting = { ...VALID_SCRIPT.steps[0], transitions: [{ when: "intent == 'done'", goto: 'farewell' }], fallback_goto: 'staff_transfer' }
    const result = svc.lint({
      ...VALID_SCRIPT,
      steps: [greeting, VALID_SCRIPT.steps[1], handoffStep],
    })
    expect(result.warnings.some((w) => w.code === 'L007')).toBe(false)
  })

  test('L008: rejects more than 50 steps', () => {
    const steps = Array.from({ length: 51 }, (_, i) => ({
      id: `step_${i}`,
      type: 'speak',
      variants: [{ id: 'v1', beats: [{ text: `Step ${i}`, pause_after: 'none' }] }],
    }))
    const result = svc.lint({ ...VALID_SCRIPT, entry_step: 'step_0', steps })
    expect(result.errors.some((e) => e.code === 'L008')).toBe(true)
  })
})
