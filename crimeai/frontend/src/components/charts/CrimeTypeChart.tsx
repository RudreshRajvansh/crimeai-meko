import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useThemeColors } from '@/lib/theme'

const COLORS = ['#1f6feb','#3fb950','#d29922','#f85149','#8957e5','#39d353','#ff7b72','#88c0d0']

interface CrimeTypeChartProps {
  data: Record<string, number>
}

export default function CrimeTypeChart({ data }: CrimeTypeChartProps) {
  const theme = useThemeColors()
  const chartData = Object.entries(data)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8)
    .map(([name, value]) => ({
      name: name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      value,
    }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={85}
          paddingAngle={2}
          dataKey="value"
        >
          {chartData.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="transparent" />
          ))}
        </Pie>
        <Tooltip
          contentStyle={theme.tooltip}
          itemStyle={{ color: theme.text }}
        />
        <Legend
          wrapperStyle={{ fontSize: '11px', color: theme.muted }}
          iconSize={8}
          iconType="circle"
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
