import { Injectable, NotFoundException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { ConfigService } from '@nestjs/config'
import { NluDocument, NluDocType } from './nlu-document.entity'
import { CreateNluDocDto } from './dto/create-nlu-doc.dto'
import { UpdateNluDocDto } from './dto/update-nlu-doc.dto'

@Injectable()
export class NluService {
  private readonly voiceWorkerUrl: string

  constructor(
    @InjectRepository(NluDocument)
    private readonly repo: Repository<NluDocument>,
    private readonly config: ConfigService,
  ) {
    this.voiceWorkerUrl = this.config.get<string>('VOICE_WORKER_URL', 'http://localhost:8000')
  }

  list(type?: NluDocType, campaignId?: string, activeOnly = true, scriptId?: string) {
    const qb = this.repo.createQueryBuilder('d').orderBy('d.type').addOrderBy('d.label').addOrderBy('d.createdAt', 'DESC')
    if (activeOnly) qb.andWhere('d.isActive = true')
    if (type) qb.andWhere('d.type = :type', { type })
    if (scriptId) qb.andWhere('d.scriptId = :scriptId', { scriptId })
    else if (campaignId) qb.andWhere('(d.campaignId = :campaignId OR d.campaignId IS NULL)', { campaignId })
    return qb.getMany()
  }

  async get(id: string): Promise<NluDocument> {
    const doc = await this.repo.findOne({ where: { id } })
    if (!doc) throw new NotFoundException(`NluDocument ${id} not found`)
    return doc
  }

  async create(dto: CreateNluDocDto): Promise<NluDocument> {
    const doc = await this.repo.save(
      this.repo.create({
        type: dto.type,
        label: dto.label,
        content: dto.content,
        meta: dto.meta ?? {},
        campaignId: dto.campaignId ?? null,
        scriptId: dto.scriptId ?? null,
        isActive: dto.isActive ?? true,
      }),
    )
    void this.triggerEmbed(doc.id, doc.content)
    return doc
  }

  async update(id: string, dto: UpdateNluDocDto): Promise<NluDocument> {
    const doc = await this.get(id)
    const updated = await this.repo.save({ ...doc, ...dto })
    if (dto.content && dto.content !== doc.content) {
      void this.triggerEmbed(id, dto.content)
    }
    return updated
  }

  async remove(id: string): Promise<void> {
    const doc = await this.get(id)
    await this.repo.remove(doc)
  }

  async updateEmbedding(id: string, embeddingJson: string): Promise<{ ok: boolean }> {
    await this.repo.update(id, { embeddingJson })
    return { ok: true }
  }

  /** Export all active documents with embeddings for voice worker NLU store */
  listForExport(campaignId?: string) {
    const qb = this.repo
      .createQueryBuilder('d')
      .where('d.isActive = true')
      .select(['d.id', 'd.type', 'd.label', 'd.content', 'd.meta', 'd.embeddingJson', 'd.campaignId', 'd.scriptId'])
    if (campaignId) qb.andWhere('(d.campaignId = :campaignId OR d.campaignId IS NULL)', { campaignId })
    return qb.getMany()
  }

  private async triggerEmbed(docId: string, content: string): Promise<void> {
    try {
      await fetch(`${this.voiceWorkerUrl}/nlu/embed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, content }),
      })
    } catch {
      // Non-fatal — doc saved, embedding computed on next store reload
    }
  }
}
