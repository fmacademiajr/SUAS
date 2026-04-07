import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { useScoreDistribution } from '../../api/dashboard'

interface ScoreDistributionProps {
  days?: number
}

export function ScoreDistribution({ days = 30 }: ScoreDistributionProps) {
  const { data, isLoading } = useScoreDistribution(days)

  if (isLoading) {
    return (
      <div className="h-[280px] w-full bg-gray-800 rounded-lg animate-pulse" />
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="h-[280px] w-full flex items-center justify-center bg-gray-900 rounded-lg">
        <p className="text-gray-400">No score data yet</p>
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
        <XAxis
          dataKey="score"
          tick={{ fill: '#9ca3af', fontSize: 12 }}
          axisLine={{ stroke: '#374151' }}
          tickLine={false}
          label={{ value: 'Alignment Score', position: 'insideBottom', offset: -2, fill: '#6b7280', fontSize: 11 }}
        />
        <YAxis
          tick={{ fill: '#9ca3af', fontSize: 12 }}
          axisLine={{ stroke: '#374151' }}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#111827',
            border: '1px solid #374151',
            borderRadius: '6px',
            color: '#f9fafb',
          }}
          labelStyle={{ color: '#9ca3af' }}
          formatter={(value: number) => [value, 'Posts']}
          labelFormatter={(label) => `Score: ${label}`}
        />
        <Bar dataKey="count" fill="#3b82f6" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
