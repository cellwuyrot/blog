import unittest, io, os, tempfile
from pathlib import Path
D = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = D.name
import app as a

class Images(unittest.TestCase):
 def setUp(self):
  self.c=a.app.test_client(); self.h={'X-CSRF-Token':'token'}
  with self.c.session_transaction() as s: s['admin']=True; s['csrf']='token'
 def upload(self):
  f=io.BytesIO((Path(a.ROOT)/'static'/'favicon.png').read_bytes())
  r=self.c.post('/api/admin/upload',data={'file':(f,'image.png')},headers=self.h);self.assertEqual(r.status_code,200);return r.json['url']
 def test_separate_media_and_legacy(self):
  cover=self.upload(); art=self.upload(); p=next(x for x in a.projects() if x['slug']=='connect'); p.update(cover=cover,feature_image=art,cover_fit='contain')
  r=self.c.post('/api/admin/projects',json=p,headers=self.h);self.assertEqual(r.status_code,200)
  html=self.c.get('/ru/').text
  self.assertIn('class="feature-image" src="'+art+'"',html);self.assertIn(cover,html);self.assertIn('"cover_fit": "contain"',html)
  p['feature_image']='';p['cover_fit']='invalid';self.assertEqual(self.c.post('/api/admin/projects',json=p,headers=self.h).status_code,400)
  p.pop('feature_image');p.pop('cover_fit');self.assertEqual(self.c.post('/api/admin/projects',json=p,headers=self.h).status_code,200)
  self.assertIn('class="orbit one"',self.c.get('/ru/').text)
