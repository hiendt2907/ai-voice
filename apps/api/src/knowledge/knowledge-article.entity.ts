import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  Index,
} from 'typeorm'

@Entity('knowledge_articles')
@Index(['isActive', 'category'])
export class KnowledgeArticle {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column({ type: 'varchar', length: 255 })
  title: string

  @Column({ type: 'varchar', length: 100, nullable: true })
  category: string | null

  @Column('simple-array', { nullable: true })
  tags: string[]

  /** Example questions used to compute embedding */
  @Column('simple-array', { nullable: true })
  questionVariants: string[]

  /** TTS-ready base answer — use {{pronoun}} for anh/chị */
  @Column({ type: 'text' })
  answerText: string

  /** Override for male caller */
  @Column({ type: 'text', nullable: true })
  answerMale: string | null

  /** Override for female caller */
  @Column({ type: 'text', nullable: true })
  answerFemale: string | null

  /** Vector stored as JSON string "[0.1, 0.2, ...]" — set by voice worker */
  @Column({ type: 'text', nullable: true })
  embeddingJson: string | null

  @Column({ type: 'float', default: 0.82 })
  confidenceThreshold: number

  /** Scope to a specific script. Null = global */
  @Column({ type: 'uuid', nullable: true })
  scriptId: string | null

  @Column({ type: 'boolean', default: true })
  isActive: boolean

  @Column({ type: 'varchar', nullable: true })
  createdBy: string | null

  @Column({ type: 'varchar', nullable: true })
  updatedBy: string | null

  @CreateDateColumn()
  createdAt: Date

  @UpdateDateColumn()
  updatedAt: Date
}
