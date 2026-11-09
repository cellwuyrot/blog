import os,sys,tempfile,unittest,io,json
from pathlib import Path
D=tempfile.TemporaryDirectory();os.environ['DATA_DIR']=D.name;sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as a
class SiteEditing(unittest.TestCase):
 def setUp(self):
  self.c=a.app.test_client()
  with self.c.session_transaction() as s:s['admin']=True;s['csrf']='token'
  self.h={'X-CSRF-Token':'token'}
 def post(self,url,data):return self.c.post(url,json=data,headers=self.h)
 def test_text_language_and_escaping(self):
  bad={'index_03':{'ru':'Новая фраза','en':''}}
  self.assertEqual(self.post('/api/admin/site/copy',bad).status_code,400)
  good={'index_03':{'ru':'<script>ru</script>','en':'New English phrase'}}
  self.assertEqual(self.post('/api/admin/site/copy',good).status_code,200)
  self.assertIn('&lt;script&gt;ru&lt;/script&gt;',self.c.get('/ru/').text);self.assertIn('New English phrase',self.c.get('/en/').text)
  self.assertEqual(self.post('/api/admin/site/copy',{'unknown':{'ru':'x','en':'y'}}).status_code,400)
 def test_photos(self):
  upload=self.c.post('/api/admin/upload',data={'file':(io.BytesIO(b'GIF89a'+b'x'*100),'a.gif')},headers=self.h);src=upload.json['url']
  photo={'src':src,'alt':{'ru':'Снимок','en':'Photo'},'caption':{'ru':'','en':''},'focus_x':50,'focus_y':50}
  v={'enabled':True,'captions':False,'photos':[photo]}
  self.assertEqual(self.post('/api/admin/site/visual',v).status_code,200)
  self.assertIn(src,self.c.get('/ru/').text);self.assertEqual(self.post('/api/admin/site/about_photos',v).status_code,200);self.assertIn(src,self.c.get('/en/about').text)
  photo['caption']['ru']='только русский';self.assertEqual(self.post('/api/admin/site/visual',v).status_code,400)
  photo['caption']={'ru':'','en':''};photo['src']='/media/'+'f'*32+'.gif';self.assertEqual(self.post('/api/admin/site/visual',v).status_code,400)
 def test_now_and_related(self):
  self.assertEqual(self.post('/api/admin/site/copy',{'now_text':{'ru':'Пишу','en':''}}).status_code,400)
  self.assertEqual(self.post('/api/admin/site/copy',{'now_text':{'ru':'Пишу','en':'Writing'}}).status_code,200);self.assertIn('Пишу',self.c.get('/ru/').text)
  p=a.project('v3-news',a.t('Новость','News'),a.t('Заметка','Update'),a.t('Текст','Text'),'');p['kind']='news';p['related_id']=1
  r=self.post('/api/admin/projects',p);self.assertEqual(r.status_code,200);self.assertIn('/ru/project/tophit',self.c.get('/ru/project/v3-news').text)
  p['related_id']=999999;self.assertEqual(self.post('/api/admin/projects',p).status_code,400)
 def test_contacts_and_partial_updates(self):
  data={'telegram':'https://example.org/andys','email':'andy@example.org','connect':''}
  self.assertEqual(self.post('/api/admin/site/contacts',data).status_code,200)
  html=self.c.get('/ru/about').text;self.assertIn('andy@example.org',html);self.assertIn('https://example.org/andys',html)
  self.assertEqual(self.post('/api/admin/site/contacts',dict(data,telegram='javascript:alert(1)')).status_code,400)
  self.assertEqual(self.post('/api/admin/site/copy',{'hero_author':{'ru':'Автор','en':'Author'}}).status_code,200)
  self.assertIn('andy@example.org',self.c.get('/ru/about').text)
  self.assertIn('Автор',self.c.get('/ru/').text)
 def test_unauthorized(self):
  c=a.app.test_client();self.assertEqual(c.get('/api/admin/site').status_code,401);self.assertEqual(c.post('/api/admin/site/copy',json={}).status_code,401)
