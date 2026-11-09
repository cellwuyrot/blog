import os,tempfile,sys,json,io,unittest,re,xml.etree.ElementTree as ET
from urllib.parse import urlparse
D=tempfile.TemporaryDirectory();os.environ['DATA_DIR']=D.name;os.environ['SITE_URL']='https://acoulbot.space';sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as a
class Web(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.c=a.app.test_client()
 def test_public(self):
  for lang in ['ru','en']:
   for path in ['','news','about','privacy','project/tophit','project/asiabasa','project/connect','project/sera']:
    r=self.c.get('/'+lang+'/'+path);s=r.get_data(as_text=True);self.assertEqual(r.status_code,200,path);self.assertEqual(len(re.findall(r'<h1\b',s)),1,path);self.assertIn('rel="canonical"',s);self.assertIn('hreflang="en"',s);self.assertIn('property="og:image"',s)
  self.assertEqual(self.c.get('/ru/nope').status_code,404);self.assertEqual(self.c.get('/project/tophit').status_code,301)
  self.assertIn('/ru/project/tophit',self.c.get('/ru/').text)
 def test_sitemap_feed(self):
  r=self.c.get('/sitemap.xml');root=ET.fromstring(r.data);locs=[e.text for e in root.findall('{*}url/{*}loc')];self.assertGreaterEqual(len(locs),16)
  for loc in locs:self.assertEqual(self.c.get(urlparse(loc).path).status_code,200,loc)
  self.assertIn('Sitemap: https://acoulbot.space/sitemap.xml',self.c.get('/robots.txt').text)
  root=ET.fromstring(self.c.get('/ru/feed.xml').data);urls=[i.findtext('link') for i in root.findall('./channel/item')];self.assertTrue(any('journal' in u for u in urls));self.assertFalse(any('tophit' in u for u in urls))
 def test_auth_validation_upload(self):
  self.assertEqual(self.c.get('/api/admin/projects').status_code,401);self.assertEqual(self.c.get('/ru/preview/1').status_code,302)
  with self.c.session_transaction() as s:s['admin']=True;s['csrf']='secret'
  self.assertIn('noindex',self.c.get('/ru/preview/1').headers['X-Robots-Tag'])
  p=a.project('test-example',a.t('','English'),a.t('категория','category'),a.t('описание','description'),'');p['kind']='news'
  self.assertEqual(self.c.post('/api/admin/projects',json=p,headers={'X-CSRF-Token':'secret'}).status_code,400)
  p['published']=False;r=self.c.post('/api/admin/projects',json=p,headers={'X-CSRF-Token':'secret'});self.assertEqual(r.status_code,200);self.assertNotIn('test-example',self.c.get('/sitemap.xml').text)
  p['id']=r.json['id'];p['title']['ru']='Заголовок';p['published']=True;r=self.c.post('/api/admin/projects',json=p,headers={'X-CSRF-Token':'secret'});self.assertEqual(r.status_code,200);self.assertIn('test-example',self.c.get('/ru/feed.xml').text)
  self.assertEqual(self.c.post('/api/admin/upload',data={'file':(io.BytesIO(b'not-image'),'test.png')},headers={'X-CSRF-Token':'secret'}).status_code,400)
  data=b'GIF89a'+b'x'*100;r=self.c.post('/api/admin/upload',data={'file':(io.BytesIO(data),'test.gif')},headers={'X-CSRF-Token':'secret'});self.assertEqual(r.status_code,200);response=self.c.get(r.json['url']);self.assertEqual(response.data,data);response.close()
if __name__=='__main__':unittest.main(verbosity=2)
