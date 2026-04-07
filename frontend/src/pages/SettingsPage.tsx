import { useState, useEffect, useRef, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import { useVoiceGuide, useUpdateVoiceGuide } from '../api/settings'
import {
  useCelebrities,
  useAddCelebrity,
  useToggleCelebrity,
  useDeleteCelebrity,
} from '../api/celebrities'
import {
  useLearningLog,
  useRateLearningEntry,
} from '../api/learning_log'
import type { LearningLogEntry } from '../api/learning_log'
import { ConfirmDialog } from '../components/common/ConfirmDialog'
import {
  useModelStatus,
  useModelOverrides,
  usePostCount,
  useTriggerTraining,
} from '../api/model_admin'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-800 rounded-lg ${className}`} />
}

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

type TabId = 'voice-guide' | 'celebrity-tracker' | 'learning-log' | 'scoring-model'

const TABS: { id: TabId; label: string }[] = [
  { id: 'voice-guide', label: 'Voice Guide' },
  { id: 'celebrity-tracker', label: 'Celebrity Tracker' },
  { id: 'learning-log', label: 'Learning Log' },
  { id: 'scoring-model', label: 'Scoring Model' },
]

// ---------------------------------------------------------------------------
// Tab 1: Voice Guide Editor
// ---------------------------------------------------------------------------

function VoiceGuideTab() {
  const { data: guide, isLoading, isError } = useVoiceGuide()
  const updateMutation = useUpdateVoiceGuide()

  const serialise = (g: typeof guide): string => {
    if (!g) return ''
    const lines: string[] = []

    if (g.persona_description) {
      lines.push('## Persona Description', '', g.persona_description, '')
    }

    if (g.tone_rules?.length) {
      lines.push('## Tone Rules', '')
      g.tone_rules.forEach((r) => lines.push(`- ${r}`))
      lines.push('')
    }

    if (g.one_liner_patterns?.length) {
      lines.push('## One-Liner Patterns', '')
      g.one_liner_patterns.forEach((p) => lines.push(`- ${p}`))
      lines.push('')
    }

    if (g.forbidden_phrases?.length) {
      lines.push('## Forbidden Phrases', '')
      g.forbidden_phrases.forEach((p) => lines.push(`- ${p}`))
      lines.push('')
    }

    if (g.example_posts?.length) {
      lines.push('## Example Posts', '')
      g.example_posts.forEach((p, i) => lines.push(`### Example ${i + 1}`, '', p, ''))
    }

    return lines.join('\n').trim()
  }

  const deserialise = (text: string): typeof guide => {
    const sections: Record<string, string> = {}
    const parts = text.split(/^## /m)
    parts.forEach((part) => {
      const firstLine = part.split('\n')[0].trim()
      const body = part.split('\n').slice(1).join('\n').trim()
      if (firstLine) sections[firstLine] = body
    })

    const bulletLines = (raw: string) =>
      raw
        .split('\n')
        .map((l) => l.replace(/^[-*]\s*/, '').trim())
        .filter(Boolean)

    const exampleBlocks = (raw: string) =>
      raw
        .split(/^### Example \d+/m)
        .map((b) => b.trim())
        .filter(Boolean)

    return {
      persona_description: (sections['Persona Description'] || '').trim(),
      tone_rules: bulletLines(sections['Tone Rules'] || ''),
      one_liner_patterns: bulletLines(sections['One-Liner Patterns'] || ''),
      forbidden_phrases: bulletLines(sections['Forbidden Phrases'] || ''),
      example_posts: exampleBlocks(sections['Example Posts'] || ''),
    }
  }

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const successTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (guide && !editing) {
      setDraft(serialise(guide))
    }
  }, [guide]) // eslint-disable-line react-hooks/exhaustive-deps

  const savedValue = guide ? serialise(guide) : ''
  const hasUnsaved = editing && draft !== savedValue

  function handleEdit() {
    setDraft(serialise(guide))
    setEditing(true)
    setErrorMsg(null)
    setSuccessMsg(null)
  }

  function handleCancel() {
    setDraft(serialise(guide))
    setEditing(false)
    setErrorMsg(null)
  }

  async function handleSave() {
    setErrorMsg(null)
    const payload = deserialise(draft)
    try {
      await updateMutation.mutateAsync(payload ?? {})
      setEditing(false)
      setSuccessMsg('Voice guide saved.')
      if (successTimer.current) clearTimeout(successTimer.current)
      successTimer.current = setTimeout(() => setSuccessMsg(null), 3000)
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Save failed.')
    }
  }

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-300">Voice Guide</h2>
        {!editing && !isLoading && (
          <button className="btn-secondary text-sm" onClick={handleEdit}>
            Edit
          </button>
        )}
      </div>

      {isLoading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-3">
          <SkeletonBlock className="h-4 w-1/3" />
          <SkeletonBlock className="h-4 w-full" />
          <SkeletonBlock className="h-4 w-5/6" />
          <SkeletonBlock className="h-4 w-full" />
          <SkeletonBlock className="h-4 w-4/6" />
          <SkeletonBlock className="h-24 w-full mt-2" />
        </div>
      )}

      {isError && !isLoading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-red-400 text-sm">
          Failed to load voice guide.
        </div>
      )}

      {!isLoading && !isError && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          {editing ? (
            <>
              <textarea
                className="input font-mono text-xs leading-relaxed resize-y"
                style={{ minHeight: 400 }}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                spellCheck={false}
              />

              {hasUnsaved && (
                <div className="flex items-center gap-2 text-yellow-400 text-xs">
                  <span className="w-2 h-2 rounded-full bg-yellow-400 inline-block" />
                  Unsaved changes
                </div>
              )}

              {errorMsg && <p className="text-red-400 text-sm">{errorMsg}</p>}

              <div className="flex gap-3">
                <button
                  className="btn-primary"
                  onClick={handleSave}
                  disabled={updateMutation.isPending}
                >
                  {updateMutation.isPending ? 'Saving…' : 'Save'}
                </button>
                <button
                  className="btn-secondary"
                  onClick={handleCancel}
                  disabled={updateMutation.isPending}
                >
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <div className="prose-sm max-w-none text-gray-300 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_strong]:text-white [&_code]:bg-gray-800 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_pre]:bg-gray-800 [&_pre]:p-4 [&_pre]:rounded-lg [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-0.5">
              <ReactMarkdown>{savedValue || '_No voice guide configured yet._'}</ReactMarkdown>
            </div>
          )}

          {successMsg && !editing && (
            <p className="text-green-400 text-sm">{successMsg}</p>
          )}
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Tab 2: Celebrity Tracker
// ---------------------------------------------------------------------------

const ALL_PLATFORMS = ['twitter', 'facebook', 'instagram', 'tiktok']

function CelebrityTrackerTab() {
  const { data: celebrities = [], isLoading } = useCelebrities()
  const addMutation = useAddCelebrity()
  const toggleMutation = useToggleCelebrity()
  const deleteMutation = useDeleteCelebrity()

  // Delete confirm state
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null)

  // Add form state
  const [newName, setNewName] = useState('')
  const [newAliases, setNewAliases] = useState<string[]>([])
  const [aliasInput, setAliasInput] = useState('')
  const [newPlatforms, setNewPlatforms] = useState<string[]>([])
  const [formErrors, setFormErrors] = useState<{ name?: string; aliases?: string }>({})
  const [addSuccess, setAddSuccess] = useState(false)
  const addSuccessTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function commitAlias(raw: string) {
    const trimmed = raw.replace(/,/g, '').trim()
    if (trimmed && !newAliases.includes(trimmed)) {
      setNewAliases((prev) => [...prev, trimmed])
    }
    setAliasInput('')
  }

  function handleAliasKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commitAlias(aliasInput)
    } else if (e.key === 'Backspace' && aliasInput === '' && newAliases.length > 0) {
      setNewAliases((prev) => prev.slice(0, -1))
    }
  }

  function removeAlias(alias: string) {
    setNewAliases((prev) => prev.filter((a) => a !== alias))
  }

  function togglePlatform(platform: string) {
    setNewPlatforms((prev) =>
      prev.includes(platform) ? prev.filter((p) => p !== platform) : [...prev, platform]
    )
  }

  async function handleAddSubmit(e: React.FormEvent) {
    e.preventDefault()
    const errors: { name?: string; aliases?: string } = {}

    // Commit any pending alias text
    const finalAliases = aliasInput.trim()
      ? [...newAliases, aliasInput.trim()]
      : newAliases

    if (!newName.trim()) errors.name = 'Name is required.'
    if (finalAliases.length === 0) errors.aliases = 'At least one search alias is required.'

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors)
      return
    }

    setFormErrors({})
    if (aliasInput.trim()) {
      setNewAliases(finalAliases)
      setAliasInput('')
    }

    try {
      await addMutation.mutateAsync({
        name: newName.trim(),
        search_aliases: finalAliases,
        platforms: newPlatforms,
      })
      setNewName('')
      setNewAliases([])
      setAliasInput('')
      setNewPlatforms([])
      setAddSuccess(true)
      if (addSuccessTimer.current) clearTimeout(addSuccessTimer.current)
      addSuccessTimer.current = setTimeout(() => setAddSuccess(false), 3000)
    } catch {
      // error surfaced via mutation state
    }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return
    await deleteMutation.mutateAsync(deleteTarget.id)
    setDeleteTarget(null)
  }

  return (
    <section className="space-y-6">
      {/* Celebrity list */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="p-6 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonBlock key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : celebrities.length === 0 ? (
          <div className="p-10 text-center text-gray-500 text-sm">
            No celebrities tracked yet.
          </div>
        ) : (
          <ul className="divide-y divide-gray-800">
            {celebrities.map((celeb) => (
              <li
                key={celeb.id}
                className="flex items-center gap-3 px-5 py-4"
              >
                {/* Toggle */}
                <button
                  role="switch"
                  aria-checked={celeb.active}
                  onClick={() =>
                    toggleMutation.mutate({ id: celeb.id, active: !celeb.active })
                  }
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
                    celeb.active ? 'bg-blue-600' : 'bg-gray-700'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      celeb.active ? 'translate-x-4' : 'translate-x-0'
                    }`}
                  />
                </button>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-100 truncate">
                    {celeb.name}
                  </p>
                  {celeb.search_aliases.length > 0 && (
                    <p className="text-xs text-gray-400 truncate">
                      {celeb.search_aliases.join(', ')}
                    </p>
                  )}
                  {celeb.platforms.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {celeb.platforms.map((p) => (
                        <span
                          key={p}
                          className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700"
                        >
                          {p}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Delete */}
                <button
                  onClick={() => setDeleteTarget({ id: celeb.id, name: celeb.name })}
                  className="shrink-0 text-gray-600 hover:text-red-400 transition-colors text-lg leading-none px-1"
                  aria-label={`Delete ${celeb.name}`}
                >
                  &times;
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Add Celebrity form */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Add Celebrity</h3>
        <form onSubmit={handleAddSubmit} className="space-y-4" noValidate>
          {/* Name */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Name</label>
            <input
              type="text"
              className={`input ${formErrors.name ? 'border-red-500' : ''}`}
              placeholder="e.g. Lionel Messi"
              value={newName}
              onChange={(e) => {
                setNewName(e.target.value)
                if (formErrors.name) setFormErrors((prev) => ({ ...prev, name: undefined }))
              }}
            />
            {formErrors.name && (
              <p className="text-red-400 text-xs mt-1">{formErrors.name}</p>
            )}
          </div>

          {/* Search aliases */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Search Aliases{' '}
              <span className="text-gray-600">(press Enter or comma to add)</span>
            </label>
            <div
              className={`flex flex-wrap gap-1.5 p-2 bg-gray-800 border rounded-lg min-h-[42px] ${
                formErrors.aliases ? 'border-red-500' : 'border-gray-700'
              }`}
            >
              {newAliases.map((alias) => (
                <span
                  key={alias}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-700 text-gray-200 text-xs"
                >
                  {alias}
                  <button
                    type="button"
                    onClick={() => removeAlias(alias)}
                    className="text-gray-400 hover:text-white leading-none"
                    aria-label={`Remove alias ${alias}`}
                  >
                    &times;
                  </button>
                </span>
              ))}
              <input
                type="text"
                className="flex-1 bg-transparent outline-none text-sm text-gray-200 placeholder-gray-600 min-w-[120px]"
                placeholder={newAliases.length === 0 ? 'e.g. @messi, messi' : ''}
                value={aliasInput}
                onChange={(e) => {
                  setAliasInput(e.target.value)
                  if (formErrors.aliases) setFormErrors((prev) => ({ ...prev, aliases: undefined }))
                }}
                onKeyDown={handleAliasKeyDown}
                onBlur={() => {
                  if (aliasInput.trim()) commitAlias(aliasInput)
                }}
              />
            </div>
            {formErrors.aliases && (
              <p className="text-red-400 text-xs mt-1">{formErrors.aliases}</p>
            )}
          </div>

          {/* Platforms */}
          <div>
            <label className="block text-xs text-gray-400 mb-2">Platforms</label>
            <div className="flex flex-wrap gap-3">
              {ALL_PLATFORMS.map((platform) => (
                <label
                  key={platform}
                  className="flex items-center gap-2 cursor-pointer select-none"
                >
                  <input
                    type="checkbox"
                    checked={newPlatforms.includes(platform)}
                    onChange={() => togglePlatform(platform)}
                    className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-900"
                  />
                  <span className="text-sm text-gray-300 capitalize">{platform}</span>
                </label>
              ))}
            </div>
          </div>

          {addMutation.isError && (
            <p className="text-red-400 text-sm">
              {addMutation.error instanceof Error
                ? addMutation.error.message
                : 'Failed to add celebrity.'}
            </p>
          )}

          {addSuccess && (
            <p className="text-green-400 text-sm">Celebrity added successfully.</p>
          )}

          <button
            type="submit"
            className="btn-primary"
            disabled={addMutation.isPending}
          >
            {addMutation.isPending ? 'Adding…' : 'Add Celebrity'}
          </button>
        </form>
      </div>

      {/* Delete confirm dialog */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        title="Delete Celebrity"
        message={`Remove "${deleteTarget?.name}" from tracking? This cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </section>
  )
}

// ---------------------------------------------------------------------------
// Tab 3: Learning Log
// ---------------------------------------------------------------------------

function StarPicker({
  value,
  onChange,
}: {
  value?: number
  onChange: (rating: number) => void
}) {
  const [hovered, setHovered] = useState<number | null>(null)
  const display = hovered ?? value ?? 0

  return (
    <div className="flex gap-0.5" onMouseLeave={() => setHovered(null)}>
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          className={`text-lg leading-none transition-colors ${
            star <= display ? 'text-yellow-400' : 'text-gray-600'
          }`}
          onMouseEnter={() => setHovered(star)}
          onClick={() => onChange(star)}
          aria-label={`Rate ${star} star${star !== 1 ? 's' : ''}`}
        >
          {star <= display ? '★' : '☆'}
        </button>
      ))}
    </div>
  )
}

