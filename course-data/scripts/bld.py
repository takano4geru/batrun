import json,sys,fsspec,pyarrow.parquet as pq, pyarrow.compute as pc, pyarrow as pa
B="https://overturemaps-us-west-2.s3.amazonaws.com"
hits=json.load(open(sys.argv[1])); BB=(130.25,33.50,130.52,33.72)
fs=fsspec.filesystem("https"); tabs=[]
cols=["id","names","subtype","class","height","num_floors","roof_shape","is_underground","sources","geometry","bbox"]
for k,gs in hits:
    f=pq.ParquetFile(fs.open(f"{B}/{k}",block_size=2**22))
    for g in gs:
        t=f.read_row_group(g,columns=[c for c in cols if c in f.schema_arrow.names])
        b=t["bbox"].combine_chunks()
        m=pc.and_(pc.and_(pc.less_equal(b.field("xmin"),BB[2]),pc.greater_equal(b.field("xmax"),BB[0])),pc.and_(pc.less_equal(b.field("ymin"),BB[3]),pc.greater_equal(b.field("ymax"),BB[1])))
        t=t.filter(m); tabs.append(t); print(g,t.num_rows,flush=True)
pq.write_table(pa.concat_tables(tabs),sys.argv[2])
