/**
 * DoctorCheck seed data — sourced from doctorcheck.vn
 * All factual content verified against the live website.
 * DO NOT add logic here — pure data definitions only.
 */

export interface ArticleDef {
  title: string
  category: string
  tags: string[]
  questionVariants: string[]
  answerText: string
  answerMale?: string
  answerFemale?: string
  confidenceThreshold?: number
}

export interface NluDocDef {
  type: 'intent' | 'filler' | 'reprompt'
  label: string
  content: string
  meta?: Record<string, unknown>
}

export interface CampaignDef {
  name: string
  direction: 'inbound' | 'outbound'
  voiceProfile: string
  scriptVersion: string
  scriptBody: Record<string, unknown>
}

// ─── Campaign + Script ────────────────────────────────────────────────────────

export const CAMPAIGN_DEF: CampaignDef = {
  name: 'Đặt lịch khám — DoctorCheck',
  direction: 'inbound',
  voiceProfile: 'linh_clone_v1',
  scriptVersion: '1.0.0',
  scriptBody: {
    type: 'ai_driven',
    execution_mode: 'rag_assisted',
    version: '1.0.0',
    greeting: 'Dạ, Doctor Check xin nghe ạ. Bạn cần hỗ trợ gì ạ?',
    persona: {
      gender_detect: true,
      barge_in: true,
      fillers: ['Dạ vâng ạ', 'Vâng ạ', 'Dạ', 'Dạ để em kiểm tra ạ'],
    },
    rag: {
      enabled: true,
      linkedKbTags: ['general', 'booking', 'pricing', 'services', 'hours', 'insurance', 'preparation', 'doctors', 'endoscopy', 'faq'],
    },
    escalation: {
      telegram: true,
      chat_id: process.env['TELEGRAM_CHAT_ID'] ?? '',
      bot_token: process.env['TELEGRAM_BOT_TOKEN'] ?? '',
      template: '❓ {question}\n📞 Cuộc gọi: {session_id}',
      waiting_message: 'Dạ em đã ghi nhận câu hỏi và sẽ phản hồi anh/chị ngay ạ',
    },
    fallback_message: 'Dạ để em kiểm tra thêm thông tin ạ',
    ragFallbackMessage: 'Dạ em sẽ xem lại và phản hồi anh/chị sớm nhất có thể ạ',
  },
}

// ─── KB Articles ──────────────────────────────────────────────────────────────

