"""Reproducible, constrained within-scene gMAD screening from chunk frame scores.

Run with the project's conda/base Python (numpy, scipy and torch required).
These are screening pairs, not validated final stimuli or subjective rankings.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import itertools
import json
from pathlib import Path

import numpy as np
import torch
from scipy.stats import spearmanr
import temporal_pooling_snapshot as pooling

ROOT = Path(__file__).resolve().parents[1]
RULES = list(pooling.RULES)
DISPLAY_FPS = 120
PAPER_FPS = 25
EXP_TAU_FRAMES = round(100 * DISPLAY_FPS / PAPER_FPS)
WORST_WINDOW_FRAMES = round(100 * DISPLAY_FPS / PAPER_FPS)
LAST_FRAMES = round(125 * DISPLAY_FPS / PAPER_FPS)


def write_csv(path, rows, fields=None):
    rows = list(rows)
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(root, group_by='scene'):
    manifest_path = root / 'manifest.json'
    records = json.loads(manifest_path.read_text())
    chunks, provenance, audit = {}, [], []
    for r in records:
        # Steam exports identify content by shot rather than a separate scene.
        # Keep each full shot path distinct and make its candidate IDs file-safe.
        if group_by == 'shot' or 'scene' not in r:
            r = dict(r, scene=r['shot'].replace('/', '__'))
        key = (r['scene'], r['chunk'], r['height'], r['fps'])
        if key in chunks:
            raise ValueError(f'Duplicate chunk {key}')
        path = root / r['shot'] / 'frames' / Path(r['frames_csv']).name
        meta_path = path.with_suffix('.metadata.json')
        meta = json.loads(meta_path.read_text())
        a = np.genfromtxt(path, delimiter=',', names=True)
        q = a['jod_frame_proxy']
        assert len(q) == 180 and np.isfinite(q).all(), path
        assert np.array_equal(a['frame_index'], np.arange(180)), path
        assert np.allclose(a['time_s'], np.arange(180)/120, atol=1e-8), path
        assert meta['fps'] == 120 and meta['usable_for_design'], path
        assert meta['display'] == 'standard_fhd', path
        chunks[key] = (q, r)
        provenance.append({'path': str(path.resolve()), 'sha256': digest(path),
                           'metadata_sha256': digest(meta_path)})
        audit.append(dict(scene=r['scene'], chunk=r['chunk'], height=r['height'], fps=r['fps'],
                          frames=len(q), min=float(q.min()), max=float(q.max()),
                          negative_frames=int((q < 0).sum()), mean=float(q.mean()),
                          native_jod=r['native_jod']))
    candidates, sequences = [], []
    scenes = sorted({k[0] for k in chunks})
    for scene in scenes:
        settings = sorted({(k[2], k[3]) for k in chunks if k[0] == scene})
        assert len(settings) >= 2, (scene, settings)
        for chunk in (1, 2, 3):
            present = {(key[2], key[3]) for key in chunks if key[0] == scene and key[1] == chunk}
            assert present == set(settings), (scene, chunk, 'Incomplete condition grid', present, settings)
        for triple in itertools.product(settings, repeat=3):
            parts = [chunks[(scene, i+1, *setting)] for i, setting in enumerate(triple)]
            labels = [f'{h}p{f}' for h, f in triple]
            cid = scene + '__' + '-'.join(labels)
            candidates.append(dict(candidate_id=cid, scene=scene,
                chunk1=labels[0], chunk2=labels[1], chunk3=labels[2],
                is_fixed=len(set(triple)) == 1,
                switches=sum(triple[i] != triple[i+1] for i in range(2)),
                source_videos=[x[1]['test'] for x in parts],
                source_references=[x[1]['reference'] for x in parts]))
            sequences.append(np.concatenate([x[0] for x in parts]))
    return candidates, np.array(sequences), audit, provenance, digest(manifest_path)


def predict(q, offset, exp_tau_frames=EXP_TAU_FRAMES,
            worst_window_frames=WORST_WINDOW_FRAMES, last_frames=LAST_FRAMES):
    """All pooling functions see the same strictly positive input.

    Frame-count parameters from 25 fps studies are converted to 120 Hz while
    preserving their original physical durations. Hysteresis is 2 s;
    segment weighting uses the three experimental chunks. CQM's 50/60 s
    windows cover all 4.5 s; duration weighting corrects its partial-second bias.
    """
    out = np.empty((len(q), len(RULES)))
    lengths=np.array([len(row) for row in q])
    for length in sorted(set(lengths)):
        indices=np.flatnonzero(lengths==length)
        x=torch.as_tensor(np.stack([q[i] for i in indices])+offset,dtype=torch.float64)
        for m,name in enumerate(RULES):
            if name == 'hysteresis':
                total=torch.zeros(len(x),dtype=x.dtype)
                for t in range(length):
                    memory=x[:,0] if t==0 else x[:,max(0,t-240):t].min(dim=1).values
                    v=x[:,t:min(t+240,length-1)+1].sort(dim=1).values
                    k=v.shape[1]
                    w=torch.exp(-torch.arange(k,dtype=x.dtype)**2/(2*((2*k-1)/12)**2))
                    total+=.8*(v*w/w.sum()).sum(dim=1)+.2*memory
                out[indices,m]=(total/length).numpy()-offset
            elif name=='cumulative_quality':
                out[indices,m]=[float(q[i].mean()) for i in indices]
            else:
                kwargs={'n_segments':3} if name in (
                    'early_dominance','late_dominance','increasing_weights','decreasing_weights') else {}
                if name=='exp_weighted_minkowski':kwargs={'tau':exp_tau_frames}
                if name=='worst_window':kwargs={'window':worst_window_frames}
                if name=='last_frames_mean':kwargs={'num_frames':last_frames}
                out[indices,m]=[float(pooling.RULES[name](row,**kwargs))-offset for row in x]
        print(f'Computed 15 rules for {len(indices)} candidates with {length} frames',flush=True)
    assert np.isfinite(out).all()
    # Verify optimized hysteresis independently against the original function.
    for i in (0,len(q)//2,len(q)-1):
        expected=float(pooling.hysteresis_pooling(torch.as_tensor(q[i]+offset,dtype=torch.float64),fps=120))-offset
        assert np.isclose(out[i,RULES.index('hysteresis')], expected, atol=1e-10)
    return out


def equivalence(pred):
    representative, rows = {}, []
    for i, name in enumerate(RULES):
        match = next((RULES[j] for j in range(i) if np.allclose(pred[:,i],pred[:,j],atol=1e-9,rtol=0)),name)
        representative[name] = representative.get(match, match)
    for i,j in itertools.combinations(range(len(RULES)),2):
        rows.append(dict(rule1=RULES[i], rule2=RULES[j],
                         identical=bool(np.allclose(pred[:,i],pred[:,j],atol=1e-9,rtol=0)),
                         max_abs_difference=float(np.abs(pred[:,i]-pred[:,j]).max()),
                         spearman=float(spearmanr(pred[:,i],pred[:,j]).statistic)))
    return representative, rows


def select(candidates, pred, bins, eps_fraction, eps_cap, min_attack_fraction, representative):
    """Exact exhaustive search over unordered pairs; ties resolved by IDs.

    Bins are within-scene defender quantiles; equal predictions stay together.
    Both videos must belong to the same bin AND satisfy the defender gap cap.
    Attack span and epsilon use the within-scene p95-p5 prediction range.
    """
    tasks, selected, contexts = [], {}, {}
    scenes = sorted({c['scene'] for c in candidates})
    for s in scenes:
        idx = np.array([i for i,c in enumerate(candidates) if c['scene']==s])
        p = pred[idx]
        ii,jj = np.triu_indices(len(idx),1)
        gaps = np.abs(p[ii]-p[jj])
        spans = np.quantile(p,.95,axis=0)-np.quantile(p,.05,axis=0)
        contexts[s]=(idx, ii, jj, gaps, spans)
        for d,dname in enumerate(RULES):
            edges=np.quantile(p[:,d],np.arange(1,bins)/bins)
            b=np.searchsorted(edges,p[:,d],side='right')
            eps=min(eps_cap,eps_fraction*spans[d])
            for a,aname in enumerate(RULES):
                if a==d:continue
                for k in range(bins):
                    row=dict(task_id=f'{s}__{dname}__{aname}__{k+1}',scene=s,
                        defender=dname,attacker=aname,quality_bin=k+1,
                        bin_low=float(p[:,d].min() if k==0 else edges[k-1]),
                        bin_high=float(p[:,d].max() if k==bins-1 else edges[k]),
                        bin_candidates=int((b==k).sum()),defender_epsilon=float(eps),
                        min_attack_gap=float(min_attack_fraction*spans[a]),
                        status='',pair_id='',video_high='',video_low='',
                        defender_high='',defender_low='',attacker_high='',attacker_low='',
                        defender_gap='',attacker_gap='',attack_gap_normalized='',
                        feasible_pairs=0)
                    if representative[dname]==representative[aname]:
                        row['status']='equivalent_rules'
                    elif spans[a]<1e-10 or spans[d]<1e-10:
                        row['status']='constant_rule'
                    else:
                        valid=np.flatnonzero((b[ii]==k)&(b[jj]==k)&(gaps[:,d]<=eps+1e-10))
                        row['feasible_pairs']=len(valid)
                        if len(valid)==0:row['status']='no_feasible_pair'
                        else:
                            best=valid[np.argmax(gaps[valid,a])]
                            if gaps[best,a] < max(1e-9,min_attack_fraction*spans[a]):
                                row['status']='insufficient_attack_gap'
                            else:
                                i,j=int(idx[ii[best]]),int(idx[jj[best]])
                                ids=sorted([candidates[i]['candidate_id'],candidates[j]['candidate_id']])
                                pid='pair_'+hashlib.sha256('|'.join(ids).encode()).hexdigest()[:12]
                                high,low=(i,j) if pred[i,a]>pred[j,a] else (j,i)
                                row.update(status='selected',pair_id=pid,
                                    video_high=candidates[high]['candidate_id'],video_low=candidates[low]['candidate_id'],
                                    defender_high=float(pred[high,d]),defender_low=float(pred[low,d]),
                                    attacker_high=float(pred[high,a]),attacker_low=float(pred[low,a]),
                                    defender_gap=float(gaps[best,d]),attacker_gap=float(gaps[best,a]),
                                    attack_gap_normalized=float(gaps[best,a]/spans[a]))
                                selected.setdefault(pid,dict(pair_id=pid,scene=s,video_a=ids[0],video_b=ids[1]))
                    tasks.append(row)
    return tasks,selected,contexts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'results/legacy/gmad_frame_scores/lossless_spatiotemporal_chunks')
    parser.add_argument('--output',type=Path,default=ROOT/'results/legacy/gmad_selection')
    parser.add_argument('--bins',type=int,default=3)
    parser.add_argument('--epsilon-fraction',type=float,default=.05)
    parser.add_argument('--epsilon-cap',type=float,default=.10)
    parser.add_argument('--min-attack-fraction',type=float,default=.10)
    parser.add_argument('--seed',type=int,default=20260930)
    parser.add_argument('--group-by',choices=('scene','shot'),default='scene',
                        help='Content group for candidates and pairs: manifest scene, or each shot separately')
    parser.add_argument('--time-policy',choices=('original','converted'),default='converted',
                        help='Use 100/125 frames or time-equivalent 480/600 frames')
    parser.add_argument('--skip-negative',action='store_true',
                        help='Remove negative frame values before every pooling rule')
    parser.add_argument('--input-offset',type=float,
                        help='Keep the same positive input offset as a baseline for an isolated comparison')
    args=parser.parse_args()
    assert args.bins>=2 and args.epsilon_fraction>0 and args.epsilon_cap>0
    torch.set_num_threads(1)
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    candidates,original_q,audit,provenance,manifest_hash=load(args.input,args.group_by)
    q=[row[row>=0] for row in original_q] if args.skip_negative else original_q
    assert all(len(row)>0 for row in q)
    offset=args.input_offset if args.input_offset is not None else max(0.,1.-min(float(row.min()) for row in q))
    assert min(float(row.min()) for row in q)+offset>0
    exp_tau,worst_window,last_frames=((100,100,125) if args.time_policy=='original' else
                                     (EXP_TAU_FRAMES,WORST_WINDOW_FRAMES,LAST_FRAMES))
    pred=predict(q,offset,exp_tau,worst_window,last_frames)
    reps,eq=equivalence(pred)
    tasks,pairs,contexts=select(candidates,pred,args.bins,args.epsilon_fraction,args.epsilon_cap,args.min_attack_fraction,reps)
    scenes=sorted(contexts)
    lookup={c['candidate_id']:c for c in candidates}
    by_pair={pid:[t for t in tasks if t['pair_id']==pid] for pid in pairs}
    # A deterministic compact task design assigns each direction/bin to one scene.
    compact=[]
    for d in RULES:
        for a in RULES:
            if a==d:continue
            for k in range(1,args.bins+1):
                rank=RULES.index(d)*14+[n for n in RULES if n!=d].index(a)
                s=scenes[(rank*args.bins+k-1)%len(scenes)]
                compact.append(next(t for t in tasks if (t['scene'],t['defender'],t['attacker'],t['quality_bin'])==(s,d,a,k)))
    # Greedy coverage of distinct effective model-direction/bin cells, 10 per scene.
    pilot_roles={}
    for s in scenes:
        covered=set()
        remaining={pid for pid,v in pairs.items() if v['scene']==s}
        for _ in range(min(10,len(remaining))):
            def utility(pid):
                cells={(reps[t['defender']],reps[t['attacker']],t['quality_bin']) for t in by_pair[pid]}
                return (len(cells-covered),max(t['attack_gap_normalized'] for t in by_pair[pid]),pid)
            pid=max(remaining,key=utility);remaining.remove(pid)
            pilot_roles.setdefault(pid,[]).append('gmad_pilot')
            covered|={(reps[t['defender']],reps[t['attacker']],t['quality_bin']) for t in by_pair[pid]}
    rng=np.random.default_rng(args.seed)
    supplements=[]
    def add_pair(i,j,role):
        ids=sorted([candidates[int(i)]['candidate_id'],candidates[int(j)]['candidate_id']])
        pid='pair_'+hashlib.sha256('|'.join(ids).encode()).hexdigest()[:12]
        pairs.setdefault(pid,dict(pair_id=pid,scene=candidates[int(i)]['scene'],video_a=ids[0],video_b=ids[1]))
        pilot_roles.setdefault(pid,[]).append(role)
        supplements.append(dict(pair_id=pid,role=role,scene=candidates[int(i)]['scene'],video_a=ids[0],video_b=ids[1]))
    for s,(idx,ii,jj,gaps,spans) in contexts.items():
        # Independently sample the full population, without excluding adversarial pairs.
        fixed=np.array([candidates[i]['is_fixed'] for i in idx])
        for role,mask in [('random_fixed',fixed[ii]&fixed[jj]),('random_varying',~(fixed[ii]&fixed[jj]))]:
            pos=int(rng.choice(np.flatnonzero(mask)));add_pair(idx[ii[pos]],idx[jj[pos]],role)
        norm_delta=(pred[idx[ii]]-pred[idx[jj]])/np.maximum(spans,1e-10)
        disagreement=np.ptp(norm_delta,axis=1)
        reversal=np.array([all(candidates[idx[i]][f'chunk{k}']==candidates[idx[j]][f'chunk{4-k}'] for k in (1,2,3)) for i,j in zip(ii,jj)])
        mean_gap=gaps[:,RULES.index('mean')]
        stable=(fixed[ii]!=fixed[jj])&(mean_gap<=min(args.epsilon_cap,args.epsilon_fraction*spans[RULES.index('mean')])+1e-10)
        for role,mask in [('diagnostic_reversal',reversal),('diagnostic_stable_vs_varying',stable)]:
            eligible=np.flatnonzero(mask)
            if len(eligible):
                pos=eligible[np.argmax(disagreement[eligible])];add_pair(idx[ii[pos]],idx[jj[pos]],role)
    def enrich(p):
        a,b=lookup[p['video_a']],lookup[p['video_b']]
        ts=by_pair.get(p['pair_id'],[])
        return dict(**p,settings_a=' / '.join(a[f'chunk{k}'] for k in (1,2,3)),
                    settings_b=' / '.join(b[f'chunk{k}'] for k in (1,2,3)),
                    gmad_task_count=len(ts),roles=';'.join(pilot_roles.get(p['pair_id'],[])))
    full_pairs=[enrich(pairs[pid]) for pid in sorted(by_pair)]
    pilot=[enrich(pairs[pid]) for pid in sorted(pilot_roles)]
    sensitivity=[]
    primary_ids=set(by_pair)
    for frac in (.025,.05,.10):
        ts,ps,_=select(candidates,pred,args.bins,frac,args.epsilon_cap,args.min_attack_fraction,reps)
        ids=set(ps)
        sensitivity.append(dict(kind='epsilon_fraction',value=frac,selected_tasks=sum(t['status']=='selected' for t in ts),
            unique_pairs=len(ps),pair_jaccard=len(ids&primary_ids)/len(ids|primary_ids)))
    # Input-offset sensitivity matters specifically for RMS and VQPooling.
    shifted=pred.copy()
    for name in ('minkowski','exp_weighted_minkowski','vqpooling_temporal'):
        m=RULES.index(name)
        kwargs={'tau':exp_tau} if name=='exp_weighted_minkowski' else {}
        shifted[:,m]=[float(pooling.RULES[name](torch.tensor(row+offset+1,dtype=torch.float64),**kwargs))-offset-1 for row in q]
    ts,ps,_=select(candidates,shifted,args.bins,args.epsilon_fraction,args.epsilon_cap,args.min_attack_fraction,reps)
    ids=set(ps)
    sensitivity.append(dict(kind='input_offset',value=offset+1,selected_tasks=sum(t['status']=='selected' for t in ts),
        unique_pairs=len(ps),pair_jaccard=len(ids&primary_ids)/len(ids|primary_ids)))
    baseline=pred[:,RULES.index('cumulative_quality')]
    legacy=np.array([float(pooling.cumulative_quality_pooling(torch.tensor(row),fps=120)) for row in q])
    write_csv(out/'cqm_tail_bias_audit.csv',[dict(candidate_id=c['candidate_id'],duration_weighted=float(v),legacy_equal_seconds=float(w),difference=float(w-v)) for c,v,w in zip(candidates,baseline,legacy)])
    write_csv(out/'input_audit.csv',audit)
    negative=[]
    for source in provenance:
        path=Path(source['path'])
        arr=np.genfromtxt(path,delimiter=',',names=True)
        for row in arr[arr['jod_frame_proxy']<0]:
            negative.append(dict(source_csv=str(path),frame_index=int(row['frame_index']),
                                 chunk_time_s=float(row['time_s']),score=float(row['jod_frame_proxy'])))
    write_csv(out/'negative_frames.csv',negative,fields=['source_csv','frame_index','chunk_time_s','score'])
    write_csv(out/'candidates.csv', [{k:v for k,v in c.items() if not k.startswith('source_')} for c in candidates])
    write_csv(out/'predictions.csv',[dict(candidate_id=c['candidate_id'],**dict(zip(RULES,map(float,row)))) for c,row in zip(candidates,pred)])
    write_csv(out/'rule_equivalence.csv',eq)
    write_csv(out/'attack_tasks.csv',tasks)
    write_csv(out/'compact_attack_tasks.csv',compact)
    write_csv(out/'gmad_pairs.csv',full_pairs)
    write_csv(out/'pilot_pairs.csv',pilot)
    write_csv(out/'supplementary_pairs.csv',supplements)
    write_csv(out/'sensitivity.csv',sensitivity)
    config=dict(status='screening_requires_full_video_recheck',scenes=scenes,bins=args.bins,
        settings_per_chunk={scene:len({c['chunk1'] for c in candidates if c['scene']==scene}) for scene in scenes},
        candidates_per_scene={scene:sum(c['scene']==scene for c in candidates) for scene in scenes},
        epsilon_fraction=args.epsilon_fraction,epsilon_cap=args.epsilon_cap,
        min_attack_fraction=args.min_attack_fraction,normalization='within-scene p95-p5 span',
        bins_policy='quantile bins, tied predictions never split',fps=120,frames_per_chunk=180,
        common_input_offset=offset,output_offset_removed=True,input_transform_status='provisional_screening_assumption',
        negative_frame_policy='skip' if args.skip_negative else 'retain',
        time_policy=args.time_policy,
        time_parameters=dict(source_study_fps=PAPER_FPS,display_fps=DISPLAY_FPS,
                             exp_tau_frames=exp_tau,exp_tau_s=exp_tau/DISPLAY_FPS,
                             last_frames=last_frames,last_seconds=last_frames/DISPLAY_FPS,
                             worst_window_frames=worst_window,worst_window_s=worst_window/DISPLAY_FPS,
                             hysteresis_tau_s=2,hysteresis_fps=DISPLAY_FPS,
                             n_segments=3,cumulative_quality='duration weighted; 50/60 s windows reduce to mean'),
        rules=RULES,representative=reps,seed=args.seed,
        input_root=str(args.input.resolve()),
        content_group_policy=('full shot path with / replaced by __' if args.group_by=='shot' else
                              'manifest scene when present; otherwise full shot path with / replaced by __'),
        selection_source_sha256=digest(Path(__file__)),
        source_manifest_sha256=manifest_hash,pooling_source_sha256=digest(Path(pooling.__file__)),
        source_files=provenance)
    (out/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    all_ids={p[key] for p in pairs.values() for key in ('video_a','video_b')}
    pilot_ids={p[key] for p in pilot for key in ('video_a','video_b')}
    for filename,ids in [('selected_video_recipes.json',all_ids),('pilot_video_recipes.json',pilot_ids)]:
        (out/filename).write_text(json.dumps([dict(**lookup[cid],output_name=cid+'.mp4',target_width=1920,target_height=1080,target_fps=120,expected_frames=540) for cid in sorted(ids)],indent=2)+'\n')
    counts={status:sum(t['status']==status for t in tasks) for status in sorted({t['status'] for t in tasks})}
    summary=dict(candidates=len(candidates),rules=len(RULES),effective_rules=len(set(reps.values())),
        scenes=scenes,attack_tasks=len(tasks),task_status=counts,gmad_unique_pairs=len(full_pairs),
        compact_tasks=len(compact),compact_unique_pairs=len({t['pair_id'] for t in compact if t['pair_id']}),
        pilot_unique_pairs=len(pilot),pilot_unique_videos=len(pilot_ids),all_selected_videos=len(all_ids),
        min_raw_score=min(float(row.min()) for row in q),max_raw_score=max(float(row.max()) for row in q),input_offset=offset,
        negative_input_samples=sum(a['negative_frames'] for a in audit),
        skipped_candidate_frame_values=sum(int((row<0).sum()) for row in original_q) if args.skip_negative else 0,
        candidates_with_skipped_frames=sum(bool((row<0).any()) for row in original_q) if args.skip_negative else 0,
        candidate_frame_count_distribution={str(n):sum(len(row)==n for row in q) for n in sorted(set(map(len,q)))},
        sensitivity=sensitivity,
        max_cqm_tail_bias=float(np.abs(legacy-baseline).max()),
        boundary_validation='not yet performed; no final subjective ranking is available')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Structural checks verify every chosen pair and preserve attack orientation.
    for t in tasks:
        if t['status']=='selected':
            assert t['defender_gap']<=t['defender_epsilon']+1e-9
            assert t['attacker_high']>t['attacker_low']
            assert t['attacker_gap']>=t['min_attack_gap']-1e-9
            assert lookup[t['video_high']]['scene']==lookup[t['video_low']]['scene']==t['scene']
    print(json.dumps(summary,indent=2),flush=True)
    render_report(out,summary,config,pilot,eq)


def render_report(out,s,c,pilot,eq):
    esc=html.escape
    rows=''.join('<tr>'+''.join(f'<td>{esc(str(row[k]))}</td>' for k in ('scene','pair_id','settings_a','settings_b','roles','gmad_task_count'))+'</tr>' for row in pilot)
    equival='；'.join(f"{r['rule1']} = {r['rule2']}" for r in eq if r['identical'])
    input_note=(f"删除负分帧，共 {s['negative_input_samples']} 个输入负分样本；"
                f"{s['candidates_with_skipped_frames']} 个候选受影响。"
                if c['negative_frame_policy']=='skip' else '保留负分帧。')
    input_note+=(f"所有规则共用 q′=q+{c['common_input_offset']:.9f}，池化后减回相同偏移。"
                 'Minkowski 与 VQPooling 的偏移敏感性结果见下方文件。参数尚未由主观预实验校准。')
    time_note=(f"指数规则衰减尺度 {c['time_parameters']['exp_tau_s']:g} 秒；"
               f"最差窗口 {c['time_parameters']['worst_window_s']:g} 秒；"
               f"尾部窗口 {c['time_parameters']['last_seconds']:g} 秒。"
               'hysteresis 使用 2 秒；四种位置权重按三段计算；CQM 修正尾部半秒等权问题。')
    page=f'''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>gMAD 选对结果</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;background:#f3f6f8;color:#173447;margin:0}}main{{max-width:1250px;margin:30px auto;padding:28px;background:white;border-radius:16px}}h1{{color:#096c70}}.stats{{display:flex;gap:20px;flex-wrap:wrap}}.stat{{background:#e9f5f3;padding:18px;border-radius:10px}}strong{{font-size:24px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #ccdce2;padding:9px;text-align:left}}th{{background:#e9f5f3}}.note{{background:#fff0d6;padding:16px}}input{{padding:10px;width:350px;max-width:90%}}a{{color:#096c70}}</style><main>
<h1>gMAD 视频初筛已执行</h1><p>{len(s['scenes'])} 个内容组，共 {s['candidates']:,} 个三段设置候选；每段 1.5 秒、统一 120 Hz。同一视频对来自同一内容组。状态：<b>初筛，待完整视频边界复核</b>。</p>
<div class="stats"><div class="stat"><strong>{s['candidates']}</strong><br>候选视频</div><div class="stat"><strong>{s['attack_tasks']}</strong><br>攻击任务</div><div class="stat"><strong>{s['gmad_unique_pairs']}</strong><br>去重 gMAD 视频对</div><div class="stat"><strong>{s['pilot_unique_pairs']}</strong><br>预实验视频对</div></div>
<p>参赛 15 条 RULES，{s['effective_rules']} 组不同预测。完全等价：{esc(equival)}。未加入需要拟合参数的 Hammerstein–Wiener 或使用帧时间输入的两种模型。</p>
<p class="note">逐帧分数实际范围 {s['min_raw_score']:.3f}～{s['max_raw_score']:.3f}。{esc(input_note)}</p>
<p>K={c['bins']}；同内容组、同防守者质量档，并满足防守分差 ≤ min({c['epsilon_cap']:g}, {c['epsilon_fraction']*100:g}% × 防守者 p95−p5)。最大化攻击者分差，要求至少达到攻击者 p95−p5 的 {c['min_attack_fraction']*100:g}%。阈值是本轮初筛的分布规则，不代表人的可觉察差异。</p>
<p>时间参数策略：{esc(c['time_policy'])}。{esc(time_note)}</p>
<p>全任务状态：{esc(json.dumps(s['task_status'],ensure_ascii=False))}。无有效攻击不记为防守获胜。紧凑场景轮换设计为 {s['compact_tasks']} 个任务、{s['compact_unique_pairs']} 个唯一视频对。</p>
<p>预实验每场景最多 10 对 gMAD、2 对独立随机对、2 对诊断对，重复对只播放一次。建议每次观看 A/B 共 9 秒，按每对 20 秒估算，本清单约 {s['pilot_unique_pairs']*20/60:.1f} 分钟纯试次；加入练习、重播与休息后再据实测时长分配被试。A/B 顺序必须随机化；目前没有人评数据，因此没有模型胜负排名。</p>
<p class="note">拼接 chunk 分数忽略了切换处的时间滤波上下文。清单中的视频须实际拼接，并重新计算完整 4.5 秒的 CVVDP 后复核所选不等式。显示设置为 standard_fhd，视频内容连续性也需核对。</p>
<p><a href="pilot_pairs.csv">预实验对清单</a> · <a href="gmad_pairs.csv">全部 gMAD 唯一对</a> · <a href="attack_tasks.csv">攻击任务映射</a> · <a href="compact_attack_tasks.csv">630 任务设计</a> · <a href="predictions.csv">全部候选预测</a> · <a href="sensitivity.csv">敏感性检查</a> · <a href="config.json">全部参数与文件哈希</a> · <a href="pilot_video_recipes.json">预实验视频拼接配方</a></p>
<h2>预实验清单</h2><input id="search" placeholder="按场景、设置或 pair ID 筛选"><div style="overflow:auto"><table><thead><tr><th>场景</th><th>Pair ID</th><th>视频 A 三段设置</th><th>视频 B 三段设置</th><th>用途</th><th>关联 gMAD 任务</th></tr></thead><tbody>{rows}</tbody></table></div>
<script>document.querySelector('#search').addEventListener('input',e=>{{const q=e.target.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));}});</script></main></html>'''
    (out/'report.html').write_text(page)


if __name__=='__main__':main()
