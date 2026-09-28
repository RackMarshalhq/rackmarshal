#!/usr/bin/env python3
import argparse,json,os,sqlite3
p=argparse.ArgumentParser(); p.add_argument('--db'); p.add_argument('--observation-id',type=int,required=True); a=p.parse_args(); c=sqlite3.connect(a.db); row=c.execute('select observed_at from observations where id=?',(a.observation_id,)).fetchone(); c.close(); mode=os.environ.get('RACKMARSHAL_FIXTURE_MODE','bad')
outcome='STATUS-CHANGED' if mode=='bad' else 'MATCH'
print(json.dumps({'schema_version':1,'comparator':'fixture','observation_id':a.observation_id,'observed_at':row[0],'differences':0 if outcome=='MATCH' else 1,'results':[{'resource_type':'ha_core','resource_key':'home_assistant_core','display_name':'Fictional Core','baseline_state':'VERIFIED','expected_status':'RUNNING','actual_status':'STOPPED' if outcome!='MATCH' else 'RUNNING','outcome':outcome}]}))
