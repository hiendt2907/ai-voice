import { Test, TestingModule } from '@nestjs/testing'
import { getRepositoryToken } from '@nestjs/typeorm'
import { ConfigService } from '@nestjs/config'
import { Repository } from 'typeorm'
import { KnowledgeService } from './knowledge.service'
import { KnowledgeArticle } from './knowledge-article.entity'

/**
 * Part A — RAG export scoping.
 * listForRag(campaignId) must filter by campaign so campaign A never pulls
 * campaign B's articles. KnowledgeArticle.scriptId stores the campaign UUID.
 */
describe('KnowledgeService.listForRag', () => {
  let service: KnowledgeService
  let repo: jest.Mocked<Pick<Repository<KnowledgeArticle>, 'find'>>

  const CAMPAIGN_A = '11111111-1111-1111-1111-111111111111'
  const CAMPAIGN_B = '22222222-2222-2222-2222-222222222222'

  beforeEach(async () => {
    repo = { find: jest.fn().mockResolvedValue([]) }

    const moduleRef: TestingModule = await Test.createTestingModule({
      providers: [
        KnowledgeService,
        { provide: getRepositoryToken(KnowledgeArticle), useValue: repo },
        { provide: ConfigService, useValue: { get: () => 'http://localhost:8001' } },
      ],
    }).compile()

    service = moduleRef.get(KnowledgeService)
  })

  it('scopes the query to the given campaign (scriptId === campaignId)', async () => {
    await service.listForRag(CAMPAIGN_A)

    expect(repo.find).toHaveBeenCalledTimes(1)
    const arg = repo.find.mock.calls[0][0]
    expect(arg?.where).toMatchObject({ isActive: true, scriptId: CAMPAIGN_A })
  })

  it('does not pull another campaign — where.scriptId is the requested campaign only', async () => {
    await service.listForRag(CAMPAIGN_B)

    const arg = repo.find.mock.calls[0][0]
    expect(arg?.where).toMatchObject({ scriptId: CAMPAIGN_B })
    expect(arg?.where).not.toMatchObject({ scriptId: CAMPAIGN_A })
  })

  it('keeps legacy all-campaigns behavior when no campaignId is given', async () => {
    await service.listForRag()

    const arg = repo.find.mock.calls[0][0]
    expect(arg?.where).toEqual({ isActive: true })
    expect(arg?.where).not.toHaveProperty('scriptId')
  })
})