export const KB_ARTICLES: ArticleDef[] = [
  // === GENERAL INFO ===
  {
    title: 'Doctor Check là gì?',
    category: 'general',
    tags: ['general'],
    questionVariants: [
      'Doctor Check là gì',
      'phòng khám Doctor Check',
      'DoctorCheck làm gì',
      'trung tâm Doctor Check',
      'giới thiệu về Doctor Check',
      'Doctor Check chuyên về gì',
    ],
    answerText:
      'Dạ Doctor Check là trung tâm tầm soát bệnh chuyên biệt, tập trung phát hiện sớm bệnh tật để giúp bạn sống thọ hơn. Chúng tôi sử dụng thiết bị chẩn đoán đạt chuẩn quốc tế, đội ngũ 7 bác sĩ giàu kinh nghiệm từ các bệnh viện lớn tại TP.HCM ạ.',
  },
  {
    title: 'Địa chỉ Doctor Check',
    category: 'general',
    tags: ['general', 'faq'],
    questionVariants: [
      'địa chỉ Doctor Check',
      'Doctor Check ở đâu',
      'phòng khám ở đâu',
      'địa chỉ phòng khám',
      'địa điểm khám',
      'DoctorCheck nằm ở đâu',
      'đường đến Doctor Check',
    ],
    answerText:
      'Dạ Doctor Check tọa lạc tại 429 Tô Hiến Thành, Phường 14, Quận 10, TP. Hồ Chí Minh ạ.',
  },
  {
    title: 'Giờ làm việc Doctor Check',
    category: 'hours',
    tags: ['general', 'hours'],
    questionVariants: [
      'giờ làm việc',
      'giờ mở cửa',
      'khám mấy giờ',
      'bao giờ mở cửa',
      'giờ khám',
      'phòng khám mở cửa lúc mấy giờ',
      'thứ mấy làm việc',
      'có làm việc cuối tuần không',
      'chủ nhật có khám không',
    ],
    answerText:
      'Dạ Doctor Check làm việc Thứ 2 đến Thứ 7 từ 6:00 đến 15:00, và Chủ nhật từ 7:00 đến 12:00 ạ. Bạn nên đặt lịch trước để được phục vụ tốt nhất nhé ạ.',
    answerMale:
      'Dạ Doctor Check làm việc Thứ 2 đến Thứ 7 từ 6:00 đến 15:00, và Chủ nhật từ 7:00 đến 12:00 ạ. Anh nên đặt lịch trước để được phục vụ tốt nhất nhé ạ.',
    answerFemale:
      'Dạ Doctor Check làm việc Thứ 2 đến Thứ 7 từ 6:00 đến 15:00, và Chủ nhật từ 7:00 đến 12:00 ạ. Chị nên đặt lịch trước để được phục vụ tốt nhất nhé ạ.',
  },
  {
    title: 'Số điện thoại liên hệ Doctor Check',
    category: 'general',
    tags: ['general', 'faq'],
    questionVariants: [
      'số điện thoại Doctor Check',
      'hotline',
      'số liên hệ',
      'gọi cho Doctor Check',
      'điện thoại phòng khám',
      'contact',
    ],
    answerText:
      'Dạ số điện thoại của Doctor Check là 0939 01 01 01 và 031 654 6123 ạ. Ngoài ra bạn có thể email đến songtho@doctorcheck.vn hoặc đặt lịch qua app Doctor Check Member ạ.',
  },

  // === BOOKING ===
  {
    title: 'Cách đặt lịch khám tại Doctor Check',
    category: 'booking',
    tags: ['booking'],
    questionVariants: [
      'đặt lịch khám như thế nào',
      'cách đặt lịch',
      'đặt lịch bằng cách nào',
      'muốn đặt lịch khám',
      'đăng ký khám',
      'book lịch',
      'làm thế nào để đặt lịch',
    ],
    answerText:
      'Dạ bạn có thể đặt lịch qua 3 cách: gọi hotline 0939 01 01 01, đặt trực tuyến trên website doctorcheck.vn, hoặc qua app Doctor Check Member trên điện thoại ạ. Nếu cần em có thể ghi nhận thông tin để đặt lịch luôn cho bạn ạ.',
    answerMale:
      'Dạ anh có thể đặt lịch qua 3 cách: gọi hotline 0939 01 01 01, đặt trực tuyến trên website doctorcheck.vn, hoặc qua app Doctor Check Member ạ. Nếu cần em có thể ghi nhận thông tin để đặt lịch luôn cho anh ạ.',
    answerFemale:
      'Dạ chị có thể đặt lịch qua 3 cách: gọi hotline 0939 01 01 01, đặt trực tuyến trên website doctorcheck.vn, hoặc qua app Doctor Check Member ạ. Nếu cần em có thể ghi nhận thông tin để đặt lịch luôn cho chị ạ.',
  },
  {
    title: 'Cần mang giấy tờ gì khi đến khám',
    category: 'booking',
    tags: ['booking', 'faq'],
    questionVariants: [
      'mang giấy tờ gì',
      'cần mang gì',
      'cần giấy tờ gì',
      'giấy tờ cần thiết',
      'hồ sơ cần chuẩn bị',
      'cần chuẩn bị những gì',
    ],
    answerText:
      'Dạ bạn chỉ cần mang CMND hoặc CCCD là đủ ạ. Nếu có thẻ bảo hiểm y tế hoặc bảo hiểm sức khoẻ tư nhân thì mang thêm để Doctor Check hỗ trợ thanh toán nhé ạ.',
  },
  {
    title: 'Thời gian chờ kết quả xét nghiệm',
    category: 'booking',
    tags: ['booking', 'services'],
    questionVariants: [
      'chờ kết quả bao lâu',
      'kết quả xét nghiệm mấy lâu có',
      'bao lâu có kết quả',
      'kết quả trả sau bao lâu',
      'khi nào nhận được kết quả',
    ],
    answerText:
      'Dạ hầu hết kết quả được trả trong cùng ngày sau khi hoàn thành gói khám ạ. Bác sĩ sẽ tư vấn trực tiếp và đưa ra khuyến nghị sức khoẻ cá nhân cho bạn ạ.',
  },

  // === PRICING ===
  {
    title: 'Giá gói khám tổng quát tại Doctor Check',
    category: 'pricing',
    tags: ['pricing'],
    questionVariants: [
      'giá khám bao nhiêu',
      'giá gói khám',
      'chi phí khám',
      'khám hết bao nhiêu tiền',
      'phí khám sức khoẻ',
      'bảng giá',
      'giá khám tổng quát',
    ],
    answerText:
      'Dạ Doctor Check có 3 gói khám chính ạ. Gói Cơ bản giá 3 triệu đồng, tầm soát 21 nhóm bệnh, thời gian 60-90 phút. Gói Chuyên sâu nam 5 triệu, nữ 6 triệu, tầm soát 24-26 nhóm bệnh, 90-120 phút. Gói Trường thọ nam 11,5 triệu, nữ 14,5 triệu, tầm soát 29-31 nhóm bệnh, 120 phút trở lên ạ.',
  },
  {
    title: 'Gói khám Cơ bản Doctor Check',
    category: 'pricing',
    tags: ['pricing', 'services'],
    questionVariants: [
      'gói cơ bản',
      'gói được khuyến nghị',
      'gói rẻ nhất',
      'gói 3 triệu',
      'gói basic',
    ],
    answerText:
      'Dạ gói Cơ bản tại Doctor Check giá 3.000.000đ, tầm soát 21 nhóm bệnh và 2 loại ung thư, thời gian khám 60-90 phút ạ. Đây là gói được Doctor Check khuyến nghị cho lần đầu tầm soát ạ.',
  },
  {
    title: 'Gói khám Chuyên sâu Doctor Check',
    category: 'pricing',
    tags: ['pricing', 'services'],
    questionVariants: [
      'gói chuyên sâu',
      'gói specialized',
      'gói 5 triệu',
      'gói 6 triệu',
      'gói nâng cao',
    ],
    answerText:
      'Dạ gói Chuyên sâu tại Doctor Check giá 5.000.000đ cho nam và 6.000.000đ cho nữ, tầm soát 24-26 nhóm bệnh và 4-5 loại ung thư, thời gian khám 90-120 phút ạ.',
    answerMale:
      'Dạ gói Chuyên sâu tại Doctor Check giá 5.000.000đ cho nam như anh, tầm soát 24 nhóm bệnh và 5 loại ung thư, thời gian khám 90-120 phút ạ.',
    answerFemale:
      'Dạ gói Chuyên sâu tại Doctor Check giá 6.000.000đ cho nữ như chị, tầm soát 26 nhóm bệnh và 4 loại ung thư, thời gian khám 90-120 phút ạ.',
  },
  {
    title: 'Gói khám Trường thọ Doctor Check',
    category: 'pricing',
    tags: ['pricing', 'services'],
    questionVariants: [
      'gói trường thọ',
      'gói longevity',
      'gói cao cấp nhất',
      'gói 11 triệu',
      'gói 14 triệu',
      'gói toàn diện nhất',
    ],
    answerText:
      'Dạ gói Trường thọ là gói toàn diện nhất tại Doctor Check, giá 11.500.000đ cho nam và 14.500.000đ cho nữ, tầm soát 29-31 nhóm bệnh và 9-10 loại ung thư, thời gian khám trên 120 phút ạ.',
    answerMale:
      'Dạ gói Trường thọ cho anh giá 11.500.000đ, tầm soát 29 nhóm bệnh và 9 loại ung thư, thời gian trên 120 phút ạ. Đây là gói toàn diện nhất của Doctor Check ạ.',
    answerFemale:
      'Dạ gói Trường thọ cho chị giá 14.500.000đ, tầm soát 31 nhóm bệnh và 10 loại ung thư, thời gian trên 120 phút ạ. Đây là gói toàn diện nhất của Doctor Check ạ.',
  },

  // === SERVICES ===
  {
    title: 'Các dịch vụ tại Doctor Check',
    category: 'services',
    tags: ['services'],
    questionVariants: [
      'Doctor Check có dịch vụ gì',
      'dịch vụ phòng khám',
      'khám được những gì',
      'phòng khám có những dịch vụ nào',
      'tầm soát bệnh gì',
    ],
    answerText:
      'Dạ Doctor Check cung cấp 5 dịch vụ chính: Khám sức khoẻ tổng quát, Tầm soát ung thư, Nội soi tiêu hoá, Khám sức khoẻ doanh nghiệp, và Chương trình giáo dục trường thọ ạ.',
  },
  {
    title: 'Doctor Check có tầm soát ung thư không',
    category: 'services',
    tags: ['services'],
    questionVariants: [
      'tầm soát ung thư',
      'khám ung thư',
      'phát hiện ung thư sớm',
      'tầm soát cancer',
      'Doctor Check có khám ung thư không',
    ],
    answerText:
      'Dạ có ạ. Doctor Check chuyên về tầm soát ung thư sớm, bao gồm ung thư dạ dày, ung thư đại tràng, ung thư thực quản và nhiều loại khác tùy gói khám ạ. Phát hiện sớm giúp tỉ lệ điều trị thành công rất cao ạ.',
  },

  // === ENDOSCOPY ===
  {
    title: 'Giá nội soi tại Doctor Check',
    category: 'endoscopy',
    tags: ['endoscopy', 'pricing'],
    questionVariants: [
      'giá nội soi',
      'nội soi bao nhiêu tiền',
      'chi phí nội soi',
      'nội soi dạ dày giá bao nhiêu',
      'nội soi đại tràng giá bao nhiêu',
      'giá nội soi tiêu hoá',
    ],
    answerText:
      'Dạ tại Doctor Check, nội soi thực quản-dạ dày-tá tràng giá 3.100.000đ, nội soi đại tràng giá 4.100.000đ ạ. Bạn cũng có thể chọn gói combo nội soi cả hai, bác sĩ sẽ tư vấn gói phù hợp ạ.',
  },
  {
    title: 'Nội soi có đau không',
    category: 'endoscopy',
    tags: ['endoscopy'],
    questionVariants: [
      'nội soi có đau không',
      'nội soi dạ dày có đau không',
      'nội soi đại tràng có đau không',
      'làm nội soi đau không',
      'nội soi có sợ không',
      'nội soi có khó chịu không',
    ],
    answerText:
      'Dạ không ạ. Doctor Check dùng thuốc an thần tiêm tĩnh mạch, bạn sẽ ngủ nhẹ trong suốt quá trình nội soi và hoàn toàn không cảm thấy đau hay khó chịu ạ.',
    answerMale:
      'Dạ không ạ. Doctor Check dùng thuốc an thần tiêm tĩnh mạch, anh sẽ ngủ nhẹ trong suốt quá trình và hoàn toàn không cảm thấy đau hay khó chịu ạ.',
    answerFemale:
      'Dạ không ạ. Doctor Check dùng thuốc an thần tiêm tĩnh mạch, chị sẽ ngủ nhẹ trong suốt quá trình và hoàn toàn không cảm thấy đau hay khó chịu ạ.',
  },
  {
    title: 'Nội soi mất bao lâu',
    category: 'endoscopy',
    tags: ['endoscopy'],
    questionVariants: [
      'nội soi mất bao lâu',
      'nội soi bao nhiêu thời gian',
      'thời gian nội soi',
      'nội soi lâu không',
    ],
    answerText:
      'Dạ thủ thuật nội soi thường chỉ mất 15-30 phút ạ. Sau nội soi bạn cần nghỉ ngơi thêm khoảng 30-60 phút để hồi tỉnh thuốc an thần trước khi về ạ.',
  },
  {
    title: 'Chuẩn bị trước nội soi như thế nào',
    category: 'endoscopy',
    tags: ['endoscopy', 'preparation'],
    questionVariants: [
      'chuẩn bị nội soi như thế nào',
      'trước nội soi cần làm gì',
      'nhịn ăn trước nội soi',
      'chuẩn bị trước khi nội soi',
      'nội soi cần kiêng gì',
    ],
    answerText:
      'Dạ để chuẩn bị nội soi dạ dày, bạn cần nhịn ăn ít nhất 6-8 tiếng, không uống rượu bia và không hút thuốc ạ. Đối với nội soi đại tràng cần thêm bước uống thuốc nhuận tràng theo hướng dẫn bác sĩ ạ.',
  },
  {
    title: 'Sau nội soi có ăn được ngay không',
    category: 'endoscopy',
    tags: ['endoscopy'],
    questionVariants: [
      'sau nội soi có ăn được không',
      'nội soi xong ăn được chưa',
      'ăn uống sau nội soi',
      'sau nội soi kiêng gì',
    ],
    answerText:
      'Dạ sau nội soi khoảng 1-2 tiếng, khi bạn đã tỉnh hoàn toàn là có thể ăn uống nhẹ được ạ. Nên ăn cháo hoặc thức ăn mềm trong ngày đầu và tránh đồ cứng, cay, nóng ạ.',
  },

  // === PREPARATION ===
  {
    title: 'Chuẩn bị trước khi khám sức khoẻ tổng quát',
    category: 'preparation',
    tags: ['preparation', 'booking'],
    questionVariants: [
      'chuẩn bị trước khi khám',
      'trước khi khám cần làm gì',
      'cần nhịn ăn không',
      'chuẩn bị khám sức khoẻ',
      'khám sức khoẻ cần kiêng gì',
      'trước khám nên làm gì',
    ],
    answerText:
      'Dạ trước khi khám sức khoẻ tổng quát tại Doctor Check, bạn cần nhịn ăn ít nhất 6 tiếng, không uống rượu bia và không hút thuốc 24 tiếng trước ạ. Nữ không dùng thuốc đặt âm đạo trong 3 ngày trước khám ạ.',
    answerMale:
      'Dạ trước khi khám, anh cần nhịn ăn ít nhất 6 tiếng và không uống rượu bia, không hút thuốc trong 24 tiếng trước ạ.',
    answerFemale:
      'Dạ trước khi khám, chị cần nhịn ăn ít nhất 6 tiếng, không uống rượu bia, không hút thuốc 24 tiếng, và không dùng thuốc đặt âm đạo trong 3 ngày trước ạ.',
  },
  {
    title: 'Nhịn ăn bao lâu trước khi khám',
    category: 'preparation',
    tags: ['preparation'],
    questionVariants: [
      'nhịn ăn bao lâu',
      'cần nhịn ăn mấy tiếng',
      'có cần nhịn ăn không',
      'nhịn ăn mấy giờ',
      'trước khám có cần nhịn ăn không',
    ],
    answerText:
      'Dạ bạn cần nhịn ăn ít nhất 6 tiếng trước khi khám để xét nghiệm máu được chính xác nhất ạ. Được uống nước lọc đến 2 tiếng trước khám ạ.',
  },

  // === INSURANCE ===
  {
    title: 'Doctor Check chấp nhận bảo hiểm nào',
    category: 'insurance',
    tags: ['insurance'],
    questionVariants: [
      'bảo hiểm nào được chấp nhận',
      'dùng bảo hiểm được không',
      'có nhận bảo hiểm không',
      'bảo hiểm y tế',
      'bảo hiểm sức khoẻ',
      'thanh toán qua bảo hiểm được không',
      'BHYT có dùng được không',
    ],
    answerText:
      'Dạ Doctor Check chấp nhận hơn 20 công ty bảo hiểm sức khoẻ tư nhân và bảo hiểm y tế nhà nước (BHYT) ạ. Bạn mang thẻ bảo hiểm đến và nhân viên sẽ hỗ trợ thủ tục thanh toán cho bạn ạ.',
  },
  {
    title: 'Có trả góp không',
    category: 'insurance',
    tags: ['insurance', 'pricing'],
    questionVariants: [
      'có trả góp không',
      'trả góp được không',
      'có hỗ trợ trả góp không',
      'chia nhỏ thanh toán được không',
      'thanh toán như thế nào',
    ],
    answerText:
      'Dạ Doctor Check có hỗ trợ trả góp 0% lãi suất ạ. Bạn có thể liên hệ 0939 01 01 01 để được tư vấn chi tiết về hình thức thanh toán phù hợp ạ.',
  },

  // === DOCTORS ===
  {
    title: 'Đội ngũ bác sĩ tại Doctor Check',
    category: 'doctors',
    tags: ['doctors'],
    questionVariants: [
      'bác sĩ Doctor Check',
      'đội ngũ y tế',
      'bác sĩ có kinh nghiệm không',
      'bác sĩ nào khám',
      'có bao nhiêu bác sĩ',
      'chuyên môn bác sĩ',
    ],
    answerText:
      'Dạ Doctor Check có đội ngũ 7 bác sĩ chuyên khoa giàu kinh nghiệm từ các bệnh viện lớn tại TP.HCM ạ. Đa số là BSCKII và Thạc sĩ Y khoa, chuyên về Nội tổng quát và Nội soi tiêu hoá ạ.',
  },

  // === FAQ ===
  {
    title: 'Doctor Check có app điện thoại không',
    category: 'faq',
    tags: ['faq', 'booking'],
    questionVariants: [
      'có app không',
      'ứng dụng điện thoại',
      'app Doctor Check',
      'tải app ở đâu',
      'Doctor Check Member',
    ],
    answerText:
      'Dạ có ạ. Doctor Check có app "Doctor Check Member" trên điện thoại, bạn có thể đặt lịch, xem kết quả khám và theo dõi hồ sơ sức khoẻ cá nhân ạ. Tải miễn phí trên App Store và Google Play ạ.',
  },
  {
    title: 'Có bãi đậu xe không',
    category: 'faq',
    tags: ['faq'],
    questionVariants: [
      'có bãi xe không',
      'đậu xe ở đâu',
      'bãi đậu xe',
      'gửi xe chỗ nào',
      'có chỗ đậu xe không',
    ],
    answerText:
      'Dạ Doctor Check có bãi đậu xe cho bạn ạ. Nếu cần thêm thông tin cụ thể về bãi xe, bạn có thể gọi 0939 01 01 01 để hỏi thêm nhé ạ.',
  },
  {
    title: 'Thiết bị y tế Doctor Check',
    category: 'services',
    tags: ['services', 'general'],
    questionVariants: [
      'thiết bị y tế',
      'máy móc Doctor Check',
      'thiết bị khám',
      'Doctor Check dùng thiết bị gì',
      'công nghệ y tế',
    ],
    answerText:
      'Dạ Doctor Check sử dụng thiết bị y tế đạt chuẩn quốc tế từ các thương hiệu hàng đầu như Olympus và Fujifilm cho nội soi, Siemens cho siêu âm, Abbott và Roche cho xét nghiệm máu ạ.',
  },
  {
    title: 'Thời gian khám sức khoẻ tổng quát',
    category: 'services',
    tags: ['services', 'booking'],
    questionVariants: [
      'khám mất bao lâu',
      'thời gian khám sức khoẻ',
      'mất bao nhiêu thời gian',
      'khám tổng quát lâu không',
      'cần dành bao lâu để khám',
    ],
    answerText:
      'Dạ thời gian khám phụ thuộc vào gói bạn chọn ạ. Gói Cơ bản mất 60-90 phút, Gói Chuyên sâu 90-120 phút, và Gói Trường thọ trên 120 phút ạ. Doctor Check tổ chức quy trình khoa học để bạn không phải chờ đợi lâu ạ.',
  },
]

