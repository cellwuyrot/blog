import os, sys, tempfile, unittest, subprocess
from pathlib import Path
import app as a

class Upgrades(unittest.TestCase):
 def test_new_install_drafts(self):
  with tempfile.TemporaryDirectory() as d:
   env=dict(os.environ,DATA_DIR=d,DATABASE_URL='')
   result=subprocess.run([sys.executable,'-c','import app; print(len(app.projects(True)))'],env=env,cwd=a.ROOT,text=True,capture_output=True,check=True)
   self.assertEqual(result.stdout.strip(),'0')
 def test_inline_auth_csrf_and_escape(self):
  anon=a.app.test_client();self.assertNotIn('inline-editable',anon.get('/ru/?edit=1').text)
  c=a.app.test_client()
  with c.session_transaction() as s:s['admin']=True;s['csrf']='token'
  page=c.get('/ru/?edit=1');self.assertIn('data-copy-key="index_03"',page.text);self.assertIn('no-store',page.headers['Cache-Control'])
  payload={'index_03':{'ru':'<script>bad</script>','en':'Safe text'}}
  self.assertEqual(c.post('/api/admin/site/copy',json=payload).status_code,403)
  self.assertEqual(c.post('/api/admin/site/copy',json=payload,headers={'X-CSRF-Token':'token'}).status_code,200)
  self.assertIn('&lt;script&gt;bad&lt;/script&gt;',c.get('/ru/?edit=1').text)
 def test_visual_modes(self):
  c=a.app.test_client()
  with c.session_transaction() as s:s['admin']=True;s['csrf']='token'
  v={'enabled':True,'captions':False,'photos':[],'mode':'accordion','halftone':False}
  self.assertEqual(c.post('/api/admin/site/visual',json=v,headers={'X-CSRF-Token':'token'}).status_code,200)
  self.assertEqual(a.site_content()['visual']['mode'],'accordion')
  v['mode']='bad';self.assertEqual(c.post('/api/admin/site/visual',json=v,headers={'X-CSRF-Token':'token'}).status_code,400)
