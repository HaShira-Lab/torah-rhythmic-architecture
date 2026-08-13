# -*- coding: utf-8 -*-
"""Unified taam temporal-structure analysis.

Combines four formerly separate analyses:
1) accent-interval inventory,
2) boundary-aligned interval grammar,
3) cadence-defined phrase-shape inventory,
4) transition grammar between segment shapes.

Input: transliterated annotated Torah text, e.g. word[taam] {sof_pasuq}.
"""
import argparse, csv, hashlib, json, math, random, re, shlex, sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ACUTE='\u0301'; VOWELS=set('aeiouAEIOU')
WORD_RE=re.compile(r'\[([^\]]+)\]'); EXT_RE=re.compile(r'^\{([^}]+)\}$')
ACCENTLESS={'paseq'}
MAJOR={'atnah','atnah_hafukh','sof_pasuq'}
MINOR={'revia','zaqef_qatan','zaqef_gadol','shalshelet','paseq'}
CAD=MAJOR|MINOR
RESET_MODELS={
    'continuous':set(), 'sof_only':{'sof_pasuq'},
    'major':MAJOR, 'major_minor':CAD,
}
LEVEL_BOUNDARIES={'verse':{'sof_pasuq'},'major':MAJOR,'minor':CAD}
OUTPUT_FILES=(
    'interval_summary.csv','interval_frequency.csv','interval_ngram_top.csv',
    'interval_examples.csv','interval_within_cross_contrast.csv',
    'segment_shapes.csv','segment_shape_summary.csv','segment_shape_frequency.csv',
    'segment_transition_summary.csv','segment_transitions.csv',
    'segment_transition_z.csv','temporal_structure_meta.json',
)
DEFINITIONS={
    'pulse':'one Latin-vowel group in the annotated transliteration',
    'accent_event':'one accented word carrying at least one non-accentless taam; paseq is boundary-only',
    'verse_boundary':['sof_pasuq'],
    'major_boundary':sorted(MAJOR),
    'minor_boundary':sorted(CAD),
    'interval':'forward pulse distance between adjacent accent events',
    'within_cross_contrast':'within minus cross_reset',
}

# ---------- shared parsing ----------
def split_list(s): return [x.strip() for x in str(s).split(',') if x.strip()]
def split_token(tok):
    m=EXT_RE.match(tok)
    if m: return '',[],split_list(m.group(1))
    m=WORD_RE.search(tok)
    if not m: return tok,[],[]
    return WORD_RE.sub('',tok),split_list(m.group(1)),[]

def vowel_groups(word):
    out=[]; active=False; start=0
    for i,ch in enumerate(word):
        if ch==ACUTE: continue
        if ch in VOWELS:
            if not active: start=i; active=True
        elif active:
            out.append((start,i)); active=False
    if active: out.append((start,len(word)))
    return out

def acute_vowel_index(word):
    groups=vowel_groups(word)
    if not groups: return None
    apos=[i for i,ch in enumerate(word) if ch==ACUTE]
    if not apos: return None
    a=apos[0]
    for idx,(s,e) in enumerate(groups):
        if s<=a<=e+1: return idx
        if a<s: return max(0,idx-1)
    return len(groups)-1

def finalize_record(r):
    accent_t=[t for t in r['all_taamim'] if t not in ACCENTLESS]
    ai=acute_vowel_index(r['word'])
    if ai is None and accent_t and r['pulse_count']: ai=r['pulse_count']-1
    if ai is not None and r['pulse_count']:
        ai=max(0,min(int(ai),r['pulse_count']-1))
    r['has_accent_event']=1 if accent_t and r['pulse_count'] else 0
    r['accent_syl_index']=ai

def parse_records(text):
    recs=[]
    for tok in text.replace('\ufeff','').split():
        word,internal,external=split_token(tok)
        if external:
            if recs:
                recs[-1]['external_taamim'].extend(external)
                recs[-1]['all_taamim'].extend(external)
            continue
        if not word: continue
        recs.append({'word_index':len(recs),'word':word,'internal_taamim':internal,
                     'external_taamim':[],'all_taamim':list(internal),
                     'pulse_count':len(vowel_groups(word))})
    pos=0
    for r in recs:
        finalize_record(r)
        r['start_pulse']=pos; r['end_pulse']=pos+r['pulse_count']
        r['accent_pulse']=pos+r['accent_syl_index'] if r['has_accent_event'] and r['accent_syl_index'] is not None else None
        pos+=r['pulse_count']
    return recs,pos

