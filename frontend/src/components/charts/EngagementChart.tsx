import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { useEngagementData } from '../../api/dashboard'

interface EngagementChartProps {
  days?: number
}

export function EngagementChart({ days = 30 }: EngagementChartProps) {
  const { data, isLoading } = useEngagementData(days)

  if (isLoading) {
    return (
      <div className="h-[280px] w-full bg-gray-800 rounded-lg animate-pulse" />
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="h-[280px] w-full flex items-center justify-center bg-gray-900 rounded-lg">
        <p className="text-gray-400">No engagement data yet</p>
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#9ca3af', fontSize: 12 }}
          axisLine={{ stroke: '#374151' }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: '#9ca3af', fontSize: 12 }}
          axisLine={{ stroke: '#374151' }}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#111827',
            border: '1px solid #374151',
            borderRadius: '6px',
            color: '#f9fafb',
          }}
          labelStyle={{ color: '#9ca3af' }}
        />
        <Legend
          wrapperStyle={{ color: '#9ca3af', fontSize: 12, paddingTop: 8 }}
        />
        <Line
          type="monotone"
          dataKey="likes"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: '#3b82f6' }}
        />
        <Line
          type="monotone"
          dataKey="comments"
          stroke="#22c55e"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: '#22c55e' }}
        />
        <Line
          type="monotone"
          dataKey="shares"
          stroke="#a855f7"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: '#a855f7' }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
