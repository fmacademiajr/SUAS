import { usePipelineStatus } from '../../api/pipeline'
import { formatDistanceToNow } from 'date-fns'
import { toZonedTime, format } from 'date-fns-tz'

export function PipelineStatusBar() {
  const { data } = usePipelineStatus()

  if (!data) return null

  const running = data.running
  const lastRunAt = data.last_run_at ? new Date(data.last_run_at) : null
  const hasError = data.last_error !== null

  const getNextRunTime = () => {
    if (!lastRunAt) return null
    // Assuming hourly runs, next run is ~1 hour after last run
    const nextRun = new Date(lastRunAt.getTime() + 60 * 60 * 1000)
    const manilaTime = toZonedTime(nextRun, 'Asia/Manila')
    return format(manilaTime, 'HH:mm', { timeZone: 'Asia/Manila' })
  }

  const nextRunTime = getNextRunTime()

  return (
    <div className="w-full bg-gray-800/50 border-b border-gray-700 px-4 py-2 flex items-center gap-4 text-sm">
      {running ? (
        <>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            <span className="text-gray-300">Running...</span>
          </div>
        </>
      ) : hasError ? (
        <>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-red-500 rounded-full" />
            <span className="text-gray-300">Last run failed</span>
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-gray-500 rounded-full" />
            <span className="text-gray-400">
              {lastRunAt ? `Last run: ${formatDistanceToNow(lastRunAt, { addSuffix: true })}` : 'No runs yet'}
            </span>
          </div>
        </>
      )}
      {nextRunTime && (
        <span className="text-gray-500 text-xs">
          Next: {nextRunTime} PHT
        </span>
      )}
    </div>
  )
}