def has_any(r,items): return any(t in items for t in r['all_taamim'])

# ---------- common statistics ----------
def median(xs):
    if not xs: return ''
    ys=sorted(xs); n=len(ys)
    return ys[n//2] if n%2 else (ys[n//2-1]+ys[n//2])/2

def entropy(counter,base2=False):
    n=sum(counter.values())
    if not n: return 0.0
    log=math.log2 if base2 else math.log
    return -sum((v/n)*log(v/n) for v in counter.values())

def norm_entropy(counter):
    return entropy(counter)/math.log(len(counter)) if len(counter)>1 else 0.0

def mean(xs): return sum(xs)/len(xs) if xs else 0.0
def sd(xs):
    if len(xs)<2: return 0.0
    m=mean(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))

def zstats(obs,xs,tail='upper'):
    mu=mean(xs); s=sd(xs); z=(obs-mu)/s if s else None
    if not xs: p=''
    elif tail=='upper': p=(1+sum(1 for x in xs if x>=obs))/(len(xs)+1)
    elif tail=='lower': p=(1+sum(1 for x in xs if x<=obs))/(len(xs)+1)
    elif tail=='two_sided':
        center=mean(xs); distance=abs(obs-center)
        p=(1+sum(1 for x in xs if abs(x-center)>=distance))/(len(xs)+1)
    else: raise ValueError(f'Unknown tail: {tail}')
    return round(mu,8),round(s,8),('' if z is None else round(z,6)),('' if p=='' else round(p,8))

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def write_csv(path,rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if not rows: path.write_text('',encoding='utf-8-sig'); return
    fields=[]; seen=set()
    for r in rows:
        for k in r:
            if k not in seen: seen.add(k); fields.append(k)
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

# ---------- accent intervals ----------
def segment_ids(records,reset):
    ids=[]; seg=0
    for r in records:
        ids.append(seg)
        if has_any(r,reset): seg+=1
    return ids

def interval_rows(records,model,reset):
    ids=segment_ids(records,reset)
    ev=[{'word_index':r['word_index'],'word':r['word'],'pulse':r['accent_pulse'],'seg':s,
         'taamim':'+'.join(r['all_taamim'])} for r,s in zip(records,ids) if r['accent_pulse'] is not None]
    out=[]
    for idx,(a,b) in enumerate(zip(ev,ev[1:])):
        d=b['pulse']-a['pulse']
        if d<=0: continue
        rel='continuous' if model=='continuous' else ('within' if a['seg']==b['seg'] else 'cross_reset')
        out.append({'interval_index':idx,'prev_word_index':a['word_index'],'next_word_index':b['word_index'],
                    'prev_word':a['word'],'next_word':b['word'],'interval':d,'relation':rel,
                    'prev_seg':a['seg'],'next_seg':b['seg'],'prev_taamim':a['taamim'],'next_taamim':b['taamim']})
    return out

def interval_metrics(vals):
    if not vals: return {'n_intervals':0}
    c=Counter(vals); n=len(vals); top=c.most_common(5)
    return {'n_intervals':n,'unique_intervals':len(c),'mean_interval':round(mean(vals),6),
            'median_interval':round(median(vals),6),'entropy_norm':round(norm_entropy(c),8),
            'top1_interval':top[0][0],'top1_share':round(top[0][1]/n,8),
            'top3_intervals':'+'.join(str(k) for k,_ in top[:3]),'top3_share':round(sum(v for _,v in top[:3])/n,8),
            'top5_intervals':'+'.join(str(k) for k,_ in top),'top5_share':round(sum(v for _,v in top)/n,8)}

def interval_freq(vals,max_interval):
    c=Counter(x if x<=max_interval else f'>{max_interval}' for x in vals); n=len(vals); cum=0
    def key(x): return 10**9 if isinstance(x,str) else x
    out=[]
    for k in sorted(c,key=key):
        cum+=c[k]; out.append({'interval':k,'count':c[k],'share':round(c[k]/n,8) if n else 0,'cum_share':round(cum/n,8) if n else 0})
    return out

def interval_ngram(vals,n,top_k):
    grams=Counter(tuple(vals[i:i+n]) for i in range(len(vals)-n+1)); total=sum(grams.values())
    return [{'ngram_n':n,'rank':rank,'pattern':'-'.join(map(str,g)),'count':c,'share':round(c/total,8)}
            for rank,(g,c) in enumerate(grams.most_common(top_k),1)]

def interval_null(rows,relation,obs_top3,obs_ent,perm,seed,mode):
    if perm<=0 or mode=='none': return ('','','','','','','','')
    vals=[r['interval'] for r in rows]; rng=random.Random(seed); tnull=[]; enull=[]
    for _ in range(perm):
        if mode=='cyclic_shift':
            shift=rng.randrange(len(vals)); sh=vals[shift:]+vals[:shift]
        else:
            sh=vals[:]; rng.shuffle(sh)
        xs=[v for r,v in zip(rows,sh) if relation=='all' or r['relation']==relation]
        m=interval_metrics(xs); tnull.append(float(m.get('top3_share',0))); enull.append(float(m.get('entropy_norm',0)))
    tm,ts,tz,tp=zstats(obs_top3,tnull,tail='upper')
    em,es,ez,ep=zstats(obs_ent,enull,tail='lower')
    return tm,ts,tz,tp,em,es,ez,ep

def interval_contrast_null(rows,obs_top3_delta,obs_entropy_delta,perm,seed,mode):
    """Directly test within-minus-cross contrasts under the selected interval null."""
    if perm<=0 or mode=='none': return ('','','','','','','','')
    vals=[r['interval'] for r in rows]; rng=random.Random(seed); top3_null=[]; entropy_null=[]
    for _ in range(perm):
        if mode=='cyclic_shift':
            shift=rng.randrange(len(vals)); shuffled=vals[shift:]+vals[:shift]
        else:
            shuffled=vals[:]; rng.shuffle(shuffled)
        within=[v for r,v in zip(rows,shuffled) if r['relation']=='within']
        cross=[v for r,v in zip(rows,shuffled) if r['relation']=='cross_reset']
        wm=interval_metrics(within); cm=interval_metrics(cross)
        top3_null.append(float(wm['top3_share'])-float(cm['top3_share']))
        entropy_null.append(float(wm['entropy_norm'])-float(cm['entropy_norm']))
    tm,ts,tz,tp=zstats(obs_top3_delta,top3_null,tail='upper')
    em,es,ez,ep=zstats(obs_entropy_delta,entropy_null,tail='lower')
    return tm,ts,tz,tp,em,es,ez,ep

# ---------- cadence-defined segments and shapes ----------
def p_bucket(p):
    if p<=4:return 'P1-4'
    if p<=6:return 'P5-6'
    if p<=9:return 'P7-9'
    if p<=12:return 'P10-12'
    if p<=15:return 'P13-15'
    if p<=18:return 'P16-18'
    if p<=24:return 'P19-24'
    return 'P25+'
def w_bucket(w):
    if w<=2:return 'W1-2'
    if w<=4:return 'W3-4'
    if w<=6:return 'W5-6'
    if w<=8:return 'W7-8'
    if w<=12:return 'W9-12'
    return 'W13+'
def a_bucket(a):
    if a<=1:return 'A0-1'
    if a<=5:return f'A{a}'
    if a<=7:return 'A6-7'
    return 'A8+'
def c_bucket(c): return f'C{c}' if c<=3 else 'C4+'

def extract_segments(records,level):
    boundary=LEVEL_BOUNDARIES[level]; out=[]; start=0; sid=0
    for i,r in enumerate(records):
        if not has_any(r,boundary): continue
        chunk=records[start:i+1]
        if chunk:
            out.append(make_segment(chunk,level,sid,1)); sid+=1
        start=i+1
    if start<len(records): out.append(make_segment(records[start:],level,sid,0))
    return out

def make_segment(chunk,level,sid,complete):
    words=len(chunk); pulses=sum(r['pulse_count'] for r in chunk); accent_words=sum(r['has_accent_event'] for r in chunk)
    taam_events=sum(sum(1 for t in r['all_taamim'] if t not in ACCENTLESS) for r in chunk)
    internal_minor=sum(1 for r in chunk[:-1] if has_any(r,MINOR))
    return {'level':level,'segment_index':sid,'start_word_index':chunk[0]['word_index'],'end_word_index':chunk[-1]['word_index'],
            'start_word':chunk[0]['word'],'end_word':chunk[-1]['word'],'word_count':words,'pulse_count':pulses,
            'accent_count':accent_words,'taam_event_count':taam_events,'internal_minor_count':internal_minor,
            'density_accents_per_pulse':round(accent_words/pulses,8) if pulses else '',
            'cadence_taamim':'+'.join(t for t in chunk[-1]['all_taamim'] if t in LEVEL_BOUNDARIES[level]) if complete else 'INCOMPLETE_TRAILING',
            'is_incomplete':0 if complete else 1,
            'shape_PA':f'P{pulses}_A{accent_words}','shape_PAW':f'P{pulses}_A{accent_words}_W{words}',
            'bucket_PA':f'{p_bucket(pulses)}_{a_bucket(accent_words)}','bucket_PAW':f'{p_bucket(pulses)}_{a_bucket(accent_words)}_{w_bucket(words)}',
            'transition_exact_shape':f'P{words}_A{taam_events}_C{internal_minor}',
            'transition_bucket_shape':f'{("P<=4" if words<=4 else p_bucket(words))}_{a_bucket(taam_events)}_{c_bucket(internal_minor)}'}

def shape_summary(segs,field):
    vals=[s[field] for s in segs if not s['is_incomplete']]; c=Counter(vals); n=len(vals); top=c.most_common(20)
    row={'shape_field':field,'n_segments':n,'unique_shapes':len(c),'entropy_norm':round(norm_entropy(c),8)}
    for k in (1,3,5,10,20):
        row[f'top{k}']='+'.join(x for x,_ in top[:k]); row[f'top{k}_share']=round(sum(v for _,v in top[:k])/n,8) if n else 0
    return row

def shape_frequency(segs,field,top_k):
    vals=[s[field] for s in segs if not s['is_incomplete']]; c=Counter(vals); n=len(vals); cum=0; out=[]
    for rank,(shape,count) in enumerate(c.most_common(top_k),1):
        cum+=count; out.append({'shape_field':field,'rank':rank,'shape':shape,'count':count,'share':round(count/n,8),'cum_share':round(cum/n,8)})
    return out

# ---------- sequential grammar of segment shapes ----------
def conditional_entropy(seq):
    if len(seq)<2:return 0.0
    prev=Counter(seq[:-1]); succ=defaultdict(Counter); total=len(seq)-1
    for a,b in zip(seq,seq[1:]): succ[a][b]+=1
    return sum((ca/total)*entropy(succ[a],base2=True) for a,ca in prev.items())

def markov_accuracy(seq):
    succ=defaultdict(Counter)
    for a,b in zip(seq,seq[1:]): succ[a][b]+=1
    return mean([int(succ[a].most_common(1)[0][0]==b) for a,b in zip(seq,seq[1:])]) if len(seq)>1 else 0

def cv_accuracy(seq,seed,split_mode,train_frac=.8):
    pairs=list(zip(seq,seq[1:]));
    if not pairs:return 0.0,0,0
    if split_mode=='chronological': train=pairs[:max(1,int(len(pairs)*train_frac))]; test=pairs[len(train):] or pairs[:1]
    else:
        rng=random.Random(seed); rng.shuffle(pairs); n=max(1,int(len(pairs)*train_frac)); train,test=pairs[:n],pairs[n:] or pairs[:1]
    succ=defaultdict(Counter); bg=Counter()
    for a,b in train: succ[a][b]+=1; bg[b]+=1
    default=bg.most_common(1)[0][0]
    return mean([int((succ[a].most_common(1)[0][0] if succ[a] else default)==b) for a,b in test]),len(train),len(test)

def transition_rows(seq,min_count):
    prev=Counter(seq[:-1]); nxt=Counter(seq[1:]); big=Counter(zip(seq,seq[1:])); total=max(1,len(seq)-1); out=[]
    for (a,b),cnt in big.most_common():
        if cnt<min_count: continue
        p=cnt/prev[a]; bg=nxt[b]/total
        out.append({'from_shape':a,'to_shape':b,'count':cnt,'p_to_given_from':round(p,8),'p_to_background':round(bg,8),'lift':round(p/bg,8) if bg else 0})
    return out

def transition_permutation(seq,perm,seed,split_mode):
    H=entropy(Counter(seq),base2=True); Hc=conditional_entropy(seq); red=H-Hc; acc=markov_accuracy(seq); cv,ntr,nte=cv_accuracy(seq,seed,split_mode)
    rng=random.Random(seed); null={'conditional_entropy':[],'entropy_reduction':[],'in_sample_next_accuracy':[],'cv_next_accuracy':[]}
    for k in range(perm):
        sh=seq[:]; rng.shuffle(sh); h=entropy(Counter(sh),base2=True); hc=conditional_entropy(sh)
        null['conditional_entropy'].append(hc); null['entropy_reduction'].append(h-hc); null['in_sample_next_accuracy'].append(markov_accuracy(sh)); null['cv_next_accuracy'].append(cv_accuracy(sh,seed+k+1000,split_mode)[0])
    out=[{'metric':'unigram_entropy','observed':round(H,8),'null_mean':round(H,8),'null_sd':0,'z':0,'empirical_p':''}]
    for name,obs in [('conditional_entropy',Hc),('entropy_reduction',red),('in_sample_next_accuracy',acc),('cv_next_accuracy',cv)]:
        tail='lower' if name=='conditional_entropy' else 'upper'
        mu,s,z,p=zstats(obs,null[name],tail=tail)
        row={'metric':name,'observed':round(obs,8),'null_mean':mu,'null_sd':s,'z':z,'empirical_p':p,'empirical_p_tail':tail}
        if name=='cv_next_accuracy': row.update({'n_train_bigrams':ntr,'n_test_bigrams':nte,'split_mode':split_mode})
        out.append(row)
    return out

def transition_z(seq,rows,perm,seed,top_k):
    targets=[(r['from_shape'],r['to_shape']) for r in rows[:top_k]]; obs=Counter(zip(seq,seq[1:])); nulls={p:[] for p in targets}; rng=random.Random(seed)
    for _ in range(perm):
        sh=seq[:]; rng.shuffle(sh); c=Counter(zip(sh,sh[1:]))
        for p in targets:nulls[p].append(c[p])
    out=[]
    for r in rows[:top_k]:
        p=(r['from_shape'],r['to_shape']); mu,s,z,ep=zstats(obs[p],nulls[p],tail='upper'); rr=dict(r); rr.update({'null_mean':mu,'null_sd':s,'z':z,'empirical_p':ep,'empirical_p_tail':'upper','p_value_scope':'screening_selected_transition'}); out.append(rr)
    return sorted(out,key=lambda x:(-999999 if x['z']=='' else -x['z']))

# ---------- per-book orchestration ----------
def analyze_book(tag,path,out_dir,argsdict,run_context):
    input_path=Path(path)
    input_sha256=sha256_file(input_path)
    records,total_pulses=parse_records(input_path.read_text(encoding='utf-8-sig')); out=Path(out_dir)/tag; out.mkdir(parents=True,exist_ok=True)
    n_acc=sum(r['has_accent_event'] for r in records)
    # intervals
    isum=[]; ifreq=[]; ing=[]; iex=[]; contrasts=[]; metrics={}
    for model,reset in RESET_MODELS.items():
        rows=interval_rows(records,model,reset)
        for r in rows:r.update({'book':tag,'model':model})
        iex.extend(rows[:argsdict['max_examples']])
        rels=['continuous'] if model=='continuous' else ['within','cross_reset','all']
        for rel in rels:
            xs=[r['interval'] for r in rows if rel=='all' or r['relation']==rel]; m=interval_metrics(xs); metrics[(model,rel)]=m
            if not m.get('n_intervals'): continue
            null_applicable=(model!='continuous' and rel not in {'all','continuous'})
            if null_applicable:
                tm,ts,tz,tp,em,es,ez,ep=interval_null(rows,rel,float(m['top3_share']),float(m['entropy_norm']),argsdict['interval_perm'],argsdict['seed'],argsdict['null_model'])
                reported_null=argsdict['null_model']
            else:
                tm,ts,tz,tp,em,es,ez,ep=('','','','','','','','')
                reported_null='not_applicable_distribution_preserved'
            sr={'book':tag,'model':model,'relation':rel,'reset_taamim':'+'.join(sorted(reset)) if reset else 'none','n_words':len(records),'n_pulses':total_pulses,'n_accents':n_acc,**m,
                'null_model':reported_null,'null_top3_mean':tm,'null_top3_sd':ts,'top3_z':tz,'top3_empirical_p':tp,'top3_empirical_p_tail':'upper' if null_applicable else '',
                'null_entropy_mean':em,'null_entropy_sd':es,'entropy_z':ez,'entropy_empirical_p':ep,'entropy_empirical_p_tail':'lower' if null_applicable else ''}
            isum.append(sr)
            for fr in interval_freq(xs,argsdict['max_interval']): fr.update({'book':tag,'model':model,'relation':rel}); ifreq.append(fr)
            for nn in argsdict['interval_ngram_ns']:
                for nr in interval_ngram(xs,nn,argsdict['top_interval_ngram']): nr.update({'book':tag,'model':model,'relation':rel}); ing.append(nr)
    for model in ('sof_only','major','major_minor'):
        w=metrics.get((model,'within'),{}); c=metrics.get((model,'cross_reset'),{})
        if w.get('n_intervals') and c.get('n_intervals'):
            top3_delta=round(w['top3_share']-c['top3_share'],8)
            entropy_delta=round(w['entropy_norm']-c['entropy_norm'],8)
            tm,ts,tz,tp,em,es,ez,ep=interval_contrast_null(rows=interval_rows(records,model,RESET_MODELS[model]),obs_top3_delta=top3_delta,obs_entropy_delta=entropy_delta,perm=argsdict['interval_perm'],seed=argsdict['seed'],mode=argsdict['null_model'])
            contrasts.append({'book':tag,'model':model,'within_n':w['n_intervals'],'cross_n':c['n_intervals'],'within_top3_share':w['top3_share'],'cross_top3_share':c['top3_share'],
                              'delta_top3_within_minus_cross':top3_delta,'delta_top3_null_mean':tm,'delta_top3_null_sd':ts,'delta_top3_z':tz,'delta_top3_empirical_p':tp,'delta_top3_empirical_p_tail':'upper',
                              'within_entropy':w['entropy_norm'],'cross_entropy':c['entropy_norm'],'delta_entropy_within_minus_cross':entropy_delta,
                              'delta_entropy_null_mean':em,'delta_entropy_null_sd':es,'delta_entropy_z':ez,'delta_entropy_empirical_p':ep,'delta_entropy_empirical_p_tail':'lower','null_model':argsdict['null_model']})
    # shapes and transitions
    segments=[]; ssh=[]; sfreq=[]; stranssum=[]; strans=[]; stransz=[]
    shape_fields=['shape_PA','bucket_PA','shape_PAW','bucket_PAW']
    for level in ('minor','major','verse'):
        segs=extract_segments(records,level)
        for s in segs:s['book']=tag
        segments.extend(segs)
        for field in shape_fields:
            row=shape_summary(segs,field); row.update({'book':tag,'level':level}); ssh.append(row)
            for fr in shape_frequency(segs,field,argsdict['top_shapes']): fr.update({'book':tag,'level':level}); sfreq.append(fr)
        # preserve original transition-grammar shape definition; optional accent_words control
        for field in ('transition_bucket_shape','transition_exact_shape'):
            complete=[s for s in segs if not s['is_incomplete']]
            if argsdict['transition_accent_mode']=='accent_words':
                if field=='transition_exact_shape':
                    seq=[f"P{x['word_count']}_A{x['accent_count']}_C{x['internal_minor_count']}" for x in complete]
                else:
                    seq=[f"{('P<=4' if x['word_count']<=4 else p_bucket(x['word_count']))}_{a_bucket(x['accent_count'])}_{c_bucket(x['internal_minor_count'])}" for x in complete]
            else:
                seq=[x[field] for x in complete]
            tsum=transition_permutation(seq,argsdict['transition_perm'],argsdict['seed'],argsdict['split_mode'])
            tr=transition_rows(seq,argsdict['min_transition_count']); trz=transition_z(seq,tr,argsdict['transition_perm'],argsdict['seed'],argsdict['transition_top_k'])
            for rr in tsum: rr.update({'book':tag,'level':level,'shape_field':field,'n_segments':len(seq),'vocab_size':len(set(seq)),'split_mode':argsdict['split_mode'],'transition_accent_mode':argsdict['transition_accent_mode']})
            for group in (tr,trz):
                for rr in group: rr.update({'book':tag,'level':level,'shape_field':field,'transition_accent_mode':argsdict['transition_accent_mode']})
            stranssum.extend(tsum); strans.extend(tr); stransz.extend(trz)
    files={'interval_summary.csv':isum,'interval_frequency.csv':ifreq,'interval_ngram_top.csv':ing,'interval_examples.csv':iex,'interval_within_cross_contrast.csv':contrasts,
           'segment_shapes.csv':segments,'segment_shape_summary.csv':ssh,'segment_shape_frequency.csv':sfreq,'segment_transition_summary.csv':stranssum,'segment_transitions.csv':strans,'segment_transition_z.csv':stransz}
    for name,rows in files.items(): write_csv(out/name,rows)
    meta={'book':tag,'input':str(input_path),'input_sha256':input_sha256,'n_words':len(records),'n_pulses':total_pulses,'n_accents':n_acc,
          'run_label':run_context['run_label'],'cli':run_context['cli'],'definitions':DEFINITIONS,'parameters':argsdict,
          'interval_contrasts':contrasts,'shape_summary':ssh,'transition_summary':stranssum}
    (out/'temporal_structure_meta.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    return tag,files,meta

def validate_args(a,parser):
    tags=[tag for tag,_ in a.book]
    if len(tags)!=len(set(tags)): parser.error('book tags must be unique')
    missing=[path for _,path in a.book if not Path(path).is_file()]
    if missing: parser.error('input file(s) not found: '+', '.join(missing))
    positive={'jobs':a.jobs,'max_interval':a.max_interval,'top_interval_ngram':a.top_interval_ngram,
              'top_shapes':a.top_shapes,'min_transition_count':a.min_transition_count,
              'transition_top_k':a.transition_top_k}
    for name,value in positive.items():
        if value<=0: parser.error(f'--{name} must be positive')
    if a.interval_perm<0 or a.transition_perm<0: parser.error('permutation counts must be non-negative')
    if a.max_examples<0: parser.error('--max_examples must be non-negative')
    try: ns=[int(x) for x in a.interval_ngram_ns.split(',') if x.strip()]
    except ValueError: parser.error('--interval_ngram_ns must be a comma-separated list of integers')
    if not ns or any(n<2 for n in ns): parser.error('--interval_ngram_ns values must be integers >= 2')
    return ns

def clean_known_outputs(out,tags):
    """Remove only files this analysis owns, never unrelated user outputs."""
    for tag in tags:
        book_dir=out/tag
        for name in OUTPUT_FILES:
            p=book_dir/name
            if p.is_file(): p.unlink()
    for name in OUTPUT_FILES:
        p=out/('ALL_'+name)
        if p.is_file(): p.unlink()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out_dir',required=True); ap.add_argument('--book',action='append',nargs=2,required=True); ap.add_argument('--run_label',default='main'); ap.add_argument('--jobs',type=int,default=5)
    ap.add_argument('--interval_perm',type=int,default=500); ap.add_argument('--transition_perm',type=int,default=500); ap.add_argument('--seed',type=int,default=1)
    ap.add_argument('--null_model',choices=['global_interval_shuffle','cyclic_shift','none'],default='global_interval_shuffle')
    ap.add_argument('--max_interval',type=int,default=40); ap.add_argument('--top_interval_ngram',type=int,default=50); ap.add_argument('--interval_ngram_ns',default='2,3,4,5,6')
    ap.add_argument('--top_shapes',type=int,default=50); ap.add_argument('--min_transition_count',type=int,default=5); ap.add_argument('--transition_top_k',type=int,default=50)
    ap.add_argument('--split_mode',choices=['random','chronological'],default='random'); ap.add_argument('--transition_accent_mode',choices=['taam_events','accent_words'],default='taam_events'); ap.add_argument('--max_examples',type=int,default=2000)
    a=ap.parse_args(); interval_ngram_ns=validate_args(a,ap)
    d=vars(a).copy(); d['interval_ngram_ns']=interval_ngram_ns; d.pop('book'); d.pop('out_dir'); d.pop('jobs'); d.pop('run_label')
    out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    clean_known_outputs(out,[tag for tag,_ in a.book])
    run_context={'run_label':a.run_label,'out_dir':str(out),'jobs':a.jobs,'cli_argv':sys.argv[:],
                 'cli':shlex.join(sys.argv),'definitions':DEFINITIONS}
    allfiles=defaultdict(list); metas=[]
    if a.jobs>1 and len(a.book)>1:
        with ProcessPoolExecutor(max_workers=min(a.jobs,len(a.book))) as ex:
            futs=[ex.submit(analyze_book,t,p,a.out_dir,d,run_context) for t,p in a.book]
            results=[f.result() for f in as_completed(futs)]
    else: results=[analyze_book(t,p,a.out_dir,d,run_context) for t,p in a.book]
    order={t:i for i,(t,_) in enumerate(a.book)}; results.sort(key=lambda x:order[x[0]])
    for tag,files,meta in results:
        metas.append(meta)
        for name,rows in files.items(): allfiles[name].extend(rows)
    for name,rows in allfiles.items(): write_csv(out/('ALL_'+name),rows)
    all_meta={'run':run_context,'parameters':d,'books':metas}
    (out/'ALL_temporal_structure_meta.json').write_text(json.dumps(all_meta,indent=2,ensure_ascii=False),encoding='utf-8')
    print('=== TAAM TEMPORAL STRUCTURE ==='); print('out:',out); print('run_label:',a.run_label,'jobs:',a.jobs,'interval_perm:',a.interval_perm,'transition_perm:',a.transition_perm); print('null_model:',a.null_model,'split_mode:',a.split_mode,'transition_accent_mode:',a.transition_accent_mode)
    for m in metas:
        print(); print(m['book'],'| words:',m['n_words'],'| pulses:',m['n_pulses'],'| accents:',m['n_accents'])
        for r in m['interval_contrasts']:
            if r['model'] in {'major','major_minor'}: print(f"  interval {r['model']}: Δtop3={r['delta_top3_within_minus_cross']} Z={r['delta_top3_z']} p={r['delta_top3_empirical_p']} | Δentropy={r['delta_entropy_within_minus_cross']} Z={r['delta_entropy_z']} p={r['delta_entropy_empirical_p']}")
        for r in m['shape_summary']:
            if r['level']=='minor' and r['shape_field']=='bucket_PA': print(f"  minor bucket shapes: top5={r['top5']} share={r['top5_share']} entropy={r['entropy_norm']}")
        for r in m['transition_summary']:
            if r['level']=='minor' and r['shape_field']=='transition_bucket_shape' and r['metric']=='entropy_reduction': print(f"  minor shape transitions: entropy_reduction={r['observed']} Z={r['z']} p={r['empirical_p']}")
    print('DONE')
if __name__=='__main__': main()
