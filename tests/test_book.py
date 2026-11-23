import os,sys,tempfile,unittest,io,copy
D=tempfile.TemporaryDirectory();os.environ.setdefault('DATA_DIR',D.name);os.environ.setdefault('SITE_URL','https://acoulbot.space');sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import app as a
import book_module as bm

def loc(ru='',en=''):return {'ru':ru,'en':en}
def version(title='',body='',description='',index=True):return dict(title=title,body=body,description=description,index=index)
class BookTests(unittest.TestCase):
 def setUp(self):
  a.put_setting('confrontation_v1','{}');a.put_setting('seo_overrides_v1','{}')
  self.admin=a.app.test_client();self.guest=a.app.test_client()
  with self.admin.session_transaction() as s:s['admin']=True;s['csrf']='book-test'
  self.h={'X-CSRF-Token':'book-test'}
  self.book=bm.empty_book()
  self.chapter={'id':'1111111111111111','number':3,'title':loc('Глава','Chapter'),'cover':'','parts':[]}
  for i in (1,2):
   self.chapter['parts'].append({'id':str(i+1)*16,'number':i,'draft':{'ru':version('Часть '+str(i),'Текст **жирный** и *курсив*.\n\n<script>alert(1)</script>', 'Описание'), 'en':version()},'live':{'ru':None,'en':None}})
  self.book['chapters'].append(self.chapter)
  self.ent={'id':'4444444444444444','name':loc('Герой','Hero'),'portrait':'','portrait_public':False,'published':True,'after':'','private':{'f_notes':'SECRET_PRIVATE_STRING'},'facts':[{'id':'5555555555555555','label':loc('Деталь','Detail'),'text':loc('PUBLIC_AFTER_FIRST','PUBLIC_AFTER_FIRST'),'public':True,'after':'2222222222222222'}, {'id':'6666666666666666','label':loc('Секрет','Secret'),'text':loc('SECRET_AUTHOR_ONLY','SECRET_AUTHOR_ONLY'),'public':False,'after':''}],'relations':[]}
  self.book['characters'].append(self.ent)
 def save(self,b=None):return self.admin.post('/api/admin/book',json=b or self.book,headers=self.h)
 def test_drafts_auth_private_preview_and_formatting(self):
  self.assertEqual(self.guest.get('/api/admin/book').status_code,401)
  self.assertEqual(self.admin.post('/api/admin/book',json=self.book).status_code,403)
  self.assertEqual(self.save().status_code,200)
  path='/ru/book/'+self.chapter['id']+'/'+self.chapter['parts'][0]['id']
  self.assertEqual(self.guest.get(path).status_code,404)
  preview=self.admin.post('/api/admin/book/preview',json=dict(lang='ru',**self.chapter['parts'][0]['draft']['ru']),headers=self.h)
  self.assertEqual(preview.status_code,200);self.assertIn('noindex',preview.headers['X-Robots-Tag']);self.assertIn('<strong>жирный</strong>',preview.text);self.assertIn('<em>курсив</em>',preview.text);self.assertNotIn('<script>alert(1)</script>',preview.text)
  self.assertNotIn('SECRET_PRIVATE_STRING',self.guest.get('/ru/book/world').text)
  self.assertNotIn('PUBLIC_AFTER_FIRST',self.guest.get('/ru/book/world').text)
 def test_publication_spoilers_translation_and_sitemap(self):
  p=self.chapter['parts'][0];p['live']['ru']=copy.deepcopy(p['draft']['ru']);r=self.save();self.assertEqual(r.status_code,200,r.text);self.book['revision']=r.json['revision']
  path='/ru/book/'+self.chapter['id']+'/'+p['id'];body=self.guest.get(path)
  self.assertEqual(body.status_code,200);self.assertIn('<strong>жирный</strong>',body.text);self.assertNotIn('<script>alert(1)</script>',body.text)
  self.assertIn('nosnippet',body.text);wait=self.guest.get(path.replace('/ru/','/en/'));self.assertEqual(wait.status_code,200);self.assertIn('noindex',wait.headers['X-Robots-Tag'])
  sm=self.guest.get('/sitemap.xml').text;self.assertIn(path,sm);self.assertNotIn(path.replace('/ru/','/en/'),sm)
  base=self.guest.get('/ru/book/world').text;self.assertIn('Герой',base);detail='/ru/book/world/'+self.ent['id'];self.assertEqual(self.guest.get(detail).status_code,200);self.assertNotIn('SECRET_PRIVATE_STRING',self.guest.get(detail).text);self.assertIn(detail,self.guest.get('/sitemap.xml').text);self.assertNotIn('PUBLIC_AFTER_FIRST',base);self.assertNotIn('SECRET_AUTHOR_ONLY',base);self.assertNotIn('SECRET_PRIVATE_STRING',base)
  after=self.guest.get('/ru/book/world?through='+p['id']);self.assertIn('PUBLIC_AFTER_FIRST',after.text);self.assertNotIn('SECRET_AUTHOR_ONLY',after.text);self.assertNotIn('SECRET_PRIVATE_STRING',after.text);self.assertIn('noindex',after.headers['X-Robots-Tag'])
  self.ent['after']=p['id'];r=self.save();self.assertEqual(r.status_code,200);self.book['revision']=r.json['revision'];self.assertNotIn('Герой',self.guest.get('/ru/book/world').text);self.assertIn('Герой',self.guest.get('/ru/book/world?through='+p['id']).text);self.assertEqual(self.guest.get(detail).status_code,404);d=self.guest.get(detail+'?through='+p['id']);self.assertEqual(d.status_code,200);self.assertIn('noindex',d.headers['X-Robots-Tag']);self.assertNotIn(detail,self.guest.get('/sitemap.xml').text)
 def test_revision_seo_image_and_limits(self):
  image=self.admin.post('/api/admin/book/image',data={'file':(io.BytesIO(b'GIF89a'+b'0'*20),'x.gif')},headers=self.h);self.assertEqual(image.status_code,200);name=image.json['name'];self.ent['portrait']=name
  first=self.save();self.assertEqual(first.status_code,200);self.assertEqual(self.save().status_code,409);self.book['revision']=first.json['revision']
  self.assertEqual(self.guest.get('/book-media/'+name).status_code,404);response=self.admin.get('/book-media/'+name);self.assertEqual(response.status_code,200);response.close()
  self.ent['portrait_public']=True;r=self.save();self.assertEqual(r.status_code,200);self.book['revision']=r.json['revision'];response=self.guest.get('/book-media/'+name);self.assertEqual(response.status_code,200);response.close()
  dupe=copy.deepcopy(self.chapter);dupe['id']='7777777777777777';dupe['parts']=[];self.book['chapters'].append(dupe);self.assertEqual(self.save().status_code,400);self.book['chapters'].pop()
  seo={'ru/book':{'title':'Своя книга','description':'Без спойлеров','index':False}};self.assertEqual(self.admin.post('/api/admin/seo',json=seo,headers=self.h).status_code,200);self.assertIn('noindex',self.guest.get('/ru/book').text);self.assertNotIn('https://acoulbot.space/ru/book</loc>',self.guest.get('/sitemap.xml').text)
 def test_relationships_follow_reading_and_do_not_reveal_hidden_targets(self):
  p1,p2=self.chapter['parts']
  for p in (p1,p2):p['live']['ru']=copy.deepcopy(p['draft']['ru'])
  other={'id':'8888888888888888','name':loc('Друг','Friend'),'portrait':'','portrait_public':False,'published':True,'after':'','private':{},'facts':[],'relations':[]}
  self.book['characters'].append(other)
  self.ent['relations']=[{'id':'9999999999999999','label':loc('Знакомы',''),'text':loc('старое отношение',''),'public':True,'after':'','target':other['id']},{'id':'aaaaaaaaaaaaaaaa','label':loc('Друзья',''),'text':loc('новое отношение',''),'public':True,'after':p1['id'],'target':other['id']}]
  self.assertEqual(self.save().status_code,200)
  early=self.guest.get('/ru/book/world').text;later=self.guest.get('/ru/book/world?through='+p1['id']).text
  self.assertIn('старое отношение',early);self.assertNotIn('новое отношение',early)
  self.assertIn('новое отношение',later);self.assertNotIn('старое отношение',later)
  self.book['revision']=1;other['after']=p2['id'];self.assertEqual(self.save().status_code,200)
  later=self.guest.get('/ru/book/world?through='+p1['id']).text;self.assertNotIn('Друг',later);self.assertNotIn('новое отношение',later)
 def test_portrait_checkpoint(self):
  p=self.chapter['parts'][0];p['live']['ru']=copy.deepcopy(p['draft']['ru'])
  upload=self.admin.post('/api/admin/book/image',data={'file':(io.BytesIO(b'GIF89a'+b'0'*20),'x.gif')},headers=self.h);name=upload.json['name']
  self.ent.update(portrait=name,portrait_public=True,after=p['id']);self.assertEqual(self.save().status_code,200)
  self.assertEqual(self.guest.get('/book-media/'+name).status_code,404)
  res=self.guest.get('/book-media/'+name+'?through='+p['id']);self.assertEqual(res.status_code,200);self.assertIn('noindex',res.headers['X-Robots-Tag']);res.close()
  self.assertNotIn(name,self.guest.get('/ru/book/world').text);self.assertIn(name,self.guest.get('/ru/book/world?through='+p['id']).text)
 def test_long_document(self):
  p=self.chapter['parts'][0];p['draft']['ru']['body']='Слово '*90000;r=self.save();self.assertEqual(r.status_code,200,r.text);self.book['revision']=r.json['revision'];got=self.admin.get('/api/admin/book').json;self.assertEqual(len(got['chapters'][0]['parts'][0]['draft']['ru']['body'].split()),90000)
if __name__=='__main__':unittest.main()
