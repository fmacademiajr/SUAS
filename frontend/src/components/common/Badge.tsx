interface BadgeProps {
  variant: 'urgency-hot' | 'urgency-warm' | 'urgency-routine' | 'strategy' | 'status' | 'neutral'
  children: React.ReactNode
  className?: string
}

const variantClasses: Record<BadgeProps['variant'], string> = {
  'urgency-hot': 'bg-red-900/60 text-red-300 border border-red-700',
  'urgency-warm': 'bg-orange-900/60 text-orange-300 border border-orange-700',
  'urgency-routine': 'bg-gray-800 text-gray-400 border border-gray-700',
  strategy: 'bg-blue-900/60 text-blue-300 border border-blue-700',
  status: 'bg-green-900/60 text-green-300 border border-green-700',
  neutral: 'bg-gray-800 text-gray-300 border border-gray-700',
}

export function Badge({ variant, children, className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${variantClasses[variant]} ${className}`}>
      {children}
    </span>
  )
}
