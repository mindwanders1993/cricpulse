import sys, time, duckdb, os
S = sys.argv[1]; n = f"{S}/nopk_build.duckdb"
if os.path.exists(n): os.remove(n)
t = time.time()
c = duckdb.connect(n)
c.execute("SET memory_limit='2GB'"); c.execute(f"SET temp_directory='{S}/spill'")
c.execute("CREATE SCHEMA gold")
for tbl, src in [("fact_delivery","deliveries"),("fact_innings","innings"),("fact_wicket_detail","wickets"),("fact_player_match","match_players"),("dim_match","matches")]:
    c.execute(f"CREATE TABLE gold.{tbl} AS SELECT * FROM read_parquet('{S}/silver/{src}.parquet')")
c.execute("CHECKPOINT"); c.close()
print("build_s", round(time.time()-t,1), "mb", round(os.path.getsize(n)/1048576,1))