function LearningLogRow({
  entry,
  onRate,
}: {
  entry: LearningLogEntry
  onRate: (entryId: string, rating: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleRate(rating: number) {
    onRate(entry.id, rating)
    setSavedFlash(true)
    if (savedTimer.current) clearTimeout(savedTimer.current)
    savedTimer.current = setTimeout(() => setSavedFlash(false), 1500)
  }

  const truncatedInsight =
    entry.top_insight.length > 80
      ? entry.top_insight.slice(0, 80) + '…'
      : entry.top_insight

  return (
    <>
      {/* Main row */}
      <tr
        className="border-b border-gray-800 hover:bg-gray-800/40 cursor-pointer transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-4 py-3 text-sm text-gray-300 whitespace-nowrap">{entry.week}</td>
        <td className="px-4 py-3 text-sm text-gray-400 text-right whitespace-nowrap">
          {entry.posts_analyzed.toLocaleString()}
        </td>
        <td className="px-4 py-3 text-sm text-gray-300 max-w-xs">
          <span className="hidden sm:block">{truncatedInsight}</span>
          <span className="sm:hidden">{entry.top_insight}</span>
        </td>
        <td
          className="px-4 py-3 whitespace-nowrap"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-2">
            <StarPicker value={entry.fernando_rating} onChange={handleRate} />
            {savedFlash && (
              <span className="text-xs text-green-400 animate-pulse">Saved</span>
            )}
          </div>
        </td>
        <td className="px-4 py-3 text-sm text-gray-400 text-right whitespace-nowrap">
          {entry.model_overrides_this_week}
        </td>
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr className="border-b border-gray-800 bg-gray-900/60">
          <td colSpan={5} className="px-6 py-5">
            <div className="grid sm:grid-cols-2 gap-6 text-sm">
              {entry.confirmed_patterns.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-green-400 uppercase tracking-wider mb-2">
                    Confirmed Patterns
                  </p>
                  <ul className="space-y-1">
                    {entry.confirmed_patterns.map((p, i) => (
                      <li key={i} className="flex gap-2 text-gray-300">
                        <span className="text-green-500 shrink-0">•</span>
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {entry.disproven_assumptions.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2">
                    Disproven Assumptions
                  </p>
                  <ul className="space-y-1">
                    {entry.disproven_assumptions.map((p, i) => (
                      <li key={i} className="flex gap-2 text-gray-300">
                        <span className="text-red-500 shrink-0">•</span>
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {entry.adjustments.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-2">
                    Adjustments
                  </p>
                  <ul className="space-y-1">
                    {entry.adjustments.map((p, i) => (
                      <li key={i} className="flex gap-2 text-gray-300">
                        <span className="text-blue-500 shrink-0">•</span>
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {entry.experiment_for_next_week && (
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                    Experiment for Next Week
                  </p>
                  <p className="text-gray-300 italic">{entry.experiment_for_next_week}</p>
                </div>
              )}

              <div className="sm:col-span-2 text-xs text-gray-500 pt-1">
                Model overrides this week: {entry.model_overrides_this_week} &nbsp;·&nbsp; Generated{' '}
                {new Date(entry.generated_at).toLocaleDateString()}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function LearningLogMobileCard({
  entry,
  onRate,
}: {
  entry: LearningLogEntry
  onRate: (entryId: string, rating: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleRate(rating: number) {
    onRate(entry.id, rating)
    setSavedFlash(true)
    if (savedTimer.current) clearTimeout(savedTimer.current)
    savedTimer.current = setTimeout(() => setSavedFlash(false), 1500)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
      <div
        className="cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <p className="text-xs text-gray-400 font-medium">{entry.week}</p>
        <p className="text-sm text-gray-200 mt-1">{entry.top_insight}</p>
      </div>

      <div className="flex items-center gap-3">
        <StarPicker value={entry.fernando_rating} onChange={handleRate} />
        {savedFlash && (
          <span className="text-xs text-green-400 animate-pulse">Saved</span>
        )}
        <span className="ml-auto text-xs text-gray-500">
          {entry.posts_analyzed.toLocaleString()} posts
        </span>
      </div>

      {expanded && (
        <div className="border-t border-gray-800 pt-3 space-y-4 text-sm">
          {entry.confirmed_patterns.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-green-400 uppercase tracking-wider mb-1">
                Confirmed Patterns
              </p>
              <ul className="space-y-1">
                {entry.confirmed_patterns.map((p, i) => (
                  <li key={i} className="flex gap-2 text-gray-300">
                    <span className="text-green-500 shrink-0">•</span>{p}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {entry.disproven_assumptions.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-1">
                Disproven Assumptions
              </p>
              <ul className="space-y-1">
                {entry.disproven_assumptions.map((p, i) => (
                  <li key={i} className="flex gap-2 text-gray-300">
                    <span className="text-red-500 shrink-0">•</span>{p}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {entry.adjustments.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-1">
                Adjustments
              </p>
              <ul className="space-y-1">
                {entry.adjustments.map((p, i) => (
                  <li key={i} className="flex gap-2 text-gray-300">
                    <span className="text-blue-500 shrink-0">•</span>{p}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {entry.experiment_for_next_week && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
                Experiment for Next Week
              </p>
              <p className="text-gray-300 italic">{entry.experiment_for_next_week}</p>
            </div>
          )}
          <p className="text-xs text-gray-500">
            Overrides: {entry.model_overrides_this_week} &nbsp;·&nbsp; Generated{' '}
            {new Date(entry.generated_at).toLocaleDateString()}
          </p>
        </div>
      )}
    </div>
  )
}

function LearningLogTab() {
  const { data: entries = [], isLoading } = useLearningLog(20)
  const rateMutation = useRateLearningEntry()

  function handleRate(entryId: string, rating: number) {
    rateMutation.mutate({ entryId, rating })
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonBlock key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-10 text-center text-gray-500 text-sm">
        No learning log entries yet. Entries are generated weekly after the pipeline has been
        running for at least a week.
      </div>
    )
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden sm:block bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-800/50">
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Week
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right">
                  Posts
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Top Insight
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  Rating
                </th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right">
                  Overrides
                </th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <LearningLogRow key={entry.id} entry={entry} onRate={handleRate} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Mobile card list */}
      <div className="sm:hidden space-y-3">
        {entries.map((entry) => (
          <LearningLogMobileCard key={entry.id} entry={entry} onRate={handleRate} />
        ))}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Tab 4: Scoring Model
// ---------------------------------------------------------------------------

function FeatureBar({ name, importance }: { name: string; importance: number }) {
  const pct = Math.round(importance * 100)
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-gray-400 w-40 shrink-0 truncate font-mono text-xs">{name}</span>
      <div className="flex-1 bg-gray-800 rounded-full h-3 overflow-hidden">
        <div
          className="h-full bg-blue-500 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-gray-400 text-xs w-8 text-right">{pct}%</span>
    </div>
  )
}

function ScoringModelTab() {
  const { data: status, isLoading: statusLoading } = useModelStatus()
  const { data: postCount, isLoading: countLoading } = usePostCount()
  const { data: overrides = [], isLoading: overridesLoading } = useModelOverrides(20)
  const trainMutation = useTriggerTraining()
  const [queuedFlash, setQueuedFlash] = useState(false)
  const queuedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleTrain() {
    trainMutation.mutate(undefined, {
      onSuccess: () => {
        setQueuedFlash(true)
        if (queuedTimer.current) clearTimeout(queuedTimer.current)
        queuedTimer.current = setTimeout(() => setQueuedFlash(false), 3000)
      },
    })
  }

  function r2Color(r2: number) {
    if (r2 >= 0.5) return 'text-green-400'
    if (r2 >= 0.3) return 'text-yellow-400'
    return 'text-red-400'
  }

  function divergenceColor(d: number) {
    if (d > 0.5) return 'text-red-400'
    if (d > 0.3) return 'text-orange-400'
    return 'text-gray-300'
  }

  return (
    <section className="space-y-6">
      {/* Model Status card */}
      <div
        className={`bg-gray-900 border rounded-xl p-6 ${
          status?.has_active_model ? 'border-green-700' : 'border-gray-800'
        }`}
      >
        <h2 className="text-lg font-semibold text-gray-300 mb-4">Model Status</h2>

        {statusLoading && (
          <div className="space-y-3">
            <SkeletonBlock className="h-4 w-1/3" />
            <SkeletonBlock className="h-4 w-2/3" />
            <SkeletonBlock className="h-4 w-1/2" />
          </div>
        )}

        {!statusLoading && !status?.has_active_model && (
          <p className="text-gray-500 text-sm">
            No model trained yet. Train when 200+ posts are available.
          </p>
        )}

        {!statusLoading && status?.has_active_model && (
          <div className="space-y-4">
            {/* Header badges */}
            <div className="flex items-center gap-3 flex-wrap">
              <span className="px-2.5 py-1 rounded-lg bg-gray-800 text-gray-200 text-sm font-mono font-semibold">
                {status.model_version}
              </span>
              <span className="px-2.5 py-1 rounded-full bg-green-900/60 border border-green-700 text-green-400 text-xs font-semibold">
                Active
              </span>
            </div>

            {/* Stats grid */}
            <div className="grid sm:grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">R² Score</p>
                <p className={`text-xl font-bold ${r2Color(status.r_squared ?? 0)}`}>
                  {status.r_squared?.toFixed(3) ?? '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Training Set</p>
                <p className="text-xl font-bold text-gray-200">
                  {status.training_set_size?.toLocaleString() ?? '—'} posts
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Trained At</p>
                <p className="text-gray-300">
                  {status.trained_at
                    ? new Date(status.trained_at).toLocaleString()
                    : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">GCS Path</p>
                <p className="text-gray-500 font-mono text-xs break-all">
                  {status.gcs_path ?? '—'}
                </p>
              </div>
            </div>

            {/* Feature importance bars */}
            {status.top_features && status.top_features.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">
                  Feature Importance
                </p>
                <div className="space-y-2">
                  {status.top_features.map((f) => (
                    <FeatureBar key={f.name} name={f.name} importance={f.importance} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Training controls card */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-300 mb-4">Training Controls</h2>

        {countLoading && (
          <div className="space-y-3">
            <SkeletonBlock className="h-4 w-2/3" />
            <SkeletonBlock className="h-8 w-32" />
          </div>
        )}

        {!countLoading && postCount && (
          <div className="space-y-4">
            {/* Progress bar */}
            <div>
              <div className="flex justify-between text-sm mb-1.5">
                <span className="text-gray-300">
                  {postCount.eligible_posts.toLocaleString()} / {postCount.threshold.toLocaleString()} posts eligible
                </span>
                <span className="text-gray-500 text-xs">
                  {Math.min(100, Math.round((postCount.eligible_posts / postCount.threshold) * 100))}%
                </span>
              </div>
              <div className="h-2.5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, (postCount.eligible_posts / postCount.threshold) * 100)}%`,
                  }}
                />
              </div>
            </div>

            {/* Train button */}
            {postCount.ready_to_train ? (
              <button
                className="btn-primary"
                onClick={handleTrain}
                disabled={trainMutation.isPending}
              >
                {trainMutation.isPending ? 'Queueing…' : 'Re-train Model'}
              </button>
            ) : (
              <button className="btn-primary opacity-50 cursor-not-allowed" disabled>
                Need {postCount.threshold - postCount.eligible_posts} more posts to train
              </button>
            )}

            {queuedFlash && (
              <p className="text-green-400 text-sm">Training queued...</p>
            )}

            {trainMutation.isError && (
              <p className="text-red-400 text-sm">
                {trainMutation.error instanceof Error
                  ? trainMutation.error.message
                  : 'Failed to queue training.'}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Override Log card */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-gray-300">Fernando's Overrides (last 20)</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            These are posts where Fernando's rating diverged significantly from the model's prediction.
          </p>
        </div>

        {overridesLoading && (
          <div className="p-6 space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <SkeletonBlock key={i} className="h-10 w-full" />
            ))}
          </div>
        )}

        {!overridesLoading && overrides.length === 0 && (
          <div className="p-10 text-center text-gray-500 text-sm">
            No overrides logged yet.
          </div>
        )}

        {!overridesLoading && overrides.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-800/50">
                  <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider whitespace-nowrap">
                    Logged At
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    Post ID
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right whitespace-nowrap">
                    Fernando
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right whitespace-nowrap">
                    Predicted
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right whitespace-nowrap">
                    Divergence
                  </th>
                </tr>
              </thead>
              <tbody>
                {overrides.map((rec, i) => (
                  <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/30 transition-colors">
                    <td className="px-4 py-3 text-sm text-gray-400 whitespace-nowrap">
                      {new Date(rec.logged_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-300 font-mono">
                      {rec.post_id.length > 12 ? rec.post_id.slice(0, 12) + '…' : rec.post_id}
                    </td>
                    <td className="px-4 py-3 text-sm text-yellow-400 text-right whitespace-nowrap">
                      {'★'.repeat(rec.fernando_rating)}{'☆'.repeat(5 - rec.fernando_rating)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-300 text-right whitespace-nowrap">
                      {rec.predicted_engagement.toFixed(2)}
                    </td>
                    <td className={`px-4 py-3 text-sm text-right whitespace-nowrap font-semibold ${divergenceColor(rec.divergence)}`}>
                      {rec.divergence.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('voice-guide')

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <div className="bg-gray-900/50 border-b border-gray-800 px-4 sm:px-6 py-6 sticky top-0 z-20">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100">Settings</h1>
        </div>
      </div>

      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8">
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
        {activeTab === 'voice-guide' && <VoiceGuideTab />}
        {activeTab === 'celebrity-tracker' && <CelebrityTrackerTab />}
        {activeTab === 'learning-log' && <LearningLogTab />}
        {activeTab === 'scoring-model' && <ScoringModelTab />}
      </main>
    </div>
  )
}
