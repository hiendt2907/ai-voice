import { Entity, PrimaryGeneratedColumn, Column, CreateDateColumn, UpdateDateColumn, Index } from 'typeorm'

export type NluDocType = 'intent' | 'filler' | 'reprompt' | 'dialog_node'

@Entity('nlu_documents')
@Index(['type', 'isActive'])
@Index(['campaignId', 'type'])
export class NluDocument {
  @PrimaryGeneratedColumn('uuid')
  id: string

  /** Discriminator: intent | filler | reprompt | dialog_node */
  @Column({ type: 'varchar', length: 50 })
  type: NluDocType

  /**
   * Semantic label per type:
   *  intent      → intent name, e.g. "book_appointment"
   *  filler      → context key, e.g. "thinking" | "ack" | "wait" | ...
   *  reprompt    → step_id this reprompt belongs to
   *  dialog_node → step_id
   */
  @Column({ type: 'varchar', length: 255 })
  label: string

  /**
   * The actual text content — this is what gets embedded:
   *  intent      → example utterance, e.g. "muốn đặt lịch khám"
   *  filler      → filler phrase, e.g. "Dạ,"
   *  reprompt    → reprompt text
   *  dialog_node → step trigger description / canonical question
   */
  @Column({ type: 'text' })
  content: string

  /**
   * Type-specific extra data:
   *  intent:      { slots?: Record<string, string> } — pre-set slot values
   *  reprompt:    { order?: number }
   *  dialog_node: { slots_required?: string[] }
   *  filler:      {}
   */
  @Column({ type: 'jsonb', nullable: true, default: {} })
  meta: Record<string, unknown>

  /** Embedding of content field — stored as JSON "[0.1, ...]" (dim=384, paraphrase-multilingual-MiniLM-L12-v2) */
  @Column({ type: 'text', nullable: true })
  embeddingJson: string | null

  /** Scope to a specific campaign. Null = global (applies to all campaigns) */
  @Column({ type: 'uuid', nullable: true })
  campaignId: string | null

  /** Scope to a specific script (used by reprompt + dialog_node types) */
  @Column({ type: 'uuid', nullable: true })
  scriptId: string | null

  @Column({ type: 'boolean', default: true })
  isActive: boolean

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
