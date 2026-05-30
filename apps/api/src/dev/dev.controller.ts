import { Controller, Post, HttpCode } from '@nestjs/common'
import { InjectDataSource } from '@nestjs/typeorm'
import { DataSource } from 'typeorm'
import * as bcrypt from 'bcrypt'
import { KnowledgeService } from '../knowledge/knowledge.service'
import { NluService } from '../nlu/nlu.service'
import { NLU_SEED_DOCS } from '../nlu/nlu.seed'

const KB_ARTICLES = [
  {
    title: 'Nội soi có đau không?',
    category: 'noi_soi',
    tags: ['noi_soi', 'an_toan', 'tieu_hoa'],
    questionVariants: [
      'nội soi có đau không',
      'làm nội soi có đau không',
      'nội soi dạ dày có đau không',
      'nội soi đau lắm không',
      'nội soi đại tràng có đau không',
    ],
    answerText:
      'Dạ không ạ. DoctorCheck dùng thuốc an thần tiêm tĩnh mạch, bạn sẽ ngủ nhẹ trong suốt quá trình nội soi, hoàn toàn không cảm thấy khó chịu ạ.',
    answerMale:
      'Dạ không ạ. DoctorCheck dùng thuốc an thần tiêm tĩnh mạch, anh sẽ ngủ nhẹ trong suốt quá trình nội soi, hoàn toàn không cảm thấy khó chịu ạ.',
    answerFemale:
      'Dạ không ạ. DoctorCheck dùng thuốc an thần tiêm tĩnh mạch, chị sẽ ngủ nhẹ trong suốt quá trình nội soi, hoàn toàn không cảm thấy khó chịu ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Nhịn ăn bao lâu trước nội soi dạ dày?',
    category: 'noi_soi',
    tags: ['noi_soi', 'chuan_bi', 'da_day'],
    questionVariants: [
      'nhịn ăn bao lâu trước nội soi',
      'nhịn ăn mấy tiếng trước nội soi dạ dày',
      'cần nhịn ăn bao lâu',
      'trước nội soi cần nhịn ăn mấy tiếng',
      'trước khi nội soi dạ dày cần làm gì',
      'chuẩn bị nội soi dạ dày như thế nào',
    ],
    answerText:
      'Dạ trước nội soi dạ dày bạn cần nhịn ăn ít nhất 6-8 tiếng ạ. Không hút thuốc, không uống rượu bia. Được uống nước lọc đến 2 tiếng trước giờ nội soi ạ.',
    answerMale:
      'Dạ trước nội soi dạ dày anh cần nhịn ăn ít nhất 6-8 tiếng ạ. Không hút thuốc, không uống rượu bia. Được uống nước lọc đến 2 tiếng trước giờ nội soi ạ.',
    answerFemale:
      'Dạ trước nội soi dạ dày chị cần nhịn ăn ít nhất 6-8 tiếng ạ. Không hút thuốc, không uống rượu bia. Được uống nước lọc đến 2 tiếng trước giờ nội soi ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Nội soi đại tràng chuẩn bị như thế nào?',
    category: 'noi_soi',
    tags: ['noi_soi', 'chuan_bi', 'dai_trang'],
    questionVariants: [
      'nội soi đại tràng chuẩn bị như thế nào',
      'trước nội soi đại tràng cần làm gì',
      'chuẩn bị nội soi đại tràng',
      'nội soi đại tràng có cần uống thuốc không',
      'thuốc xổ ruột nội soi đại tràng',
      'uống thuốc gì trước nội soi đại tràng',
    ],
    answerText:
      'Dạ nội soi đại tràng cần uống thuốc làm sạch ruột trước một ngày ạ. DoctorCheck sẽ hướng dẫn bạn uống thuốc tại nhà ngày hôm trước, kết hợp ăn nhẹ thức ăn lỏng. Phòng khám sẽ gửi hướng dẫn cụ thể sau khi đặt lịch ạ.',
    answerMale:
      'Dạ nội soi đại tràng cần uống thuốc làm sạch ruột trước một ngày ạ. DoctorCheck sẽ hướng dẫn anh uống thuốc tại nhà ngày hôm trước, kết hợp ăn nhẹ thức ăn lỏng. Phòng khám sẽ gửi hướng dẫn cụ thể sau khi đặt lịch ạ.',
    answerFemale:
      'Dạ nội soi đại tràng cần uống thuốc làm sạch ruột trước một ngày ạ. DoctorCheck sẽ hướng dẫn chị uống thuốc tại nhà ngày hôm trước, kết hợp ăn nhẹ thức ăn lỏng. Phòng khám sẽ gửi hướng dẫn cụ thể sau khi đặt lịch ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Giá nội soi dạ dày bao nhiêu?',
    category: 'noi_soi',
    tags: ['noi_soi', 'gia', 'da_day'],
    questionVariants: [
      'giá nội soi dạ dày',
      'nội soi dạ dày bao nhiêu tiền',
      'chi phí nội soi dạ dày',
      'phí nội soi dạ dày',
      'giá gói nội soi dạ dày',
      'nội soi dạ dày giá bao nhiêu',
    ],
    answerText:
      'Dạ gói nội soi dạ dày có gây mê tại DoctorCheck là 3.100.000 đồng, trọn gói không phát sinh thêm ạ. Đã bao gồm thuốc an thần và đọc kết quả cùng bác sĩ ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Giá nội soi đại tràng bao nhiêu?',
    category: 'noi_soi',
    tags: ['noi_soi', 'gia', 'dai_trang'],
    questionVariants: [
      'giá nội soi đại tràng',
      'nội soi đại tràng bao nhiêu tiền',
      'chi phí nội soi đại tràng',
      'phí nội soi đại tràng',
      'giá gói nội soi đại tràng',
      'nội soi đại tràng giá bao nhiêu',
    ],
    answerText:
      'Dạ gói nội soi đại tràng có gây mê tại DoctorCheck là 4.100.000 đồng trọn gói ạ. Đã bao gồm thuốc an thần, thuốc xổ ruột và đọc kết quả cùng bác sĩ ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Nội soi combo dạ dày và đại tràng giá bao nhiêu?',
    category: 'noi_soi',
    tags: ['noi_soi', 'gia', 'combo'],
    questionVariants: [
      'nội soi cả hai giá bao nhiêu',
      'nội soi dạ dày và đại tràng combo',
      'giá combo nội soi',
      'nội soi kết hợp giá bao nhiêu',
      'nội soi cả dạ dày và đại tràng bao nhiêu tiền',
      'gói nội soi kết hợp giá bao nhiêu',
    ],
    answerText:
      'Dạ gói nội soi kết hợp dạ dày và đại tràng cùng lúc tại DoctorCheck là 6.500.000 đồng ạ. Thực hiện trong cùng một lần gây mê, tiết kiệm thời gian hơn làm riêng lẻ ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Nội soi mất bao lâu?',
    category: 'noi_soi',
    tags: ['noi_soi', 'thoi_gian'],
    questionVariants: [
      'nội soi mất bao lâu',
      'nội soi dạ dày mất bao lâu',
      'thời gian nội soi',
      'nội soi xong bao giờ về được',
      'mất bao nhiêu thời gian để nội soi',
      'nội soi khoảng mấy tiếng',
    ],
    answerText:
      'Dạ toàn bộ quy trình từ đăng ký đến nhận kết quả khoảng 90-120 phút ạ. Riêng thủ thuật nội soi khoảng 20 phút, bác sĩ quan sát tối thiểu 7 phút để đảm bảo không bỏ sót tổn thương ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Nội soi có cần người nhà đi cùng không?',
    category: 'noi_soi',
    tags: ['noi_soi', 'luu_y'],
    questionVariants: [
      'nội soi có cần người nhà không',
      'cần người đi kèm không',
      'sau nội soi có tự về được không',
      'có cần đưa đón không',
      'sau nội soi có lái xe được không',
    ],
    answerText:
      'Dạ do có dùng thuốc an thần, bạn nên có người nhà đi cùng để đưa về sau nội soi ạ. Sau gây mê khoảng 30-60 phút bạn sẽ tỉnh hoàn toàn, nhưng khuyến cáo không tự lái xe trong ngày ạ.',
    answerMale:
      'Dạ do có dùng thuốc an thần, anh nên có người nhà đi cùng để đưa về sau nội soi ạ. Sau gây mê khoảng 30-60 phút anh sẽ tỉnh hoàn toàn, nhưng khuyến cáo không tự lái xe trong ngày ạ.',
    answerFemale:
      'Dạ do có dùng thuốc an thần, chị nên có người nhà đi cùng để đưa về sau nội soi ạ. Sau gây mê khoảng 30-60 phút chị sẽ tỉnh hoàn toàn, nhưng khuyến cáo không tự lái xe trong ngày ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Nội soi có phát hiện ung thư không?',
    category: 'noi_soi',
    tags: ['noi_soi', 'ung_thu', 'tam_soat'],
    questionVariants: [
      'nội soi có phát hiện ung thư không',
      'nội soi tầm soát ung thư',
      'nội soi dạ dày có phát hiện ung thư dạ dày không',
      'kiểm tra ung thư bằng nội soi',
      'nội soi phát hiện được bệnh gì',
    ],
    answerText:
      'Dạ nội soi là phương pháp hiệu quả nhất để phát hiện sớm ung thư dạ dày và đại tràng ạ. Bác sĩ có thể sinh thiết ngay trong quá trình nội soi nếu phát hiện tổn thương bất thường ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Sau nội soi có ăn được ngay không?',
    category: 'noi_soi',
    tags: ['noi_soi', 'sau_noi_soi', 'luu_y'],
    questionVariants: [
      'sau nội soi ăn gì được',
      'sau nội soi bao lâu ăn được',
      'sau nội soi có hạn chế ăn uống không',
      'sau nội soi dạ dày có ăn được không',
      'sau nội soi có được ăn không',
    ],
    answerText:
      'Dạ sau nội soi dạ dày khoảng 1-2 tiếng khi hết tác dụng thuốc an thần, bạn có thể ăn uống nhẹ ạ. Nên ăn thức ăn mềm, tránh thức ăn cay và rượu bia trong ngày đầu ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'DoctorCheck có chấp nhận bảo hiểm không?',
    category: 'noi_soi',
    tags: ['noi_soi', 'bao_hiem'],
    questionVariants: [
      'có bảo hiểm không',
      'bảo hiểm y tế được không',
      'bhyt có được không',
      'nội soi có dùng bảo hiểm được không',
      'bảo hiểm nội soi',
    ],
    answerText:
      'Dạ hiện DoctorCheck chưa liên kết với bảo hiểm y tế nhà nước ạ. Tuy nhiên một số bảo hiểm sức khỏe tư nhân có thể hoàn tiền, bạn kiểm tra với nhà bảo hiểm để biết thêm chi tiết nhé ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Kết quả nội soi nhận khi nào?',
    category: 'noi_soi',
    tags: ['noi_soi', 'ket_qua'],
    questionVariants: [
      'kết quả nội soi bao giờ có',
      'kết quả nhận khi nào',
      'kết quả nội soi trả lúc nào',
      'bao lâu có kết quả nội soi',
      'kết quả nội soi trả khi nào',
    ],
    answerText:
      'Dạ kết quả nội soi cơ bản sẽ được bác sĩ trả và đọc ngay sau thủ thuật ạ. Nếu có sinh thiết thì kết quả mô bệnh học sẽ có sau 3-5 ngày làm việc, phòng khám sẽ thông báo qua điện thoại ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Nội soi có nguy hiểm không?',
    category: 'noi_soi',
    tags: ['noi_soi', 'an_toan', 'bien_chung'],
    questionVariants: [
      'nội soi có nguy hiểm không',
      'nội soi an toàn không',
      'nội soi có biến chứng không',
      'nội soi có rủi ro không',
      'nội soi có tác dụng phụ không',
    ],
    answerText:
      'Dạ nội soi là thủ thuật an toàn, được thực hiện bởi bác sĩ chuyên khoa có kinh nghiệm ạ. Tỷ lệ biến chứng rất thấp, dưới 0,1% ạ. DoctorCheck sử dụng ống soi HD thế hệ mới và quy trình khử khuẩn đạt chuẩn ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Nội soi được thực hiện vào khung giờ nào?',
    category: 'noi_soi',
    tags: ['noi_soi', 'gio_lam_viec'],
    questionVariants: [
      'có khám buổi chiều không',
      'nội soi buổi chiều có không',
      'mấy giờ nội soi được',
      'giờ làm việc nội soi',
      'nội soi từ mấy giờ',
      'khung giờ nội soi',
    ],
    answerText:
      'Dạ DoctorCheck thực hiện nội soi cả buổi sáng và buổi chiều ạ. Buổi sáng từ 7 giờ 30, buổi chiều từ 13 giờ 30 ạ. Lưu ý nội soi dạ dày buổi chiều bạn cần nhịn ăn từ sáng sớm nhé ạ.',
    confidenceThreshold: 0.65,
  },
  {
    title: 'Tần suất nội soi định kỳ bao lâu một lần?',
    category: 'noi_soi',
    tags: ['noi_soi', 'dinh_ky'],
    questionVariants: [
      'đã nội soi rồi có cần nội soi lại không',
      'bao lâu nội soi một lần',
      'tần suất nội soi định kỳ',
      'năm nay nội soi rồi năm sau có cần nội soi nữa không',
      'nội soi bao nhiêu năm một lần',
    ],
    answerText:
      'Dạ nếu kết quả bình thường, thông thường nội soi định kỳ mỗi 2-3 năm một lần ạ. Nếu có polyp hoặc tổn thương, bác sĩ sẽ khuyến cáo tái khám sớm hơn ạ. Bạn có thể mang kết quả cũ để bác sĩ đánh giá ạ.',
    confidenceThreshold: 0.65,
  },
]

