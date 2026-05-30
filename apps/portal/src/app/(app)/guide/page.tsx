import {
  PhoneCall,
  Bot,
  MessageSquare,
  CalendarCheck,
  ArrowRight,
  ArrowDown,
  FileText,
  BookOpen,
  Zap,
  Target,
  Clock,
  RefreshCw,
  GitBranch,
  Lightbulb,
  CheckCircle2,
  Sparkles,
} from 'lucide-react'

export const metadata = {
  title: 'Hướng dẫn sử dụng — DoctorCheck',
}

/* ----------------------------------------------------------------------------
 * Design tokens for this page (light surface, editorial layout).
 * Colors map onto the project's CSS variables in globals.css.
 * -------------------------------------------------------------------------- */

const SECTION_CARD =
  'rounded-2xl bg-[var(--color-surface-raised)] border border-[var(--color-border)] shadow-[0_1px_2px_oklch(0%_0_0_/_4%),0_8px_24px_-12px_oklch(0%_0_0_/_10%)]'

function SectionHeader({
  index,
  title,
  subtitle,
}: {
  index: string
  title: string
  subtitle?: string
}) {
  return (
    <header className="flex items-start gap-4">
      <span className="shrink-0 mt-0.5 inline-flex items-center justify-center w-9 h-9 rounded-xl bg-[oklch(55%_0.2_250_/_10%)] text-[var(--color-accent)] text-sm font-bold tabular-nums">
        {index}
      </span>
      <div className="min-w-0">
        <h2 className="text-xl font-semibold tracking-tight text-[var(--color-text)]">
          {title}
        </h2>
        {subtitle ? (
          <p className="mt-1 text-sm text-[var(--color-text-muted)] leading-relaxed">
            {subtitle}
          </p>
        ) : null}
      </div>
    </header>
  )
}

function Callout({
  tone = 'accent',
  icon: Icon,
  title,
  children,
}: {
  tone?: 'accent' | 'warning' | 'success'
  icon: React.ElementType
  title: string
  children: React.ReactNode
}) {
  const tones = {
    accent: {
      wrap: 'bg-[oklch(55%_0.2_250_/_6%)] border-[oklch(55%_0.2_250_/_22%)]',
      icon: 'text-[var(--color-accent)]',
      title: 'text-[oklch(40%_0.2_250)]',
    },
    warning: {
      wrap: 'bg-[oklch(72%_0.19_85_/_10%)] border-[oklch(72%_0.19_85_/_30%)]',
      icon: 'text-[oklch(58%_0.16_70)]',
      title: 'text-[oklch(48%_0.14_70)]',
    },
    success: {
      wrap: 'bg-[oklch(55%_0.18_145_/_8%)] border-[oklch(55%_0.18_145_/_26%)]',
      icon: 'text-[var(--color-success)]',
      title: 'text-[oklch(42%_0.16_145)]',
    },
  }[tone]

  return (
    <div className={`rounded-xl border px-4 py-3.5 ${tones.wrap}`}>
      <div className="flex items-center gap-2">
        <Icon className={`w-4 h-4 shrink-0 ${tones.icon}`} />
        <p className={`text-xs font-semibold uppercase tracking-wider ${tones.title}`}>
          {title}
        </p>
      </div>
      <div className="mt-1.5 text-sm text-[var(--color-text)] leading-relaxed">
        {children}
      </div>
    </div>
  )
}

/* A horizontal flow chip with an arrow connector (wraps on mobile). */
function FlowStep({
  icon: Icon,
  label,
  last = false,
}: {
  icon: React.ElementType
  label: string
  last?: boolean
}) {
  return (
    <>
      <div className="flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2.5">
        <Icon className="w-4 h-4 text-[var(--color-accent)] shrink-0" />
        <span className="text-sm font-medium text-[var(--color-text)] whitespace-nowrap">
          {label}
        </span>
      </div>
      {!last ? (
        <ArrowRight className="w-4 h-4 text-[var(--color-text-muted)] shrink-0 hidden sm:block" />
      ) : null}
    </>
  )
}

