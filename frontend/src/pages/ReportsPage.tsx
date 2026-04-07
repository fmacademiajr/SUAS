import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { useDigests, useWeeklyReports, useMonthlyReports } from '../api/reports'
import type { EditorialDigest, WeeklyReport, MonthlyReport } from '../api/reports'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-800 rounded-lg ${className}`} />
}

function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonBlock key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

const EMPTY_STATE = (
  <div className="card p-10 text-center text-gray-500 text-sm">
    No reports yet. Reports generate automatically after the first pipeline runs.
  </div>
)

/** Prose wrapper: applies dark-friendly markdown styles */
function Prose({ children }: { children: React.ReactNode }) {
  return (
    <div className="prose-sm max-w-none text-gray-300 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_strong]:text-white [&_a]:text-blue-400 [&_a:hover]:text-blue-300 [&_code]:bg-gray-800 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_pre]:bg-gray-800 [&_pre]:p-4 [&_pre]:rounded-lg [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-0.5 [&_hr]:border-gray-700">
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

type TabId = 'daily' | 'weekly' | 'monthly'

const TABS: { id: TabId; label: string }[] = [
  { id: 'daily', label: 'Daily' },
  { id: 'weekly', label: 'Weekly' },
  { id: 'monthly', label: 'Monthly' },
]

// ---------------------------------------------------------------------------
// Daily Tab
// ---------------------------------------------------------------------------

function DailyTab() {
  const { data: digests = [], isLoading } = useDigests(30)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const selected: EditorialDigest | undefined =
    digests.find((d) => d.id === selectedId) ?? digests[0]

  if (isLoading) {
    return (
      <div className="flex gap-6">
        <div className="hidden sm:block w-48 shrink-0 space-y-2">
          <SkeletonList rows={8} />
        </div>
        <div className="flex-1 card p-6 space-y-3">
          <SkeletonBlock className="h-4 w-1/3" />
          <SkeletonBlock className="h-4 w-full" />
          <SkeletonBlock className="h-4 w-5/6" />
          <SkeletonBlock className="h-4 w-full" />
          <SkeletonBlock className="h-40 w-full mt-2" />
        </div>
      </div>
    )
  }

  if (!digests.length) return EMPTY_STATE

  return (
    <div className="flex flex-col sm:flex-row gap-6">
      {/* Mobile: dropdown */}
      <div className="sm:hidden">
        <select
          className="input"
          value={selected?.id ?? ''}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {digests.map((d) => (
            <option key={d.id} value={d.id}>
              {d.date}
            </option>
          ))}
        </select>
      </div>

      {/* Desktop: sidebar list */}
      <aside className="hidden sm:flex flex-col w-48 shrink-0 gap-1">
        {digests.map((d) => {
          const isActive = selected?.id === d.id
          return (
            <button
              key={d.id}
              onClick={() => setSelectedId(d.id)}
              className={`text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-blue-600 text-white font-medium'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              {d.date}
            </button>
          )
        })}
      </aside>

      {/* Content panel */}
      <div className="flex-1 card p-6 overflow-auto">
        {selected ? (
          <>
            <p className="text-xs text-gray-500 mb-4">{selected.date}</p>
            <Prose>
              <ReactMarkdown>{selected.content}</ReactMarkdown>
            </Prose>
          </>
        ) : (
          <p className="text-gray-500 text-sm">Select a date to view the digest.</p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Accordion item (shared by Weekly + Monthly)
// ---------------------------------------------------------------------------

interface AccordionItemProps {
  label: string
  preview: string
  content: string
  isOpen: boolean
  onToggle: () => void
}

function AccordionItem({ label, preview, content, isOpen, onToggle }: AccordionItemProps) {
  return (
    <div className="card overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex-1 min-w-0 pr-4">
          <p className="text-sm font-semibold text-gray-200">{label}</p>
          {!isOpen && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{preview}</p>
          )}
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="px-5 pb-6 border-t border-gray-800">
          <div className="pt-4">
            <Prose>
              <ReactMarkdown>{content}</ReactMarkdown>
            </Prose>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Weekly Tab
// ---------------------------------------------------------------------------

function WeeklyTab() {
  const { data: reports = [], isLoading } = useWeeklyReports(8)
  const [openId, setOpenId] = useState<string | null>(null)

  if (isLoading) return <SkeletonList rows={4} />
  if (!reports.length) return EMPTY_STATE

  return (
    <div className="space-y-3">
      {reports.map((r: WeeklyReport) => (
        <AccordionItem
          key={r.id}
          label={`Week of ${r.week_start}`}
          preview={r.content.slice(0, 150).replace(/[#*`]/g, '')}
          content={r.content}
          isOpen={openId === r.id}
          onToggle={() => setOpenId(openId === r.id ? null : r.id)}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Monthly Tab
// ---------------------------------------------------------------------------

function MonthlyTab() {
  const { data: reports = [], isLoading } = useMonthlyReports(6)
  const [openId, setOpenId] = useState<string | null>(null)

  if (isLoading) return <SkeletonList rows={4} />
  if (!reports.length) return EMPTY_STATE

  return (
    <div className="space-y-3">
      {reports.map((r: MonthlyReport) => (
        <AccordionItem
          key={r.id}
          label={r.month}
          preview={r.content.slice(0, 150).replace(/[#*`]/g, '')}
          content={r.content}
          isOpen={openId === r.id}
          onToggle={() => setOpenId(openId === r.id ? null : r.id)}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ReportsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('daily')

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <div className="bg-gray-900/50 border-b border-gray-800 px-4 sm:px-6 py-6 sticky top-0 z-20">
        <div className="max-w-5xl mx-auto">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100">Reports</h1>
        </div>
      </div>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        {/* Tab bar */}
        <div className="flex gap-1 mb-8 bg-gray-900 border border-gray-800 rounded-xl p-1 w-fit">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === 'daily' && <DailyTab />}
        {activeTab === 'weekly' && <WeeklyTab />}
        {activeTab === 'monthly' && <MonthlyTab />}
      </main>
    </div>
  )
}
