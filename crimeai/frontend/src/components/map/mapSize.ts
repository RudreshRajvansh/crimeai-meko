import type L from 'leaflet'

/** False while the map container has no layout size; flyTo / fitBounds then compute NaN coordinates. */
export function hasSize(map: L.Map): boolean {
  const size = map.getSize()
  return size.x > 0 && size.y > 0
}
