/** Categorical colours for link-analysis node types and crime categories, drawn from the theme tokens. */
export const NODE_COLORS: Record<string, string> = {
  crime: '#58a6ff',
  vehicle: '#d29922',
  phone: '#bc8cff',
  upi: '#3fb950',
  account: '#39c5cf',
  series: '#f85149',
}

export const NODE_LABELS: Record<string, string> = {
  crime: 'Case',
  vehicle: 'Vehicle',
  phone: 'Phone',
  upi: 'UPI ID',
  account: 'Bank account',
  series: 'Crime series',
}

export const CRIME_COLORS: Record<string, string> = {
  theft: '#58a6ff',
  vehicle_theft: '#79c0ff',
  chain_snatching: '#ff7b72',
  robbery: '#f85149',
  burglary: '#d29922',
  assault: '#ffa657',
  fraud: '#3fb950',
  cybercrime: '#56d364',
  domestic_violence: '#bc8cff',
  murder: '#ff4d4d',
}

/** Light mode uses the deeper token colours; dark mode keeps the brighter tints that read on near-black. */
export const HIGHLIGHT_STYLES: Record<string, string> = {
  crime: 'bg-severity-high/15 text-severity-high dark:text-[#ffa198] decoration-severity-high',
  weapon: 'bg-severity-medium/15 text-severity-medium dark:text-[#e3b341] decoration-severity-medium',
  legal: 'bg-accent-purple/20 text-accent-purple dark:text-[#d2a8ff] decoration-accent-purple',
  place: 'bg-accent-blue/15 text-accent-blue dark:text-[#79c0ff] decoration-accent-blue',
  vehicle: 'bg-[#d29922]/15 text-[#9a6700] dark:text-[#e3b341] decoration-[#d29922]',
  phone: 'bg-[#bc8cff]/15 text-[#8250df] dark:text-[#d2a8ff] decoration-[#bc8cff]',
  upi: 'bg-severity-low/15 text-severity-low dark:text-[#7ee787] decoration-severity-low',
  amount: 'bg-[#39c5cf]/15 text-[#0e7490] dark:text-[#76e3ea] decoration-[#39c5cf]',
}

/** Crime types the platform records, in filter order. */
export const CRIME_TYPES = Object.keys(CRIME_COLORS)

export const crimeColor = (type: string) => CRIME_COLORS[type] ?? '#8b949e'
