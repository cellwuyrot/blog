import os,sys,tempfile,copy,unittest
D=tempfile.TemporaryDirectory();os.environ.setdefault('DATA_DIR',D.name);os.environ.setdefault('SITE_URL','https://acoulbot.space');sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import app as a
import book_module as bm

def L(ru='',en=''):return {'ru':ru,'en':en}
def V(body='текст'):return {'title':'','body':body,'description':'','index':True}
def character(id,name,after='',published=True):return {'id':id,'name':L(name,name),'portrait':'','portrait_public':False,'published':published,'after':after,'private':{'f_notes':'VERY_SECRET_DOSSIER'},'facts':[],'relations':[]}
class ReaderScene(unittest.TestCase):
 def setUp(self):
  a.put_setting('confrontation_v1','{}');self.admin=a.app.test_client();self.visitor=a.app.test_client();
  with self.admin.session_transaction() as s:s['admin']=True;s['csrf']='csrf'
  self.headers={'X-CSRF-Token':'csrf'};self.b=bm.empty_book();self.c={'id':'1111111111111111','number':3,'title':L('Тест'), 'cover':'','parts':[]};self.b['chapters']=[self.c]
  for id,num in [('2222222222222222',4),('3333333333333333',5),('4444444444444444',6)]:self.c['parts'].append({'id':id,'number':num,'draft':{'ru':V(),'en':V('')},'live':{'ru':V(),'en':None},'scene':bm.empty_scene(),'scene_live':{'ru':None,'en':None}})
  self.b['characters']=[character('aaaaaaaaaaaaaaaa','Алиса'),character('bbbbbbbbbbbbbbbb','Борис','2222222222222222'),character('cccccccccccccccc','Скрытый','3333333333333333'),character('dddddddddddddddd','Черновик',published=False)]
  self.scene={'cast':[{'entity':e['id'],'note':L('NOTE_'+str(i))} for i,e in enumerate(self.b['characters'])], 'relations':[{'id':'eeeeeeeeeeeeeeee','source':'aaaaaaaaaaaaaaaa','target':'bbbbbbbbbbbbbbbb','label':L('Доверие'),'text':L('RELATION_VISIBLE')}, {'id':'ffffffffffffffff','source':'aaaaaaaaaaaaaaaa','target':'cccccccccccccccc','label':L('SECRET_RELATION'),'text':L('SECRET_RELATION_BODY')}]}
  self.c['parts'][1]['scene']=copy.deepcopy(self.scene);self.c['parts'][1]['scene_live']['ru']=copy.deepcopy(self.scene)
 def post(self):return self.admin.post('/api/admin/book',json=self.b,headers=self.headers)
 def url(self,part):return '/ru/book/'+self.c['id']+'/'+part['id']
 def test_part_visibility_snapshot_and_spoilers(self):
  r=self.post();self.assertEqual(r.status_code,200,r.text);self.b['revision']=r.json['revision'];p4,p5,p6=self.c['parts']
  before=self.visitor.get(self.url(p4)).text;current=self.visitor.get(self.url(p5)).text;later=self.visitor.get(self.url(p6)).text
  for text in (before,current,later):self.assertNotIn('VERY_SECRET_DOSSIER',text);self.assertNotIn('SECRET_RELATION_BODY',text)
  self.assertNotIn('RELATION_VISIBLE',before);self.assertNotIn('RELATION_VISIBLE',later);self.assertIn('RELATION_VISIBLE',current);self.assertIn('Алиса',current);self.assertIn('Борис',current);self.assertNotIn('Скрытый',current);self.assertNotIn('Черновик',current);self.assertNotIn('NOTE_2',current);self.assertNotIn('SECRET_RELATION',current)
  p5['scene']['relations'][0]['text']['ru']='UNPUBLISHED_REVISION';r=self.post();self.assertEqual(r.status_code,200);self.b['revision']=r.json['revision'];self.assertNotIn('UNPUBLISHED_REVISION',self.visitor.get(self.url(p5)).text)
  p5['scene_live']['ru']=copy.deepcopy(p5['scene']);r=self.post();self.assertEqual(r.status_code,200);self.assertIn('UNPUBLISHED_REVISION',self.visitor.get(self.url(p5)).text)
  wait=self.visitor.get(self.url(p5).replace('/ru/','/en/'));self.assertIn('noindex',wait.headers['X-Robots-Tag']);self.assertNotIn('NOTE_',wait.text)
 def test_invalid_reference_and_self_connection_rejected(self):
  self.c['parts'][1]['scene']['cast'][0]['entity']='9999999999999999';self.assertEqual(self.post().status_code,400)
  self.c['parts'][1]['scene']=copy.deepcopy(self.scene);self.c['parts'][1]['scene']['relations'][0]['target']='aaaaaaaaaaaaaaaa';self.assertEqual(self.post().status_code,400)
 def test_malformed_request_does_not_crash(self):
  self.c['parts']=None;self.assertEqual(self.post().status_code,400)
  self.c['parts']=[];self.b['characters'][0]['facts']=None;self.assertEqual(self.post().status_code,400)
 def test_legacy_parts_gain_optional_fields_without_losing_data(self):
  part=self.c['parts'][0];del part['scene'];del part['scene_live'];self.assertEqual(self.post().status_code,200);saved=self.admin.get('/api/admin/book').json['chapters'][0]['parts'][0];self.assertEqual(saved['scene']['cast'],[]);self.assertIsNone(saved['scene_live']['ru']);self.assertEqual(saved['live']['ru']['body'],'текст')
if __name__=='__main__':unittest.main()
