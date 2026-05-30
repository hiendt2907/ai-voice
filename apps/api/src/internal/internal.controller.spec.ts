import { Test, TestingModule } from '@nestjs/testing'
import { InternalController } from './internal.controller'
import { CallsService } from '../calls/calls.service'
import { CallbacksService } from '../callbacks/callbacks.service'
import { SettingsService } from '../settings/settings.service'
import { KnowledgeService } from '../knowledge/knowledge.service'
import { LearningService } from '../learning/learning.service'
import { NluService } from '../nlu/nlu.service'

/**
 * Part A — the export endpoints must forward campaignId down to the services
 * so the voice worker can scope KB/NLU per campaign.
 */
describe('InternalController export scoping', () => {
  let controller: InternalController
  const knowledgeService = { listForRag: jest.fn().mockResolvedValue([]) }
  const nluService = { listForExport: jest.fn().mockResolvedValue([]) }

  const CAMPAIGN = '33333333-3333-3333-3333-333333333333'

  beforeEach(async () => {
    jest.clearAllMocks()
    const moduleRef: TestingModule = await Test.createTestingModule({
      controllers: [InternalController],
      providers: [
        { provide: CallsService, useValue: {} },
        { provide: CallbacksService, useValue: {} },
        { provide: SettingsService, useValue: {} },
        { provide: KnowledgeService, useValue: knowledgeService },
        { provide: LearningService, useValue: {} },
        { provide: NluService, useValue: nluService },
      ],
    }).compile()

    controller = moduleRef.get(InternalController)
  })

  it('forwards campaignId to KnowledgeService.listForRag', () => {
    controller.ragExport(CAMPAIGN)
    expect(knowledgeService.listForRag).toHaveBeenCalledWith(CAMPAIGN)
  })

  it('passes undefined to listForRag when no campaignId (legacy behavior)', () => {
    controller.ragExport()
    expect(knowledgeService.listForRag).toHaveBeenCalledWith(undefined)
  })

  it('forwards campaignId to NluService.listForExport', () => {
    controller.nluExport(CAMPAIGN)
    expect(nluService.listForExport).toHaveBeenCalledWith(CAMPAIGN)
  })
})