const SEED_USERS = [
  { email: 'admin@doctorcheck.vn', password: 'Admin@2024!', fullName: 'Admin', role: 'admin' },
  { email: 'operator@doctorcheck.vn', password: 'Operator@2024!', fullName: 'Operator', role: 'operator' },
  { email: 'qa@doctorcheck.vn', password: 'Qa@2024!', fullName: 'QA Reviewer', role: 'qa' },
  { email: 'viewer@doctorcheck.vn', password: 'Viewer@2024!', fullName: 'Viewer', role: 'viewer' },
]

@Controller('dev')
export class DevController {
  constructor(
    @InjectDataSource() private readonly ds: DataSource,
    private readonly knowledge: KnowledgeService,
    private readonly nlu: NluService,
  ) {}

  @Post('seed')
  @HttpCode(200)
  async seed() {
    const userResults: { email: string; created: boolean }[] = []

    // Seed users
    for (const u of SEED_USERS) {
      const existing = await this.ds.query<{ id: string }[]>(
        'SELECT id FROM users WHERE email = $1',
        [u.email],
      )
      if (existing.length > 0) {
        userResults.push({ email: u.email, created: false })
        continue
      }
      const hash = await bcrypt.hash(u.password, 12)
      await this.ds.query(
        `INSERT INTO users (id, email, "passwordHash", "fullName", role, "isActive", "createdAt", "updatedAt")
         VALUES (gen_random_uuid(), $1, $2, $3, $4, true, now(), now())`,
        [u.email, hash, u.fullName, u.role],
      )
      userResults.push({ email: u.email, created: true })
    }

    const adminRows = await this.ds.query<{ id: string; email: string }[]>(
      `SELECT id, email FROM users WHERE email = $1`,
      ['admin@doctorcheck.vn'],
    )
    const adminId = adminRows[0]?.id
    const adminEmail = adminRows[0]?.email ?? 'admin@doctorcheck.vn'

    // Seed sample campaign + versions
    let campaignId: string | null = null
    const existingCampaign = await this.ds.query<{ id: string }[]>(
      `SELECT id FROM campaigns WHERE name = $1`,
      ['Booking Inbound'],
    )
    if (existingCampaign.length > 0) {
      campaignId = existingCampaign[0].id
    } else if (adminId) {
      const rows = await this.ds.query<{ id: string }[]>(
        `INSERT INTO campaigns (id, name, direction, "voiceProfile", "isActive", "createdAt", "updatedAt")
         VALUES (gen_random_uuid(), $1, $2, $3, false, now(), now()) RETURNING id`,
        ['Booking Inbound', 'inbound', 'linh_clone_v1'],
      )
      campaignId = rows[0]?.id ?? null
    }

    // Seed an unscored call session for QA queue
    const existingUnscored = await this.ds.query<{ id: string }[]>(
      `SELECT id FROM call_sessions WHERE "sessionId" = $1`,
      ['sess-demo-002'],
    )
    let unscoredCallId: string | null = null
    if (existingUnscored.length === 0 && campaignId) {
      const rows = await this.ds.query<{ id: string }[]>(
        `INSERT INTO call_sessions (id, "sessionId", "campaignId", direction, "callerNumberMasked", status, transcript, "durationSeconds", "endedAt", "createdAt", "updatedAt")
         VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6::jsonb, $7, now() - interval '2 hours', now() - interval '2 hours', now() - interval '2 hours') RETURNING id`,
        [
          'sess-demo-002',
          campaignId,
          'inbound',
          '091****234',
          'completed',
          JSON.stringify([
            { role: 'agent', text: 'Xin chào, đây là hệ thống đặt lịch DoctorCheck', stepId: 'greeting' },
            { role: 'caller', text: 'Tôi muốn đặt lịch khám ngày mai' },
            { role: 'agent', text: 'Bạn muốn đặt khám vào khung giờ nào?', stepId: 'ask_time' },
            { role: 'caller', text: 'Buổi sáng 9 giờ' },
            { role: 'agent', text: 'Đã ghi nhận. Xin cảm ơn!', stepId: 'confirm' },
          ]),
          95,
        ],
      )
      unscoredCallId = rows[0]?.id ?? null
    }

    // Seed learning proposals
    const existingProposal = await this.ds.query<{ id: string }[]>(
      `SELECT id FROM learning_proposals WHERE type = $1 AND status = $2 LIMIT 1`,
      ['new_intent_example', 'pending'],
    )
    let proposalCreated = false
    if (existingProposal.length === 0 && unscoredCallId) {
      await this.ds.query(
        `INSERT INTO learning_proposals (id, "callSessionId", type, payload, status, "createdAt", "updatedAt")
         VALUES (gen_random_uuid(), $1, $2, $3::jsonb, $4, now() - interval '1 hour', now() - interval '1 hour')`,
        [
          unscoredCallId,
          'new_intent_example',
          JSON.stringify({
            stepId: 'ask_time',
            intentName: 'book_appointment_morning',
            suggestedExamples: ['sáng sớm 8 giờ', 'khoảng 9 giờ sáng', 'buổi sáng'],
            campaignId,
          }),
          'pending',
        ],
      )
      proposalCreated = true
    }

    // Seed sample audit events
    const existingAudit = await this.ds.query<{ id: string }[]>(
      `SELECT id FROM audit_events WHERE action = $1 LIMIT 1`,
      ['seed.init'],
    )
    let auditSeeded = false
    if (existingAudit.length === 0 && adminId && campaignId) {
      const events = [
        { actorId: adminId, actorEmail: adminEmail, action: 'seed.init', entity: 'system', entityId: null, diff: { after: { note: 'Initial seed' } } },
        { actorId: adminId, actorEmail: adminEmail, action: 'create', entity: 'campaign', entityId: campaignId, diff: { after: { name: 'Booking Inbound' } } },
        { actorId: adminId, actorEmail: adminEmail, action: 'publish', entity: 'script_version', entityId: campaignId, diff: { after: { version: '1.0.0', campaignId } } },
        { actorId: adminId, actorEmail: adminEmail, action: 'update', entity: 'cloudfone_settings', entityId: 'default', diff: { after: { odsUrl: 'ws://mock-ods:8080', tenantId: 'doctorcheck' } } },
      ]
      for (const e of events) {
        await this.ds.query(
          `INSERT INTO audit_events (id, "actorId", "actorEmail", action, entity, "entityId", diff, "createdAt")
           VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6::jsonb, now() - interval '${Math.floor(Math.random() * 24)} hours')`,
          [e.actorId, e.actorEmail, e.action, e.entity, e.entityId, JSON.stringify(e.diff)],
        )
      }
      auditSeeded = true
    }

    // Seed KB articles for nội soi
    const kbResults: { title: string; created: boolean }[] = []
    for (const article of KB_ARTICLES) {
      const existing = await this.ds.query<{ id: string }[]>(
        `SELECT id FROM knowledge_articles WHERE title = $1`,
        [article.title],
      )
      if (existing.length > 0) {
        kbResults.push({ title: article.title, created: false })
        continue
      }
      await this.knowledge.create({
        title: article.title,
        category: article.category,
        tags: article.tags,
        questionVariants: article.questionVariants,
        answerText: article.answerText,
        answerMale: article.answerMale,
        answerFemale: article.answerFemale,
        confidenceThreshold: article.confidenceThreshold,
      })
      kbResults.push({ title: article.title, created: true })
    }

    // Seed NLU documents (fillers + intent examples)
    const nluResults: { content: string; created: boolean }[] = []
    for (const doc of NLU_SEED_DOCS) {
      const existing = await this.ds.query<{ id: string }[]>(
        `SELECT id FROM nlu_documents WHERE type = $1 AND label = $2 AND content = $3`,
        [doc.type, doc.label, doc.content],
      )
      if (existing.length > 0) {
        nluResults.push({ content: doc.content.slice(0, 40), created: false })
        continue
      }
      await this.nlu.create(doc)
      nluResults.push({ content: doc.content.slice(0, 40), created: true })
    }

    return {
      users: userResults,
      campaign: campaignId ? 'exists' : 'not created',
      unscoredCall: unscoredCallId ? 'created' : 'exists',
      proposal: proposalCreated ? 'created' : 'exists',
      auditEvents: auditSeeded ? 'seeded 4 events' : 'already exist',
      kbArticles: kbResults,
      nluDocs: { total: NLU_SEED_DOCS.length, created: nluResults.filter((r) => r.created).length },
    }
  }

  @Post('wipe')
  @HttpCode(200)
  async wipe() {
    if (process.env.NODE_ENV === 'production') {
      return { error: 'Not allowed in production' }
    }

    const counts = await Promise.all([
      this.ds.query<{ count: string }[]>('SELECT COUNT(*)::int AS count FROM knowledge_articles'),
      this.ds.query<{ count: string }[]>('SELECT COUNT(*)::int AS count FROM nlu_documents'),
      this.ds.query<{ count: string }[]>('SELECT COUNT(*)::int AS count FROM script_versions'),
      this.ds.query<{ count: string }[]>('SELECT COUNT(*)::int AS count FROM campaigns'),
    ])

    await this.ds.query('DELETE FROM knowledge_articles')
    await this.ds.query('DELETE FROM nlu_documents')
    await this.ds.query('DELETE FROM hotline_routes')
    await this.ds.query('DELETE FROM script_versions')
    await this.ds.query('DELETE FROM campaigns')

    return {
      wiped: {
        knowledgeArticles: Number(counts[0][0].count),
        nluDocuments: Number(counts[1][0].count),
        scriptVersions: Number(counts[2][0].count),
        campaigns: Number(counts[3][0].count),
      },
    }
  }
}
