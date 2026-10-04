"""Score the CPU-tier zero-shot signals directly (before fusion). usage: python zero_shot_eval.py [-v|x] [gold.json]"""
import json, sqlite3, sys
sys.path.insert(0,'/home/user/Metachlorian/eval/content')
from evaluate import SIZES, TOD, bucket
from metachlorian.vocab import registry
reg=registry(); sv=reg.get('setting')
c=sqlite3.connect('' + __import__('os').environ.get('METACHLORIAN_LIB', '/home/user/demo-lib') + '/library.sqlite'); c.row_factory=sqlite3.Row
gold=json.load(open(sys.argv[2] if len(sys.argv)>2 else '/home/user/Metachlorian/eval/content/gold.json'))['shots']
def sig(sid,name):
    r=c.execute("select value from signals where level='shot' and target_id=? and name=? and source!='fusion'",(sid,name)).fetchone()
    return json.loads(r[0]) if r else None
stats={'size':[0,0],'size1':[0,0],'ie':[0,0],'set1':[0,0],'setany':[0,0],'tod':[0,0],'people':[0,0],'aer_tp':0,'aer_fp':0,'aer_fn':0}
conf=[]
for g in gold:
    if g.get('blank'): continue
    a=c.execute('select id from assets where filename=?',(g['filename'],)).fetchone()
    s=c.execute('select id from shots where asset_id=? and start_s<=? and end_s>?',(a[0],g['mid'],g['mid'])).fetchone()
    if not s: continue
    sid=s[0]
    zs={k:sig(sid,'zs.'+k) or [] for k in ('setting','time_of_day','shot_size','camera_angle','concepts')}
    meas=sig(sid,'camera.shot_size_measured')
    if g['shot_size']:
        p=zs['shot_size'][0]['term'] if zs['shot_size'] else None
        if meas: p=meas
        stats['size'][1]+=1; stats['size1'][1]+=1
        if p: stats['size'][0]+=p==g['shot_size']; stats['size1'][0]+=abs(SIZES.index(p)-SIZES.index(g['shot_size']))<=1
    st=[t['term'] for t in zs['setting']]
    if g['interior'] is not None:
        ie=[t for t in zs['setting'] if t['term'] in ('interior','exterior')]
        pi=None
        if ie: pi=max(ie,key=lambda t:t['confidence'])['term']=='interior'
        stats['ie'][1]+=1; stats['ie'][0]+= pi==g['interior']
    gs=[x for x in g['settings'] if x not in ('interior','exterior')]
    if gs:
        ok=set(gs)|{x for t in gs for x in sv.ancestors(t)}|{x for t in gs for x in sv.narrower(t)}
        spec=[t for t in st if t not in ('interior','exterior')]
        stats['set1'][1]+=1; stats['setany'][1]+=1
        stats['set1'][0]+= bool(spec) and spec[0] in ok; stats['setany'][0]+= any(t in ok for t in spec)
        if not (spec and spec[0] in ok): conf.append(('set',g['filename'][:30],gs,spec[:3]))
    if g['time_of_day']:
        p=zs['time_of_day'][0]['term'] if zs['time_of_day'] else None
        stats['tod'][1]+=1; stats['tod'][0]+= TOD.get(p)==TOD[g['time_of_day']]
        if TOD.get(p)!=TOD[g['time_of_day']]: conf.append(('tod',g['filename'][:30],g['time_of_day'],p))
    if g['people'] is not None:
        pc=sig(sid,'people.count'); stats['people'][1]+=1; stats['people'][0]+= bucket(pc)==g['people']
        if bucket(pc)!=g['people']: conf.append(('ppl',g['filename'][:30],g['people'],pc))
    if g['aerial'] is not None:
        ca={t['term']:t['confidence'] for t in zs['camera_angle']}; cc={t['term']:t for t in zs['concepts']}
        p = ca.get('aerial_view',0)>0.35 or ('drone_footage' in cc and cc['drone_footage']['p']>0.02)
        stats['aer_tp']+= p and g['aerial']; stats['aer_fp']+= p and not g['aerial']; stats['aer_fn']+= (not p) and g['aerial']
for k,v in stats.items(): print(k, v if isinstance(v,int) else f"{v[0]}/{v[1]} = {v[0]/max(1,v[1]):.2f}")
if '-v' in sys.argv:
    for x in conf: print(x)
