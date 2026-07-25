import json,urllib.request,urllib.parse,time,sys
Q='[out:json][timeout:240];way["natural"="coastline"](33.60,-118.80,34.45,-117.55);out geom;'
hosts=["https://overpass-api.de/api/interpreter","https://overpass.kumi.systems/api/interpreter","https://maps.mail.ru/osm/tools/overpass/api/interpreter","https://overpass.openstreetmap.ru/api/interpreter"]
d=None
for attempt in range(6):
    for host in hosts:
        try:
            req=urllib.request.Request(host,data=urllib.parse.urlencode({'data':Q}).encode(),headers={'User-Agent':'jetlag-la'})
            d=json.load(urllib.request.urlopen(req,timeout=260))
            print('ok',host,file=sys.stderr);break
        except Exception as e:
            print('fail',host,str(e)[:60],file=sys.stderr)
    if d:break
    time.sleep(10)
if not d: sys.exit('all overpass hosts failed')
feats=[]
for el in d['elements']:
    if el.get('type')=='way' and el.get('geometry'):
        coords=[[p['lon'],p['lat']] for p in el['geometry']]
        if len(coords)>=2:
            feats.append({"type":"Feature","properties":{"id":el['id']},"geometry":{"type":"LineString","coordinates":coords}})
json.dump({"type":"FeatureCollection","features":feats},open('measure_src/osm_coastline_la.geojson','w'))
print('ways',len(feats))
