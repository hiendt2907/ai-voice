export type CallEventType =
  | 'call.started'
  | 'call.step'
  | 'call.intent'
  | 'call.handoff'
  | 'call.ended'
  | 'call.no_match'
  | 'call.barge_in'

export interface CallEvent {
  event: CallEventType
  call_id: string
  timestamp: string
  session_id: string
  data: Record<string, unknown>
}

export interface CallStepEvent extends CallEvent {
  event: 'call.step'
  data: {
    step_id: string
    variant_id: string
    ttfa_ms: number
  }
}

export interface CallIntentEvent extends CallEvent {
  event: 'call.intent'
  data: {
    step_id: string
    intent: string
    confidence: number
    slots: Record<string, string>
    transcript: string
  }
}

export interface CallHandoffEvent extends CallEvent {
  event: 'call.handoff'
  data: {
    step_id: string
    reason: string
    agent_queue?: string
  }
}
