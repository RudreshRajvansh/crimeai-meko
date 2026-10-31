import { useEffect } from 'react'
import { useMap } from 'react-leaflet'

/**
 * Leaflet measures its container once. When a panel opens, a sidebar collapses or the tab was hidden at
 * mount, the map keeps a stale (often zero) size and later flyTo / fitBounds produce NaN coordinates.
 * This keeps Leaflet's idea of the size in sync with the DOM.
 */
export function AutoResize() {
  const map = useMap()
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }))
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}
