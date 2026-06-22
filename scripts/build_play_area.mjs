// Rebuilds src/data/play-area.geojson.json = the in-play counties' full legal
// (water-inclusive) boundaries MINUS the Pacific Ocean, with the offshore Farallon
// Islands dropped. Result = land + bay only (no open ocean), still county-bounded.
//
// Inputs (kept under scripts/ so the build is reproducible):
//   scripts/play_area_src_water.geojson.json  -> Census TIGERweb water-inclusive counties
//   scripts/pacific_ocean.geojson.json        -> Census TIGERweb 'Pacific Ocean' areal hydro
// Run: node scripts/build_play_area.mjs
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import polygonClipping from 'polygon-clipping'

const dir = path.dirname(fileURLToPath(import.meta.url))
const read = (p) => JSON.parse(fs.readFileSync(path.join(dir, p), 'utf8'))

const counties = read('play_area_src_water.geojson.json')
const pacific = read('pacific_ocean.geojson.json')

// Anything west of this longitude is the offshore Farallon Islands -> drop it.
const FARALLON_LON = -122.7

const toMulti = (geom) =>
  geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates

const round = (c) =>
  typeof c[0] === 'number' ? [+c[0].toFixed(5), +c[1].toFixed(5)] : c.map(round)

const polyMaxLon = (poly) => Math.max(...poly[0].map((p) => p[0]))

// Union all Pacific Ocean polygons into one clip geometry.
const pacificMulti = polygonClipping.union(
  ...pacific.features.map((f) => toMulti(f.geometry)),
)

const features = counties.features.map((f) => {
  // Drop offshore island polygons (Farallones) before subtracting the ocean.
  const polys = toMulti(f.geometry).filter((poly) => polyMaxLon(poly) > FARALLON_LON)
  const diff = polygonClipping.difference(polys, pacificMulti)
  return {
    type: 'Feature',
    properties: { name: f.properties.name },
    geometry: { type: 'MultiPolygon', coordinates: round(diff) },
  }
})

const out = { type: 'FeatureCollection', features }
const outPath = path.join(dir, '..', 'src', 'data', 'play-area.geojson.json')
fs.writeFileSync(outPath, JSON.stringify(out))
console.log('wrote', outPath, fs.statSync(outPath).size, 'bytes')
for (const f of features) {
  let mnx = 999, mxx = -999
  const w = (c) => {
    if (typeof c[0] === 'number') { mnx = Math.min(mnx, c[0]); mxx = Math.max(mxx, c[0]) }
    else c.forEach(w)
  }
  w(f.geometry.coordinates)
  console.log(`  ${f.properties.name.padEnd(15)} lon ${mnx.toFixed(3)}..${mxx.toFixed(3)}`)
}
