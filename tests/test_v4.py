import io, unittest
from pathlib import Path
import app as a

class V4(unittest.TestCase):
 def setUp(self):
  self.c=a.app.test_client(); self.h={'X-CSRF-Token':'token'}
  with self.c.session_transaction() as s:s['admin']=True;s['csrf']='token'
 def upload(self,path):
  with open(path,'rb') as f:r=self.c.post('/api/admin/upload',data={'file':(io.BytesIO(f.read()),'test.png')},headers=self.h)
  self.assertEqual(r.status_code,200);return r.json['url']
 def test_distinct_canvas_images_and_settings(self):
  one=self.upload(Path(a.ROOT)/'static/favicon.png');duplicate=self.upload(Path(a.ROOT)/'static/favicon.png');two=self.upload(Path(a.ROOT)/'static/sera.webp')
  p=next(x for x in a.projects() if x['slug']=='connect');p.update(cover=one,canvas_images=[duplicate,two],detail_image=two,detail_fit='contain',background_image=one,darkness=43,blur=5)
  self.assertEqual(self.c.post('/api/admin/projects',json=p,headers=self.h).status_code,200)
  p=next(x for x in a.projects() if x['slug']=='connect');cards=a.gallery_assets([p]);self.assertEqual([x['src'] for x in cards],[one,two]);self.assertEqual(len({x['src'] for x in cards}),2)
  page=self.c.get('/ru/project/connect');self.assertEqual(page.status_code,200);self.assertIn('detail-mode-contain',page.text);self.assertIn('rgba(12,12,12,0.43)',page.text);self.assertIn(two,page.text)
  for invalid in (-1,101,True):
   p['darkness']=invalid;self.assertEqual(self.c.post('/api/admin/projects',json=p,headers=self.h).status_code,400)
 def test_unsaved_preview_and_access(self):
  p=next(x for x in a.projects() if x['slug']=='connect');old=p['title']['ru'];p['title']['ru']='ПРЕДПРОСМОТР ТЕСТ';p['published']=False
  r=self.c.post('/api/admin/preview-unsaved/ru',json=p,headers=self.h);self.assertEqual(r.status_code,200);self.assertIn('ПРЕДПРОСМОТР ТЕСТ',r.text);self.assertNotIn('<script',r.text);self.assertIn('noindex',r.headers['X-Robots-Tag']);self.assertEqual(next(x for x in a.projects() if x['slug']=='connect')['title']['ru'],old)
  c=a.app.test_client();self.assertNotEqual(c.post('/api/admin/preview-unsaved/ru',json=p).status_code,200);self.assertNotEqual(c.get('/api/admin/media-audit').status_code,200)
 def test_contacts_and_media_audit(self):
  contacts={'telegram':'https://t.me/aclbt','email':'acoulbot@gmail.com','connect':'http://trioz.ru/connect','discord':'https://discord.com/users/123456789012345678'}
  self.assertEqual(self.c.post('/api/admin/site/contacts',json=contacts,headers=self.h).status_code,200);self.assertIn(contacts['discord'],self.c.get('/ru/').text)
  orphan=self.upload(Path(a.ROOT)/'static/favicon.png').split('/')[-1];r=self.c.get('/api/admin/media-audit');self.assertEqual(r.status_code,200);self.assertIn(orphan,[f['name'] for f in r.json['files']]);self.assertTrue((a.UPLOADS/orphan).exists())
