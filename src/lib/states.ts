import type { LatLng } from '../types'
import { statesData } from '../data/regions'
import { polysByName, pointInPolys, type NamedPolys } from './polys'

// State (1st admin division) polygons, used by the "Matching — state" question
// on a map that spans more than one: the seeker's state comes from their
// coordinate, each station carries the state its dot sits in (baked by
// build_attributes.py off these same polygons), and the eliminated-area shading
// is this polygon's inside/outside. A single-state map ships no such file — the
// layer is empty and the question stays log-only (see MULTI_STATE in regions).

const STATES: Record<string, NamedPolys> = statesData ? polysByName(statesData) : {}

export function stateNames(): string[] {
  return Object.keys(STATES)
}

/** polygon-clipping-ready geometry (a MultiPolygon) for one state, or [] if none. */
export function stateGeom(name: string): NamedPolys {
  return STATES[name] ?? []
}

/**
 * The state containing `p`, or null if the map has no state layer / `p` is off
 * it. Neighbouring states are kept in the layer (not just the ones holding
 * stations) so a point just over the line still names its real state instead of
 * reading as "nowhere".
 */
export function stateAt(p: LatLng): string | null {
  for (const [name, polys] of Object.entries(STATES)) {
    if (pointInPolys(p, polys)) return name
  }
  return null
}
