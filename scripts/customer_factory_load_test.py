#!/usr/bin/env python3
"""Low-cost concurrent API load harness using isolated synthetic customers."""
from __future__ import annotations
import argparse, asyncio, statistics, time, uuid
import httpx

async def one(base: str, idx: int, missions: int) -> tuple[list[float], list[str]]:
    errors=[]; lat=[]
    async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:
        email=f"load-{uuid.uuid4().hex[:10]}-{idx}@example.test"; password="LoadTest!23456"
        t=time.perf_counter(); r=await client.post('/api/customer/register',json={'email':email,'password':password}); lat.append((time.perf_counter()-t)*1000)
        if r.status_code != 200: return lat,[f"register:{r.status_code}:{r.text[:100]}"]
        token=r.json().get('access_token'); headers={'Authorization':f'Bearer {token}'}
        t=time.perf_counter(); r=await client.get('/api/customer/factory',headers=headers); lat.append((time.perf_counter()-t)*1000)
        if r.status_code != 200: errors.append(f"factory:{r.status_code}")
        for m in range(missions):
            t=time.perf_counter(); r=await client.post('/api/customer/factory/mission',headers=headers,json={'prompt':f'Synthetic load mission {idx}-{m}: research a local service opportunity with defensible evidence.'}); lat.append((time.perf_counter()-t)*1000)
            if r.status_code not in (200,402): errors.append(f"mission:{r.status_code}:{r.text[:100]}")
        for _ in range(5):
            t=time.perf_counter(); r=await client.get('/api/customer/factory',headers=headers); lat.append((time.perf_counter()-t)*1000)
            if r.status_code != 200: errors.append(f"poll:{r.status_code}")
    return lat,errors

async def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base',default='http://127.0.0.1:18081'); ap.add_argument('--customers',type=int,default=12); ap.add_argument('--missions',type=int,default=1); args=ap.parse_args()
    started=time.perf_counter(); results=await asyncio.gather(*(one(args.base,i,args.missions) for i in range(args.customers)))
    lat=[v for a,_ in results for v in a]; errors=[e for _,b in results for e in b]; elapsed=time.perf_counter()-started
    lat_sorted=sorted(lat); p95=lat_sorted[min(len(lat_sorted)-1,max(0,int(len(lat_sorted)*.95)-1))] if lat_sorted else 0
    print({'customers':args.customers,'requests':len(lat),'errors':len(errors),'elapsed_s':round(elapsed,2),'rps':round(len(lat)/elapsed,2) if elapsed else 0,'median_ms':round(statistics.median(lat),1) if lat else 0,'p95_ms':round(p95,1),'max_ms':round(max(lat),1) if lat else 0,'error_samples':errors[:10]})
    raise SystemExit(1 if errors else 0)

if __name__=='__main__': asyncio.run(main())