export default function GuidePage() {
  return (
    <div className="px-6 sm:px-10 py-10 max-w-4xl mx-auto">
      {/* Page intro */}
      <div className="flex items-center gap-2 text-[var(--color-accent)] mb-3">
        <Sparkles className="w-4 h-4" />
        <span className="text-xs font-semibold uppercase tracking-widest">
          Hướng dẫn sử dụng
        </span>
      </div>
      <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[var(--color-text)]">
        Cách hệ thống AI Call hoạt động
      </h1>
      <p className="mt-3 text-base text-[var(--color-text-muted)] leading-relaxed max-w-2xl">
        Tài liệu này giải thích bằng ngôn ngữ đơn giản cách AI thay nhân viên
        tổng đài trả lời khách hàng — và bạn cần chuẩn bị những gì để AI làm việc
        tốt. Không cần kiến thức kỹ thuật.
      </p>

      <div className="mt-10 space-y-6">
        {/* SECTION 1 — How it works */}
        <section className={`${SECTION_CARD} p-6 sm:p-8`}>
          <SectionHeader
            index="1"
            title="Hệ thống hoạt động thế nào?"
            subtitle="Khi khách gọi vào phòng khám, AI sẽ tự động trả lời thay nhân viên — giống như có một nhân viên tổng đài ảo làm việc 24/7, không nghỉ, không bận máy."
          />

          <div className="mt-6 rounded-xl bg-[var(--color-surface-overlay)] border border-[var(--color-border)] p-5">
            <div className="flex flex-wrap items-center gap-2.5">
              <FlowStep icon={PhoneCall} label="Khách gọi điện" />
              <FlowStep icon={Bot} label="AI nhận máy" />
              <FlowStep icon={FileText} label="AI hỏi theo kịch bản" />
              <FlowStep icon={MessageSquare} label="Khách trả lời" />
              <FlowStep icon={Sparkles} label="AI hiểu & phản hồi" />
              <FlowStep icon={CalendarCheck} label="Đặt lịch / Chuyển máy" last />
            </div>
          </div>

          <p className="mt-5 text-sm text-[var(--color-text-muted)] leading-relaxed">
            Toàn bộ cuộc gọi diễn ra tự động. AI lắng nghe khách nói, hiểu ý
            khách muốn gì, rồi trả lời bằng giọng nói tự nhiên. Nếu gặp tình
            huống ngoài khả năng, AI sẽ chuyển máy cho người thật.
          </p>
        </section>

        {/* SECTION 2 — Scripts */}
        <section className={`${SECTION_CARD} p-6 sm:p-8`}>
          <SectionHeader
            index="2"
            title="Scripts CMS — Kịch bản cuộc gọi"
            subtitle="Script là kịch bản mà AI sẽ theo để dẫn dắt cuộc hội thoại. Giống như một bản hướng dẫn các bước cho nhân viên mới: làm gì trước, hỏi gì sau."
          />

          <ol className="mt-6 space-y-3">
            {[
              { n: 1, t: 'AI chào hỏi', d: '"Dạ phòng khám DoctorCheck xin nghe ạ."' },
              { n: 2, t: 'Hỏi khách muốn khám gì', d: '"Anh/chị muốn khám chuyên khoa nào ạ?"' },
              { n: 3, t: 'Hỏi ngày giờ mong muốn', d: '"Anh/chị muốn đặt lịch vào ngày nào ạ?"' },
              { n: 4, t: 'Xác nhận lại thông tin', d: '"Em xác nhận: khám tim mạch, thứ Hai tuần sau lúc 9 giờ sáng đúng không ạ?"' },
            ].map((s) => (
              <li key={s.n} className="flex gap-3.5">
                <span className="shrink-0 mt-0.5 inline-flex items-center justify-center w-6 h-6 rounded-md bg-[oklch(55%_0.2_250_/_10%)] text-[var(--color-accent)] text-xs font-bold tabular-nums">
                  {s.n}
                </span>
                <div>
                  <p className="text-sm font-medium text-[var(--color-text)]">
                    Bước {s.n} — {s.t}
                  </p>
                  <p className="text-sm text-[var(--color-text-muted)] mt-0.5">{s.d}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-6">
            <Callout icon={Lightbulb} title="Khi nào cần tạo Script mới?">
              Mỗi loại chiến dịch gọi cần một script riêng — ví dụ một script cho{' '}
              <strong>đặt lịch khám (booking)</strong>, một script khác cho{' '}
              <strong>nhắc lịch tái khám</strong>. Mỗi mục đích gọi có flow hội
              thoại khác nhau.
            </Callout>
          </div>
        </section>

        {/* SECTION 3 — Knowledge Base */}
        <section className={`${SECTION_CARD} p-6 sm:p-8`}>
          <SectionHeader
            index="3"
            title="Knowledge Base — Kho kiến thức"
            subtitle="KB là nơi lưu các câu hỏi thường gặp và câu trả lời đã viết sẵn. Khi khách hỏi điều ngoài kịch bản, AI sẽ tra cứu ở đây để trả lời."
          />

          <div className="mt-6 rounded-xl bg-[var(--color-surface-overlay)] border border-[var(--color-border)] p-5 space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-accent)]">
                Khách hỏi
              </p>
              <p className="mt-1 text-sm font-medium text-[var(--color-text)]">
                "Phòng khám có nhận bảo hiểm không?"
              </p>
            </div>
            <div className="h-px bg-[var(--color-border)]" />
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-success)]">
                AI trả lời (từ KB)
              </p>
              <p className="mt-1 text-sm text-[var(--color-text)] leading-relaxed">
                "Dạ, phòng khám có nhận bảo hiểm BHYT và bảo hiểm tư nhân ạ.
                Anh/chị mang theo thẻ khi đến nhé."
              </p>
            </div>
          </div>

          <div className="mt-6">
            <Callout tone="warning" icon={Clock} title="Lưu ý khi viết câu trả lời">
              Câu trả lời phải <strong>viết sẵn, ngắn gọn</strong> và đọc được tự
              nhiên qua điện thoại. Tránh câu dài, liệt kê nhiều ý — khách nghe
              chứ không đọc.
            </Callout>
          </div>
        </section>

        {/* SECTION 4 — NLU Content */}
        <section className={`${SECTION_CARD} p-6 sm:p-8`}>
          <SectionHeader
            index="4"
            title="NLU Content — Bộ não hiểu tiếng Việt"
            subtitle="NLU giúp AI hiểu được khách đang nói gì, dù mỗi người diễn đạt một kiểu. Có 4 loại nội dung bạn cần chuẩn bị."
          />

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {[
              {
                icon: Target,
                tag: 'Intent Examples',
                vi: 'Ví dụ ý định',
                d: 'Dạy AI biết khi khách nói "muốn đặt lịch" hay "tôi cần khám" thì đều có nghĩa là đặt lịch. Càng nhiều ví dụ, AI càng hiểu tốt.',
              },
              {
                icon: Clock,
                tag: 'Fillers',
                vi: 'Câu chờ',
                d: 'Những câu ngắn AI nói trong khi đang xử lý, ví dụ "Dạ," hay "Để em kiểm tra ạ". Giúp cuộc gọi không bị im lặng gượng.',
              },
              {
                icon: RefreshCw,
                tag: 'Reprompts',
                vi: 'Hỏi lại',
                d: 'Khi khách không trả lời đúng yêu cầu, AI sẽ hỏi lại theo cách khác. Ví dụ: "Anh/chị muốn khám chuyên khoa gì ạ?" → nếu chưa rõ → "Em có thể hỗ trợ anh/chị chọn chuyên khoa không ạ?"',
              },
              {
                icon: GitBranch,
                tag: 'Dialog Nodes',
                vi: 'Mô tả bước',
                d: 'Mô tả kỹ thuật cho từng bước trong kịch bản, giúp AI nhận biết đang ở bước nào của cuộc hội thoại.',
              },
            ].map((item) => (
              <div
                key={item.tag}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
              >
                <div className="flex items-center gap-2.5">
                  <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-[oklch(55%_0.2_250_/_10%)]">
                    <item.icon className="w-4 h-4 text-[var(--color-accent)]" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-[var(--color-text)] leading-none">
                      {item.tag}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)] mt-1">
                      {item.vi}
                    </p>
                  </div>
                </div>
                <p className="mt-3 text-sm text-[var(--color-text-muted)] leading-relaxed">
                  {item.d}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* SECTION 5 — Relationship */}
        <section className={`${SECTION_CARD} p-6 sm:p-8`}>
          <SectionHeader
            index="5"
            title="Mối liên hệ giữa 3 thành phần"
            subtitle="Script, NLU và Knowledge Base làm việc cùng nhau. Mỗi cái lo một việc."
          />

          <div className="mt-6 space-y-2">
            {[
              {
                icon: FileText,
                title: 'SCRIPT — Kịch bản',
                role: 'định nghĩa các bước hội thoại',
              },
              {
                icon: Zap,
                title: 'NLU Content — Bộ não',
                role: 'giúp AI hiểu tiếng Việt của khách',
              },
              {
                icon: BookOpen,
                title: 'Knowledge Base — Kho kiến thức',
                role: 'trả lời câu hỏi phát sinh ngoài kịch bản',
              },
            ].map((c, i, arr) => (
              <div key={c.title}>
                <div className="flex items-center gap-3.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3.5">
                  <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-[oklch(55%_0.2_250_/_10%)] shrink-0">
                    <c.icon className="w-4 h-4 text-[var(--color-accent)]" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-[var(--color-text)]">
                      {c.title}
                    </p>
                    <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
                      ↳ {c.role}
                    </p>
                  </div>
                </div>
                {i < arr.length - 1 ? (
                  <div className="flex justify-center py-1">
                    <ArrowDown className="w-4 h-4 text-[var(--color-text-muted)]" />
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          <div className="mt-6">
            <Callout icon={Sparkles} title="Ví dụ hoàn chỉnh">
              <p className="mb-2">
                Khách gọi và nói:{' '}
                <em>"Tôi muốn đặt lịch khám tim mạch tuần sau."</em>
              </p>
              <ul className="space-y-1.5 list-none">
                <li className="flex gap-2">
                  <span className="text-[var(--color-accent)] font-semibold shrink-0">
                    NLU
                  </span>
                  <span>
                    nhận ra đây là ý định <code className="text-xs px-1 py-0.5 rounded bg-[oklch(55%_0.2_250_/_10%)] text-[var(--color-accent)]">book_appointment</code> (nhờ intent examples).
                  </span>
                </li>
                <li className="flex gap-2">
                  <span className="text-[var(--color-accent)] font-semibold shrink-0">
                    Script
                  </span>
                  <span>dẫn dắt hỏi thêm ngày giờ cụ thể.</span>
                </li>
                <li className="flex gap-2">
                  <span className="text-[var(--color-accent)] font-semibold shrink-0">
                    KB
                  </span>
                  <span>
                    nếu khách hỏi "Bác sĩ tim mạch của phòng khám tên gì?" → tra
                    cứu và trả lời.
                  </span>
                </li>
              </ul>
            </Callout>
          </div>
        </section>

        {/* SECTION 6 — How-to */}
        <section className={`${SECTION_CARD} p-6 sm:p-8`}>
          <SectionHeader
            index="6"
            title="Hướng dẫn khởi tạo từng bước"
            subtitle="Làm theo thứ tự này để đưa một chiến dịch gọi mới vào hoạt động."
          />

          <ol className="mt-6 space-y-px">
            {[
              {
                t: 'Tạo Script (Campaign) mới',
                d: 'Vào /scripts/new — đặt tên, chọn loại inbound (khách gọi vào) hoặc outbound (mình gọi ra).',
              },
              {
                t: 'Thêm KB articles',
                d: 'Viết các câu hỏi & trả lời thường gặp, gắn với script tương ứng.',
              },
              {
                t: 'Thêm NLU intents',
                d: 'Cung cấp ít nhất 5–10 ví dụ câu nói cho mỗi hành động khách có thể làm.',
              },
              {
                t: 'Thêm Fillers',
                d: 'Tối thiểu cho các ngữ cảnh: thinking (đang nghĩ), ack (xác nhận), wait (chờ máy).',
              },
              {
                t: 'Thêm Reprompts',
                d: 'Mỗi bước "collect" (thu thập thông tin) trong script nên có 1–2 câu hỏi lại.',
              },
              {
                t: 'Tạo Script Version và submit review',
                d: 'Đóng gói phiên bản hoàn chỉnh và gửi QA duyệt.',
              },
              {
                t: 'Admin publish → bắt đầu chiến dịch',
                d: 'Sau khi được duyệt, Admin xuất bản và AI bắt đầu nhận cuộc gọi.',
              },
            ].map((s, i) => (
              <li
                key={s.t}
                className="flex gap-4 py-3 border-b border-[var(--color-border)] last:border-b-0"
              >
                <span className="shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-full bg-[var(--color-accent)] text-white text-xs font-bold tabular-nums">
                  {i + 1}
                </span>
                <div>
                  <p className="text-sm font-semibold text-[var(--color-text)]">
                    {s.t}
                  </p>
                  <p className="text-sm text-[var(--color-text-muted)] mt-0.5 leading-relaxed">
                    {s.d}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* SECTION 7 — Tips */}
        <section className={`${SECTION_CARD} p-6 sm:p-8`}>
          <SectionHeader
            index="7"
            title="Tips & Lưu ý"
            subtitle="Những điều nhỏ tạo nên khác biệt lớn về chất lượng cuộc gọi."
          />

          <div className="mt-6 space-y-3">
            <Callout tone="success" icon={CheckCircle2} title="Viết KB như đang nói chuyện">
              Câu trả lời KB nên viết như đang nói chuyện điện thoại, không phải
              văn bản. Đọc to lên thử — nếu nghe gượng, viết lại.
            </Callout>
            <Callout tone="success" icon={CheckCircle2} title="Intent đa dạng cách nói">
              Intent examples cần đa dạng cách diễn đạt, kể cả cách nói không
              chuẩn, viết tắt, hoặc cách nói vùng miền.
            </Callout>
            <Callout tone="warning" icon={CheckCircle2} title="Luôn test trước khi publish">
              Test kỹ bằng <strong>Simulator</strong> trước khi publish. Đóng vai
              khách và thử các tình huống khó để xem AI phản ứng ra sao.
            </Callout>
          </div>
        </section>
      </div>
    </div>
  )
}
