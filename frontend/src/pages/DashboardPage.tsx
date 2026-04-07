import { useDashboardStats } from '../api/dashboard'
import { usePipelineStatus } from '../api/pipeline'
import { EngagementChart } from '../components/charts/EngagementChart'
import { ScoreDistribution } from '../components/charts/ScoreDistribution'

interface StatCardProps {
  label: string
  value: number | string
  loading: boolean
}

function StatCard({ label, value, loading }: StatCardProps) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col gap-1">
      <span className="text-gray-400 text-xs font-medium uppercase tracking-wide">{label}</span>
      {loading ? (
        <div className="h-8 w-20 bg-gray-800 rounded animate-pulse mt-1" />
      ) : (
        <span className="text-white text-2xl font-bold">{value}</span>
      )}
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <h2 className="text-gray-300 text-sm font-semibold mb-4">{title}</h2>
      {children}
    </div>
  )
}

export function DashboardPage() {
  const { data: stats, isLoading: statsLoading, isError: statsError } = useDashboardStats()
  const { data: pipeline, isLoading: pipelineLoading } = usePipelineStatus()

  const loading = statsLoading || pipelineLoading

  if (statsError) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-red-400 text-sm">Failed to load dashboard stats. Please try again.</p>
      </div>
    )
  }

  const counts = stats?.post_counts

  const statCards = [
    {
      label: 'Total Posts',
      value: counts
        ? Object.values(counts).reduce((sum, n) => sum + n, 0)
        : 0,
    },
    {
      label: 'Pending Review',
      value: counts?.pending_review ?? 0,
    },
    {
      label: 'Published Today',
      value: counts?.published ?? 0,
    },
    {
      label: 'Approved',
      value: counts?.approved ?? 0,
    },
    {
      label: 'Metrics Synced',
      value: counts?.metrics_synced ?? 0,
    },
    {
      label: 'Pipeline Running',
      value: pipeline?.running ? 'Yes' : 'No',
    },
  ]

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-white text-2xl font-bold">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-0.5">Pipeline and post overview</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {statCards.map((card) => (
          <StatCard key={card.label} label={card.label} value={card.value} loading={loading} />
        ))}
      </div>

      {/* Charts grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Engagement (Last 7 Days)">
          <EngagementChart days={7} />
        </ChartCard>
        <ChartCard title="Score Distribution">
          <ScoreDistribution />
        </ChartCard>
      </div>
    </div>
  )
}
