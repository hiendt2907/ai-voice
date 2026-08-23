import { Injectable, NotFoundException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { KnowledgeArticle } from './knowledge-article.entity'
import { CreateArticleDto } from './dto/create-article.dto'
import { UpdateArticleDto } from './dto/update-article.dto'
import { VoiceWorkerUrlResolver } from '../common/voice-worker-url.resolver'

@Injectable()
export class KnowledgeService {
  constructor(
    @InjectRepository(KnowledgeArticle)
    private readonly repo: Repository<KnowledgeArticle>,
    private readonly voiceWorkerUrlResolver: VoiceWorkerUrlResolver,
  ) {}

  list(category?: string, activeOnly = true) {
    const qb = this.repo.createQueryBuilder('a').orderBy('a.createdAt', 'DESC')
    if (activeOnly) qb.andWhere('a.isActive = true')
    if (category) qb.andWhere('a.category = :category', { category })
    return qb.getMany()
  }

  async get(id: string): Promise<KnowledgeArticle> {
    const article = await this.repo.findOne({ where: { id } })
    if (!article) throw new NotFoundException(`Article ${id} not found`)
    return article
  }

  async create(dto: CreateArticleDto, actorId?: string): Promise<KnowledgeArticle> {
    const article = await this.repo.save(
      this.repo.create({
        title: dto.title,
        category: dto.category ?? null,
        tags: dto.tags ?? [],
        questionVariants: dto.questionVariants,
        answerText: dto.answerText,
        answerMale: dto.answerMale ?? null,
        answerFemale: dto.answerFemale ?? null,
        confidenceThreshold: dto.confidenceThreshold ?? 0.82,
        scriptId: dto.scriptId ?? null,
        createdBy: actorId ?? null,
        updatedBy: actorId ?? null,
      }),
    )
    // A brand-new article isn't in the voice worker's in-memory store yet —
    // upsert_embedding() only replaces an ID it already knows, never
    // inserts. Full reload is the only way it goes live immediately.
    void this.triggerReload()
    return article
  }

  async update(id: string, dto: UpdateArticleDto, actorId?: string): Promise<KnowledgeArticle> {
    const article = await this.get(id)
    const updated = await this.repo.save({ ...article, ...dto, updatedBy: actorId ?? article.updatedBy })
    if (dto.questionVariants) {
      void this.triggerEmbed(id, dto.questionVariants)
    }
    return updated
  }

  async remove(id: string): Promise<void> {
    const article = await this.get(id)
    await this.repo.remove(article)
    void this.triggerReload()
  }

  async updateEmbedding(id: string, embeddingJson: string): Promise<{ ok: boolean }> {
    await this.repo.update(id, { embeddingJson })
    return { ok: true }
  }

  /**
   * Returns active articles with embeddings for RAG search in voice worker.
   * When campaignId is provided, scopes to that campaign (KnowledgeArticle.scriptId
   * stores the campaign UUID). Omitting it keeps the legacy all-campaigns behavior.
   */
  listForRag(campaignId?: string) {
    return this.repo.find({
      where: { isActive: true, ...(campaignId ? { scriptId: campaignId } : {}) },
      select: ['id', 'title', 'answerText', 'answerMale', 'answerFemale', 'embeddingJson', 'confidenceThreshold', 'category', 'tags', 'scriptId'],
    })
  }

  async testSearch(query: string, limit = 3): Promise<unknown> {
    try {
      const base = await this.voiceWorkerUrlResolver.resolve()
      const res = await fetch(`${base}/rag/test-search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit }),
        signal: AbortSignal.timeout(10000),
      })
      if (!res.ok) return { error: `Voice worker HTTP ${res.status}` }
      return res.json()
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'Voice worker unavailable' }
    }
  }

  private async triggerEmbed(articleId: string, texts: string[]): Promise<void> {
    try {
      const base = await this.voiceWorkerUrlResolver.resolve()
      await fetch(`${base}/rag/embed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ article_id: articleId, texts }),
      })
    } catch {
      // Non-fatal — article saved, embedding will retry on next reload
    }
  }

  private async triggerReload(): Promise<void> {
    try {
      const base = await this.voiceWorkerUrlResolver.resolve()
      await fetch(`${base}/rag/reload`, { method: 'POST' })
    } catch {
      // Non-fatal — article saved, will be picked up on the next reload anyway
    }
  }
}
