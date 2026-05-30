'use client'

import { useState } from 'react'
import { ChevronRight, ChevronDown, BookOpen, FileText, Loader2 } from 'lucide-react'

interface KbArticle {
  id: string
  title: string
  category: string | null
  tags: string[]
}

interface CategoryNode {
  name: string
  displayName: string
  articles: KbArticle[]
}

function groupByCategory(articles: KbArticle[]): CategoryNode[] {
  const map = new Map<string, KbArticle[]>()
  for (const a of articles) {
    const key = a.category ?? '__uncategorized__'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(a)
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, arts]) => ({
      name,
      displayName: name === '__uncategorized__' ? 'Không phân loại' : name,
      articles: arts,
    }))
}

interface Props {
  selected: string[]
  onChange: (selected: string[]) => void
  loading?: boolean
  articles: KbArticle[]
}

export function KbCategoryTree({ selected, onChange, loading, articles }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const categories = groupByCategory(articles)
  const selectedSet = new Set(selected)

  function toggleCategory(name: string) {
    const next = new Set(selectedSet)
    if (next.has(name)) {
      next.delete(name)
    } else {
      next.add(name)
    }
    onChange([...next])
  }

  function toggleExpand(name: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-xs text-[var(--color-text-muted)]">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Đang tải danh mục KB...
      </div>
    )
  }

  if (articles.length === 0) {
    return (
      <div className="py-4 text-xs text-[var(--color-text-muted)] italic">
        Chưa có article nào trong Knowledge Base. Thêm article trước để cấu hình filter.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] overflow-hidden">
      {categories.map((cat, i) => {
        const isSelected = selectedSet.has(cat.name)
        const isExpanded = expanded.has(cat.name)
        const isLast = i === categories.length - 1

        return (
          <div key={cat.name} className={!isLast ? 'border-b border-[var(--color-border)]' : ''}>
            {/* Category row */}
            <div
              className={[
                'flex items-center gap-0 transition-colors',
                isSelected
                  ? 'bg-[oklch(96%_0.03_250)]'
                  : 'bg-white hover:bg-[var(--color-surface-overlay)]',
              ].join(' ')}
            >
              {/* Checkbox */}
              <label className="flex items-center gap-2.5 flex-1 px-3 py-2.5 cursor-pointer">
                <div
                  className={[
                    'w-4 h-4 rounded flex items-center justify-center shrink-0 border transition-colors',
                    isSelected
                      ? 'bg-[var(--color-accent)] border-[var(--color-accent)]'
                      : 'bg-white border-[oklch(75%_0.03_250)]',
                  ].join(' ')}
                  onClick={() => toggleCategory(cat.name)}
                >
                  {isSelected && (
                    <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 10 8" fill="none">
                      <path d="M1 4l3 3 5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </div>
                <div
                  className="flex items-center gap-2 flex-1 min-w-0"
                  onClick={() => toggleCategory(cat.name)}
                >
                  <BookOpen className={['w-3.5 h-3.5 shrink-0', isSelected ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]'].join(' ')} />
                  <span className={['text-sm font-medium truncate', isSelected ? 'text-[var(--color-accent)]' : 'text-[var(--color-text)]'].join(' ')}>
                    {cat.displayName}
                  </span>
                  <span className="text-[10px] text-[var(--color-text-muted)] shrink-0">
                    {cat.articles.length} article{cat.articles.length !== 1 ? 's' : ''}
                  </span>
                </div>
              </label>

              {/* Expand toggle */}
              <button
                type="button"
                onClick={() => toggleExpand(cat.name)}
                className="px-3 py-2.5 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors shrink-0"
              >
                {isExpanded
                  ? <ChevronDown className="w-3.5 h-3.5" />
                  : <ChevronRight className="w-3.5 h-3.5" />
                }
              </button>
            </div>

            {/* Articles (expandable) */}
            {isExpanded && (
              <div className="bg-[oklch(98.5%_0.003_250)] border-t border-[var(--color-border)]">
                {cat.articles.map((article, ai) => (
                  <div
                    key={article.id}
                    className={[
                      'flex items-start gap-2 px-5 py-2',
                      ai < cat.articles.length - 1 ? 'border-b border-[var(--color-border)]' : '',
                    ].join(' ')}
                  >
                    <FileText className="w-3 h-3 text-[var(--color-text-muted)] mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-[var(--color-text)] truncate">{article.title}</p>
                      {article.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {article.tags.map((tag) => (
                            <span
                              key={tag}
                              className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-[oklch(93%_0.02_250)] text-[var(--color-text-muted)]"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
