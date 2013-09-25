import time, json, requests, os, sys
from lxml import etree
from datetime import datetime
from sys import argv
from sets import Set
from ModestMaps.Geo import MercatorProjection, Location, Coordinate
import pystache

dir_path = os.path.dirname(os.path.abspath(__file__))

def extractosc(): os.system('gunzip -f change.osc.gz')

def getstate():
    r = requests.get('http://planet.openstreetmap.org/replication/day/state.txt')
    return r.text.split('\n')[1].split('=')[1]

def getosc(state):
    stateurl = 'http://planet.openstreetmap.org/replication/day/000/000/%s.osc.gz' % state
    sys.stderr.write('downloading %s...\n' % stateurl)
    os.system('wget --quiet %s -O change.osc.gz' % stateurl)

def get_bbox(poly):
    box = [200, 200, -200, -200]
    for p in poly:
        if p[0] < box[0]: box[0] = p[0]
        if p[0] > box[2]: box[2] = p[0]
        if p[1] < box[1]: box[1] = p[1]
        if p[1] > box[3]: box[3] = p[1]
    return box

def point_in_box(x, y, box):
    return x > box[0] and x < box[2] and y > box[1] and y < box[3]

def point_in_poly(x, y, poly):
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in xrange(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def pip(lon, lat):
    if(geotype == 'MultiPolygon'):
        for poly in nypoly:
            if(point_in_poly(lon, lat, poly)):
                return true
        return false

    elif(geotype == 'Polygon'):
        return point_in_poly(lon, lat, nypoly)

def coordAverage(c1, c2): return (float(c1) + float(c2)) / 2

def getExtent(s):
    extent = {}
    m = MercatorProjection(0)

    points = [[float(s['max_lat']), float(s['min_lon'])], [float(s['min_lat']), float(s['max_lon'])]]
    
    if (points[0][0] - points[1][0] == 0) or (points[1][1] - points[0][1] == 0):
        extent['lat'] = points[0][0]
        extent['lon'] = points[1][1]
        extent['zoom'] = 18
    else:
        i = float('inf')
         
        w = 800
        h = 600
         
        tl = [min(map(lambda x: x[0], points)), min(map(lambda x: x[1], points))]
        br = [max(map(lambda x: x[0], points)), max(map(lambda x: x[1], points))]
         
        c1 = m.locationCoordinate(Location(tl[0], tl[1]))
        c2 = m.locationCoordinate(Location(br[0], br[1]))
         
        while (abs(c1.column - c2.column) * 256.0) < w and (abs(c1.row - c2.row) * 256.0) < h:
            c1 = c1.zoomBy(1)
            c2 = c2.zoomBy(1)
         
        center = m.coordinateLocation(Coordinate(
            (c1.row + c2.row) / 2,
            (c1.column + c2.column) / 2,
            c1.zoom))
        
        extent['lat'] = center.lat
        extent['lon'] = center.lon
        if c1.zoom > 18:
            extent['zoom'] = 18
        else:
            extent['zoom'] = c1.zoom
        
    return extent

def hasbuildingtag(n):
    return n.find(".//tag[@k='building']") is not None
    
def getaddresstags(tags):
    addr_tags = []
    for t in tags:
        key = t.get('k')
        if key.split(':')[0] == 'addr':
            addr_tags.append(t.attrib)
    return addr_tags
    
def hasaddresschange(gid, addr, version, elem):
    url = 'http://api.openstreetmap.org/api/0.6/%s/%s/history' % (elem, gid)
    r = requests.get(url)
    if not r.text: return False
    e = etree.fromstring(r.text.encode('utf-8'))
    previous_elem = e.find(".//%s[@version='%s']" % (elem, (version - 1)))
    previous_addr = getaddresstags(previous_elem.findall(".//tag[@k]"))
    if len(addr) != len(previous_addr):
        return True
    else:
        for a in addr:
            if a not in previous_addr: return True
    return False

def loadChangeset(changeset):
    changeset['wids'] = list(changeset['wids'])
    changeset['nids'] = list(changeset['nids'])
    changeset['addr_chg_nd'] = list(changeset['addr_chg_nd'])
    changeset['addr_chg_way'] = list(changeset['addr_chg_way'])
    url = 'http://api.openstreetmap.org/api/0.6/changeset/%s' % changeset['id']
    r = requests.get(url)
    if not r.text: return changeset
    t = etree.fromstring(r.text.encode('utf-8'))
    changeset['details'] = dict(t.find('.//changeset').attrib)
    comment = t.find(".//tag[@k='comment']")
    created_by = t.find(".//tag[@k='created_by']")
    if comment is not None: changeset['comment'] = comment.get('v')
    if created_by is not None: changeset['created_by'] = created_by.get('v')
    extent = getExtent(changeset['details'])
    changeset['map_img'] = 'http://api.tiles.mapbox.com/v3/lxbarth.map-lxoorpwz/%s,%s,%s/300x225.png' % (extent['lon'], extent['lat'], extent['zoom'])
    changeset['map_link'] = 'http://www.openstreetmap.org/?lat=%s&lon=%s&zoom=%s&layers=M' % (extent['lon'], extent['lat'], extent['zoom'])
    return changeset

ny = json.load(open(os.path.join(dir_path,'nyc.geojson')))

nypoly = [ ]
geotype = 'Polygon'
if(nypoly['features'][0]['geometry']['type'] == 'Polygon'):
    geotype = 'Polygon'
    nypoly = ny['features'][0]['geometry']['coordinates'][0]
elif(nypoly['features'][0]['geometry']['type'] == 'MultiPolygon'):
    geotype = 'MultiPolygon'
    for poly in ny['features'][0]['geometry']['coordinates']:
        nypoly.append(poly[0])

nybox = get_bbox(nypoly)
sys.stderr.write('getting state\n')
state = getstate()
getosc(state)
sys.stderr.write('extracting\n')
extractosc()

sys.stderr.write('reading file\n')

nids = Set()
changesets = {}
stats = {}
stats['buildings'] = 0
stats['addresses'] = 0

def addchangeset(el, cid):
    if not changesets.get(cid, False):
        changesets[cid] = {
            'id': cid,
            'user': el.get('user'),
            'uid': el.get('uid'),
            'wids': Set(),
            'nids': Set(),
            'addr_chg_way': Set(),
            'addr_chg_nd': Set()
        }

sys.stderr.write('finding points\n')

# Find nodes that fall within specified area
context = iter(etree.iterparse('change.osc', events=('start', 'end')))
event, root = context.next()
for event, n in context:
    if event == 'start':
        if n.tag == 'node':
            lon = float(n.get('lon', 0))
            lat = float(n.get('lat', 0))
            if point_in_box(lon, lat, nybox) and pip(lon, lat):
                cid = n.get('changeset')
                nid = n.get('id', -1)
                nids.add(nid)
                ntags = n.findall(".//tag[@k]")
                addr_tags = getaddresstags(ntags)
                version = int(n.get('version'))
                
                # Capture address changes
                if version != 1:
                    if hasaddresschange(nid, addr_tags, version, 'node'):
                        addchangeset(n, cid)
                        changesets[cid]['nids'].add(nid)
                        changesets[cid]['addr_chg_nd'].add(nid)
                        stats['addresses'] += 1
                elif len(addr_tags):
                    addchangeset(n, cid)
                    changesets[cid]['nids'].add(nid)
                    changesets[cid]['addr_chg_nd'].add(nid)
                    stats['addresses'] += 1
    n.clear()
    root.clear()

sys.stderr.write('finding changesets\n')

# Find ways that contain nodes that were previously determined to fall within specified area
context = iter(etree.iterparse('change.osc', events=('start', 'end')))
event, root = context.next()
for event, w in context:
    if event == 'start':
        if w.tag == 'way':
            relevant = False
            cid = w.get('changeset')
            wid = w.get('id', -1)
            
            # Only if the way has 'building' tag
            if hasbuildingtag(w):
                for nd in w.iterfind('./nd'):
                    if nd.get('ref', -2) in nids:
                        relevant = True
                        addchangeset(w, cid)
                        nid = nd.get('ref', -2)
                        changesets[cid]['nids'].add(nid)
                        changesets[cid]['wids'].add(wid)
            if relevant:
                stats['buildings'] += 1
                wtags = w.findall(".//tag[@k]")
                version = int(w.get('version'))
                addr_tags = getaddresstags(wtags)
                
                # Capture address changes
                if version != 1:
                    if hasaddresschange(wid, addr_tags, version, 'way'):
                        changesets[cid]['addr_chg_way'].add(wid)
                        stats['addresses'] += 1
                elif len(addr_tags):
                    changesets[cid]['addr_chg_way'].add(wid)
                    stats['addresses'] += 1
    w.clear()
    root.clear()

changesets = map(loadChangeset, changesets.values())

stats['total'] = len(changesets)

if len(changesets) > 1000:
    changesets = changesets[:999]
    stats['limit_exceed'] = 'Note: For performance reasons only the first 1000 changesets are displayed.'
    
now = datetime.now()

tmpl = """
<div style='font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;color:#333;max-width:600px;'>
<p style='float:right;'>{{date}}</p>
<h1 style='margin-bottom:10px;'>Summary</h1>
{{#stats}}
<ul style='font-size:15px;line-height:17px;list-style:none;margin-left:0;padding-left:0;'>
<li>Total changesets: <strong>{{total}}</strong></li>
<li>Total address changes: <strong>{{addresses}}</strong></li>
<li>Total building footprint changes: <strong>{{buildings}}</strong></li>
</ul>
{{#limit_exceed}}
<p style='font-size:13px;font-style:italic;'>{{limit_exceed}}</p>
{{/limit_exceed}}
{{/stats}}
{{#changesets}}
<h2 style='border-bottom:1px solid #ddd;padding-top:15px;padding-bottom:8px;'>Changeset <a href='http://openstreetmap.org/browse/changeset/{{id}}' style='text-decoration:none;color:#3879D9;'>#{{id}}</a></h2>
<p style='font-size:14px;line-height:17px;margin-bottom:20px;'>
<a href='http://openstreetmap.org/user/{{#details}}{{user}}{{/details}}' style='text-decoration:none;color:#3879D9;font-weight:bold;'>{{#details}}{{user}}{{/details}}</a>: {{comment}}
</p>
<p style='font-size:14px;line-height:17px;margin-bottom:0;'>
Changed buildings: {{#wids}}<a href='http://openstreetmap.org/browse/way/{{.}}/history' style='text-decoration:none;color:#3879D9;'>#{{.}}</a> {{/wids}}
</p>
<p style='font-size:14px;line-height:17px;margin-top:5px;margin-bottom:20px;'>
Changed addresses: {{#addr_chg_nd}}<a href='http://openstreetmap.org/browse/node/{{.}}/history' style='text-decoration:none;color:#3879D9;'>#{{.}}</a> {{/addr_chg_nd}}{{#addr_chg_way}}<a href='http://openstreetmap.org/browse/way/{{.}}/history' style='text-decoration:none;color:#3879D9;'>#{{.}}</a> {{/addr_chg_way}}
</p>
<a href='{{map_link}}'><img src='{{map_img}}' style='border:1px solid #ddd;' /></a>
{{/changesets}}
</div>
"""

text_tmpl = """
### Summary ###
{{date}}

{{#stats}}
Total changesets: {{total}}
Total building footprint changes: {{buildings}}
Total address changes: {{addresses}}
{{#limit_exceed}}

{{limit_exceed}}

{{/limit_exceed}}
{{/stats}}

{{#changesets}}
--- Changeset #{{id}} ---
URL: http://openstreetmap.org/browse/changeset/{{id}}
User: http://openstreetmap.org/user/{{#details}}{{user}}{{/details}}
Comment: {{comment}}

Changed buildings: {{wids}}
Changed addresses: {{addr_chg_nd}} {{addr_chg_way}}
{{/changesets}}
"""

html_version = pystache.render(tmpl, {
    'changesets': changesets,
    'stats': stats,
    'date': now.strftime("%B %d, %Y")
})

text_version = pystache.render(text_tmpl, {
    'changesets': changesets,
    'stats': stats,
    'date': now.strftime("%B %d, %Y")
})

resp = requests.post(('https://api.mailgun.net/v2/changewithin.mailgun.org/messages'),
    auth = ('api', 'key-7y2k6qu8-qq1w78o1ow1ms116pkn31j7'),
    data = {
            'from': 'Change Within <changewithin@changewithin.mailgun.org>',
            'to': json.load(open(os.path.join(dir_path,'users.json'))),
            'subject': 'OSM building and address changes %s' % now.strftime("%B %d, %Y"),
            'text': text_version,
            "html": html_version,
    })

f_out = open('osm_change_report_%s.html' % now.strftime("%m-%d-%y"), 'w')
f_out.write(html_version.encode('utf-8'))
f_out.close()

# print html_version

# print resp, resp.text