// ─── NLU Documents ────────────────────────────────────────────────────────────

export const NLU_DOCS: NluDocDef[] = [
  // === FILLERS: thinking ===
  { type: 'filler', label: 'thinking', content: 'Dạ để em kiểm tra thông tin cho bạn ạ.' },
  { type: 'filler', label: 'thinking', content: 'Dạ em xem lại thông tin một chút ạ.' },
  { type: 'filler', label: 'thinking', content: 'Vâng, để em tra cứu thông tin ngay ạ.' },
  { type: 'filler', label: 'thinking', content: 'Dạ em kiểm tra ngay cho bạn ạ.' },
  { type: 'filler', label: 'thinking', content: 'Dạ một chút ạ, em đang tìm thông tin.' },

  // === FILLERS: ack ===
  { type: 'filler', label: 'ack', content: 'Dạ vâng ạ.' },
  { type: 'filler', label: 'ack', content: 'Vâng, em hiểu rồi ạ.' },
  { type: 'filler', label: 'ack', content: 'Dạ, em ghi nhận ạ.' },
  { type: 'filler', label: 'ack', content: 'Vâng ạ, cảm ơn bạn.' },
  { type: 'filler', label: 'ack', content: 'Dạ, bạn cho em biết thêm ạ.' },

  // === FILLERS: wait ===
  { type: 'filler', label: 'wait', content: 'Dạ bạn chờ em một chút nhé ạ.' },
  { type: 'filler', label: 'wait', content: 'Vâng, bạn chờ em xíu ạ.' },
  { type: 'filler', label: 'wait', content: 'Dạ một chút ạ.' },
  { type: 'filler', label: 'wait', content: 'Bạn cho em xin một chút ạ.' },
  { type: 'filler', label: 'wait', content: 'Dạ em đang xử lý ạ, bạn chờ xíu nhé.' },

  // === FILLERS: checking ===
  { type: 'filler', label: 'checking', content: 'Dạ em đang kiểm tra lịch cho bạn ạ.' },
  { type: 'filler', label: 'checking', content: 'Vâng, em xem lịch khám còn trống ạ.' },
  { type: 'filler', label: 'checking', content: 'Dạ em tra lịch ngay ạ.' },

  // === FILLERS: confirming ===
  { type: 'filler', label: 'confirming', content: 'Dạ để em xác nhận lại thông tin ạ.' },
  { type: 'filler', label: 'confirming', content: 'Vâng, em tóm tắt lại cho bạn ạ.' },
  { type: 'filler', label: 'confirming', content: 'Dạ em xác nhận lịch hẹn cho bạn ạ.' },

  // === INTENTS: book_appointment ===
  { type: 'intent', label: 'book_appointment', content: 'muốn đặt lịch khám' },
  { type: 'intent', label: 'book_appointment', content: 'tôi cần đặt lịch' },
  { type: 'intent', label: 'book_appointment', content: 'đăng ký khám sức khoẻ' },
  { type: 'intent', label: 'book_appointment', content: 'tôi muốn book lịch' },
  { type: 'intent', label: 'book_appointment', content: 'cho tôi đặt lịch khám tổng quát' },
  { type: 'intent', label: 'book_appointment', content: 'đặt hẹn khám' },
  { type: 'intent', label: 'book_appointment', content: 'tôi muốn đăng ký khám' },
  { type: 'intent', label: 'book_appointment', content: 'cần đặt lịch khám sức khoẻ' },
  { type: 'intent', label: 'book_appointment', content: 'có thể đặt lịch cho tôi không' },
  { type: 'intent', label: 'book_appointment', content: 'tôi muốn khám sức khoẻ định kỳ' },

  // === INTENTS: pricing_inquiry ===
  { type: 'intent', label: 'pricing_inquiry', content: 'giá khám bao nhiêu' },
  { type: 'intent', label: 'pricing_inquiry', content: 'chi phí khám sức khoẻ' },
  { type: 'intent', label: 'pricing_inquiry', content: 'bảng giá các gói khám' },
  { type: 'intent', label: 'pricing_inquiry', content: 'khám tốn bao nhiêu tiền' },
  { type: 'intent', label: 'pricing_inquiry', content: 'các gói khám giá bao nhiêu' },
  { type: 'intent', label: 'pricing_inquiry', content: 'gói rẻ nhất là bao nhiêu' },
  { type: 'intent', label: 'pricing_inquiry', content: 'phí khám sức khoẻ tổng quát' },
  { type: 'intent', label: 'pricing_inquiry', content: 'giá nội soi' },

  // === INTENTS: hours_inquiry ===
  { type: 'intent', label: 'hours_inquiry', content: 'phòng khám mở cửa mấy giờ' },
  { type: 'intent', label: 'hours_inquiry', content: 'giờ làm việc' },
  { type: 'intent', label: 'hours_inquiry', content: 'có làm cuối tuần không' },
  { type: 'intent', label: 'hours_inquiry', content: 'thứ 7 có khám không' },
  { type: 'intent', label: 'hours_inquiry', content: 'chủ nhật có mở cửa không' },
  { type: 'intent', label: 'hours_inquiry', content: 'buổi tối có khám không' },
  { type: 'intent', label: 'hours_inquiry', content: 'khám sáng hay chiều' },

  // === INTENTS: location_inquiry ===
  { type: 'intent', label: 'location_inquiry', content: 'phòng khám ở đâu' },
  { type: 'intent', label: 'location_inquiry', content: 'địa chỉ Doctor Check' },
  { type: 'intent', label: 'location_inquiry', content: 'cách đi đến phòng khám' },
  { type: 'intent', label: 'location_inquiry', content: 'Doctor Check nằm ở đâu' },
  { type: 'intent', label: 'location_inquiry', content: 'địa điểm khám' },
  { type: 'intent', label: 'location_inquiry', content: 'bệnh viện ở quận mấy' },

  // === INTENTS: insurance_inquiry ===
  { type: 'intent', label: 'insurance_inquiry', content: 'có nhận bảo hiểm không' },
  { type: 'intent', label: 'insurance_inquiry', content: 'dùng bảo hiểm y tế được không' },
  { type: 'intent', label: 'insurance_inquiry', content: 'BHYT có dùng được không' },
  { type: 'intent', label: 'insurance_inquiry', content: 'bảo hiểm sức khoẻ tư nhân' },
  { type: 'intent', label: 'insurance_inquiry', content: 'có hỗ trợ bảo hiểm không' },
  { type: 'intent', label: 'insurance_inquiry', content: 'trả bằng bảo hiểm được không' },

  // === INTENTS: preparation_inquiry ===
  { type: 'intent', label: 'preparation_inquiry', content: 'cần chuẩn bị gì trước khi khám' },
  { type: 'intent', label: 'preparation_inquiry', content: 'có cần nhịn ăn không' },
  { type: 'intent', label: 'preparation_inquiry', content: 'trước khám cần làm gì' },
  { type: 'intent', label: 'preparation_inquiry', content: 'mang giấy tờ gì đến khám' },
  { type: 'intent', label: 'preparation_inquiry', content: 'cần nhịn ăn mấy tiếng' },

  // === INTENTS: service_inquiry ===
  { type: 'intent', label: 'service_inquiry', content: 'phòng khám có dịch vụ gì' },
  { type: 'intent', label: 'service_inquiry', content: 'Doctor Check khám được những bệnh gì' },
  { type: 'intent', label: 'service_inquiry', content: 'tầm soát bệnh gì' },
  { type: 'intent', label: 'service_inquiry', content: 'có nội soi không' },
  { type: 'intent', label: 'service_inquiry', content: 'có tầm soát ung thư không' },
  { type: 'intent', label: 'service_inquiry', content: 'khám sức khoẻ doanh nghiệp' },

  // === INTENTS: doctor_inquiry ===
  { type: 'intent', label: 'doctor_inquiry', content: 'bác sĩ Doctor Check là ai' },
  { type: 'intent', label: 'doctor_inquiry', content: 'đội ngũ bác sĩ' },
  { type: 'intent', label: 'doctor_inquiry', content: 'bác sĩ có kinh nghiệm không' },
  { type: 'intent', label: 'doctor_inquiry', content: 'muốn biết về bác sĩ' },

  // === INTENTS: cancel_booking ===
  { type: 'intent', label: 'cancel_booking', content: 'tôi muốn huỷ lịch' },
  { type: 'intent', label: 'cancel_booking', content: 'huỷ lịch khám' },
  { type: 'intent', label: 'cancel_booking', content: 'đổi lịch được không' },
  { type: 'intent', label: 'cancel_booking', content: 'không đi khám được nữa' },
  { type: 'intent', label: 'cancel_booking', content: 'muốn dời lịch hẹn' },

  // === INTENTS: confirm / deny ===
  { type: 'intent', label: 'confirm', content: 'đúng rồi' },
  { type: 'intent', label: 'confirm', content: 'vâng đúng ạ' },
  { type: 'intent', label: 'confirm', content: 'ừ đúng vậy' },
  { type: 'intent', label: 'confirm', content: 'ok' },
  { type: 'intent', label: 'confirm', content: 'được ạ' },
  { type: 'intent', label: 'deny', content: 'không đúng' },
  { type: 'intent', label: 'deny', content: 'không phải vậy' },
  { type: 'intent', label: 'deny', content: 'không' },
  { type: 'intent', label: 'deny', content: 'thôi không cần' },
  { type: 'intent', label: 'deny', content: 'không muốn nữa' },
]
