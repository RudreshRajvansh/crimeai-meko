import { Toaster } from 'react-hot-toast'
import { useThemeColors } from '@/lib/theme'

export default function ThemedToaster() {
  const theme = useThemeColors()
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        style: { ...theme.tooltip, fontSize: '13px' },
        success: { iconTheme: { primary: theme.c('severity-low'), secondary: theme.c('severity-low-bg') } },
        error: { iconTheme: { primary: theme.c('severity-high'), secondary: theme.c('severity-high-bg') } },
      }}
    />
  )
}
