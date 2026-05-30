import { ValidationPipe, ArgumentMetadata } from '@nestjs/common'
import { UpdateArticleDto } from './update-article.dto'

// Regression: "Gắn đã chọn" trong Script CMS gửi PATCH { scriptId }. Với
// ValidationPipe({ whitelist: true }) mọi field không khai báo trong DTO bị
// strip âm thầm — nếu DTO thiếu scriptId thì liên kết campaign không bao giờ ghi.
describe('UpdateArticleDto', () => {
  const pipe = new ValidationPipe({ whitelist: true, transform: true })
  const meta: ArgumentMetadata = { type: 'body', metatype: UpdateArticleDto, data: '' }
  const CAMPAIGN_ID = '11111111-1111-4111-8111-111111111111'

  test('retains scriptId so attaching a KB article to a campaign persists', async () => {
    const out = (await pipe.transform({ scriptId: CAMPAIGN_ID }, meta)) as UpdateArticleDto
    expect(out.scriptId).toBe(CAMPAIGN_ID)
  })

  test('still strips unknown fields', async () => {
    const out = (await pipe.transform(
      { scriptId: CAMPAIGN_ID, bogus: 'x' },
      meta,
    )) as Record<string, unknown>
    expect(out.bogus).toBeUndefined()
  })
})
