import json

def publish_samples(a):
 # Regression tests intentionally exercise the old populated-site scenarios.
 # A real new installation leaves these samples as drafts.
 with a.conn() as db:
  for row in db.execute('SELECT id,data FROM projects').fetchall():
   p=json.loads(row['data'])
   if p.get('slug') in {'tophit','asiabasa','connect','sera','signal','journal'}:
    p['published']=True
    db.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),row['id']))
