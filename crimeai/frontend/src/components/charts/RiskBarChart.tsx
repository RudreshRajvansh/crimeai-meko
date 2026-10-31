import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { riskColor } from '@/utils'
import { useThemeColors } from '@/lib/theme'

interface RiskBarChartProps {
  data: Record<string, { score: number; level: string }>
}

export default function RiskBarChart({ data }: RiskBarChartProps) {
  const theme = useThemeColors()
  const chartData = Object.entries(data)
    .sort(([, a], [, b]) => b.score - a.score)
    .slice(0, 10)
    .map(([district, info]) => ({ district, score: Math.round(info.score), level: info.level }))

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 8, top: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={{ fill: theme.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis
          type="category"
          dataKey="district"
          tick={{ fill: theme.axis, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={110}
        />
        <Tooltip
          contentStyle={theme.tooltip}
          itemStyle={{ color: theme.text }}
          formatter={(v: number) => [`${v}/100`, 'Risk Score']}
        />
        <Bar dataKey="score" radius={[0, 3, 3, 0]}>
          {chartData.map((entry, i) => (
            <Cell key={i} fill={riskColor(entry.score)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
