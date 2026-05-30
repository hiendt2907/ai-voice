import { ValidationPipe, ArgumentMetadata } from '@nestjs/common'
import { UpdateNluDocDto } from './update-nlu-doc.dto'

// Regression: "Gắn đã chọn" NLU gửi PATCH { scriptId }. ValidationPipe whitelist
// strip field không khai báo — DTO thiếu scriptId thì liên kết campaign không ghi.
describe('UpdateNluDocDto', () => {
  const pipe = new ValidationPipe({ whitelist: true, transform: true })
  const meta: ArgumentMetadata = { type: 'body', metatype: UpdateNluDocDto, data: '' }
  const CAMPAIGN_ID = '11111111-1111-4111-8111-111111111111'

  test('retains scriptId so attaching an NLU doc to a campaign persists', async () => {
    const out = (await pipe.transform({ scriptId: CAMPAIGN_ID }, meta)) as UpdateNluDocDto
    expect(out.scriptId).toBe(CAMPAIGN_ID)
  })
})
