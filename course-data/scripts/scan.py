import sys, json, re, subprocess, fsspec, pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor
B="https://overturemaps-us-west-2.s3.amazonaws.com"; R="release/2026-09-23.1"
theme=sys.argv[1]; out=sys.argv[2]
BB=(130.25,33.50,130.52,33.72)
keys=[]; tok=None
while True:
    u=f"{B}/?list-type=2&prefix={R}/{theme}/"+(f"&continuation-token={tok}" if tok else "")
    x=subprocess.run(["curl","-sS","-m","60","-G",f"{B}/","--data-urlencode","list-type=2","--data-urlencode",f"prefix={R}/{theme}/"]+(["--data-urlencode",f"continuation-token={tok}"] if tok else []),capture_output=True,text=True).stdout
    keys+=re.findall(r"<Key>([^<]*)",x); m=re.search(r"<NextContinuationToken>([^<]*)",x)
    if not m: break
    tok=m.group(1)
fs=fsspec.filesystem("https")
def chk(k):
    try:
        f=pq.ParquetFile(fs.open(f"{B}/{k}",block_size=2**20))
        md=f.metadata; names=[md.schema.column(i).path for i in range(md.num_columns)]
        ix={n:names.index(f"bbox.{n}") for n in ["xmin","ymin","xmax","ymax"]}
        hits=[]
        for g in range(md.num_row_groups):
            rg=md.row_group(g); s={n:rg.column(i).statistics for n,i in ix.items()}
            if s["xmin"].min<=BB[2] and s["xmax"].max>=BB[0] and s["ymin"].min<=BB[3] and s["ymax"].max>=BB[1]: hits.append(g)
        return k,hits
    except Exception as e: return k,str(e)
with ThreadPoolExecutor(16) as ex: res=[r for r in ex.map(chk,keys) if r[1]]
json.dump(res,open(out,"w")); print(len(keys),res)
