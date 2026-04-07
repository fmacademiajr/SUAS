import { useState, useEffect } from 'react'
import { useTriggerPipeline } from '../../api/pipeline'
import { usePipelineStatus } from '../../api/pipeline'
import { Loader2 } from 'lucide-react'

interface TriggerButtonProps {
  className?: string
}

export function TriggerButton({ className = '' }: TriggerButtonProps) {
  const trigger = useTriggerPipeline()
  const { data: status } = usePipelineStatus()
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const isLoading = trigger.isPending || status?.running

  useEffect(() => {
    if (trigger.isSuccess) {
      setSuccessMessage('Triggered!')
      setErrorMessage(null)
      const timer = setTimeout(() => setSuccessMessage(null), 2000)
      return () => clearTimeout(timer)
    }
  }, [trigger.isSuccess])

  useEffect(() => {
    if (trigger.isError) {
      const errorText = trigger.error instanceof Error ? trigger.error.message : 'Failed to trigger pipeline'
      setErrorMessage(errorText)
      const timer = setTimeout(() => setErrorMessage(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [trigger.isError, trigger.error])

  const handleClick = () => {
    trigger.mutate({ slot: 'manual', dryRun: false })
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={handleClick}
        disabled={isLoading}
        className={`btn-primary ${className}`}
      >
        {isLoading ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            <span>Running...</span>
          </>
        ) : (
          'Run Pipeline'
        )}
      </button>
      {successMessage && (
        <span className="text-green-400 text-sm font-medium animate-fade-out">
          {successMessage}
        </span>
      )}
      {errorMessage && (
        <span className="text-red-400 text-sm font-medium">
          {errorMessage}
        </span>
      )}
    </div>
  )
}
