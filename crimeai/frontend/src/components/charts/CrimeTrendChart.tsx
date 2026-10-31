import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'
import { monthName } from '@/utils'
import { useThemeColors } from '@/lib/theme'

interface CrimeTrendChartProps {
  data: Array<{ year: number; month: number; count: number }>
}

export default function CrimeTrendChart({ data }: CrimeTrendChartProps) {
  const theme = useThemeColors()
  const chartData = data.map((d) => ({
    label: `${monthName(d.month)} '${String(d.year).slice(2)}`,
    crimes: d.count,
  }))

  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="crimeGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#1f6feb" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#1f6feb" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: theme.axis, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: theme.axis, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={theme.tooltip}
          itemStyle={{ color: theme.text }}
        />
        <Area
          type="monotone"
          dataKey="crimes"
          stroke="#1f6feb"
          strokeWidth={2}
          fill="url(#crimeGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
