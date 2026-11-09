import os, sys, re, json, sqlite3, time, secrets, hashlib, base64, urllib.parse, urllib.request, urllib.error, threading, shutil
from pathlib import Path
from functools import wraps
from contextlib import contextmanager
os.umask(0o077)
from flask import Flask, request, session, jsonify, render_template, redirect, send_from_directory, abort, Response
from xml.etree import ElementTree as ET
from email.utils import formatdate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import RequestEntityTooLarge
from copy_fields import FIELDS, BY_KEY

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('DATA_DIR', ROOT/'data')).resolve(); DATA.mkdir(parents=True, exist_ok=True)
UPLOADS=DATA/'uploads'; UPLOADS.mkdir(exist_ok=True)
DB=DATA/'site.sqlite3'

def load_env():
 p=ROOT/'.env'
 if p.exists():
  for line in p.read_text().splitlines():
   if line.strip() and not line.lstrip().startswith('#') and '=' in line:
    k,v=line.split('=',1);os.environ.setdefault(k.strip(),v.strip().strip('"\''))
load_env()
# DATA_DIR is best provided in the process environment (e.g. systemd).
keyfile=DATA/'secret_key'
if not keyfile.exists():
 keyfile.write_text(secrets.token_hex(32)); keyfile.chmod(0o600)
app=Flask(__name__)
app.secret_key=os.environ.get('SECRET_KEY') or keyfile.read_text().strip()
app.config.update(MAX_CONTENT_LENGTH=150*1024*1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','0')=='1', PERMANENT_SESSION_LIFETIME=28800)
if os.environ.get('TRUST_PROXY')=='1': app.wsgi_app=ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

@contextmanager
def conn():
 db=sqlite3.connect(DB,timeout=15);db.row_factory=sqlite3.Row
 try:
  with db: yield db
 finally: db.close()

def init_db():
 with conn() as db:
  db.executescript('''PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, data TEXT NOT NULL, updated INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
  ''')
  if not db.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
   for p in SEED:
    db.execute('INSERT INTO projects(slug,data,updated) VALUES(?,?,?)',(p['slug'],json.dumps(p,ensure_ascii=False),int(time.time())))
  db.execute("INSERT OR IGNORE INTO settings VALUES('playlist','')")
  db.execute("INSERT OR IGNORE INTO settings VALUES('seeded','1')")
  # Prevent recreating sample entries after all entries are intentionally deleted.

def t(ru,en): return {'ru':ru,'en':en}
def block(kind,ru='',en='',hru='',hen='',media=''):
 return {'type':kind,'heading':t(hru,hen),'text':t(ru,en),'media':media,'alt':t('','')}
def project(slug,title,cat,summary,url,feature='',cover='',background='#161616',blocks=None,published=True):
 return {'slug':slug,'title':title,'category':cat,'summary':summary,'url':url,'feature':feature,'cover':cover,'background':background,'background_image':'','blur':18,'published':published,'blocks':blocks or []}
SEED=[
 project('tophit',t('Топхит','Tophit'),t('ИНТЕРНЕТ-МАГАЗИН','ONLINE STORE'),t('Товары на каждый день — в одном месте.','Everyday essentials, all in one place.'),'https://tophitt.ru/',blocks=[block('text','Магазин товаров повседневного спроса для дома и бизнеса.','An online store for everyday goods for home and business.','О проекте','About the project'),block('image_left','Здесь можно рассказать о процессе, решениях и деталях проекта. Замените этот текст своим описанием.','Use this space to share the process, decisions and details behind the project. Replace this text with your own.','Продолжение','The story')]),
 project('asiabasa',t('AsiaBasa','AsiaBasa'),t('ИНТЕРНЕТ-МАГАЗИН','ONLINE STORE'),t('Подарочные наборы и вкусы стран Азии.','Curated gift sets and flavours from across Asia.'),'https://asia-basa.ru/',blocks=[block('text','Магазин азиатских продуктов и тематических подарочных наборов.','A store for Asian products and curated gift sets.','О проекте','About the project'),block('image_right','Добавьте фотографии, расскажите о деталях проекта и своём участии.','Add your images and describe the project and your contribution.','Детали','Details')]),
 project('connect',t('Connect','Connect'),t('ЦИФРОВАЯ СРЕДА','DIGITAL SPACE'),t('Пространство для общения, связей и новых идей.','A space for conversations, connections and new ideas.'),'http://trioz.ru/connect','connect',blocks=[block('text','Connect — многофункциональный мессенджер, созданный для общения и совместных пространств.','Connect is a multifunctional messenger created for conversation and shared spaces.','Связь без лишних границ','Connection without unnecessary boundaries'),block('video','Здесь можно разместить короткое видео о Connect.','A short video about Connect can live here.','В движении','In motion')]),
 project('sera',t('Сера','Sera'),t('РОМАН В ПРОЦЕССЕ','NOVEL IN PROGRESS'),t('Планета. Обычные жители. Необычные обстоятельства.','A planet. Ordinary people. Extraordinary circumstances.'),'','book','/static/sera.webp','#111111',[block('text','Фантастический роман-антиутопия о планете Сера и её обычных жителях, которые сталкиваются с необычными ситуациями.','A dystopian science-fiction novel about the planet Sera and ordinary people facing extraordinary circumstances.','История рождается','A story in progress')]),
 project('signal',t('Signal','Signal'),t('ШАБЛОН ПРОЕКТА','PROJECT TEMPLATE'),t('Пример будущего проекта. Замените текст и изображение.','A sample future project. Replace the text and image.'),'',blocks=[block('text','Это демонстрационная запись. Добавьте свою историю, изображения и ссылки.','This is a sample entry. Add your own story, images and links.','Здесь может быть ваша идея','Your idea could live here')]),
 project('journal',t('Новая запись','New entry'),t('ШАБЛОН НОВОСТИ','NEWS TEMPLATE'),t('Пример записи о работе, идее или событии.','A sample update about a project, idea or event.'),'',blocks=[block('text','Расскажите, над чем работаете сейчас. Это пример, который можно изменить или удалить.','Share what you are working on. This is a sample you can edit or delete.','Заметки','Notes')]),
]

# Fresh installations contain a clearly marked sample news item.
SEED[-1]['kind'] = 'news'

def projects(pub=False):
 with conn() as db: rows=db.execute('SELECT id,data,updated FROM projects ORDER BY id').fetchall()
 result=[]
 for r in rows:
  p=json.loads(r['data']);p['id']=r['id'];p['updated']=r['updated'];p.setdefault('kind', 'news' if p.get('slug') == 'journal' and p.get('category',{}).get('ru') == 'ШАБЛОН НОВОСТИ' else 'project');p.setdefault('published_at',r['updated']);p.setdefault('related_id',None)
  if not pub or p.get('published'): result.append(p)
 return result

def setting(key,default=''):
 with conn() as db: r=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
 return r[0] if r else default

def put_setting(key,value):
 with conn() as db: db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))

def site_content():
 try:
  data=json.loads(setting('site_content_v3','{}'))
  return data if isinstance(data,dict) else {}
 except (ValueError,TypeError):return {}

def site_copy(data,key,lang):
 default=BY_KEY.get(key,{}); custom=data.get('copy',{}).get(key,{})
 return custom.get(lang,default.get(lang,''))

def save_site_part(part,value):
 # SQLite transaction serializes partial updates; existing v1/v2 data is untouched.
 with conn() as db:
  db.execute("BEGIN IMMEDIATE")
  row=db.execute("SELECT value FROM settings WHERE key='site_content_v3'").fetchone()
  try: data=json.loads(row[0]) if row else {}
  except (ValueError,TypeError): data={}
  if not isinstance(data,dict):data={}
  if part=='copy':data.setdefault('copy',{}).update(value)
  else:data[part]=value
  db.execute("INSERT INTO settings(key,value) VALUES('site_content_v3',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(data,ensure_ascii=False),))

def logged():return session.get('admin') is True

def admin_required(f):
 @wraps(f)
 def inner(*a,**kw):
  if not logged(): return jsonify(error='Требуется вход'),401
  return f(*a,**kw)
 return inner

def csrf_required(f):
 @wraps(f)
 def inner(*a,**kw):
  token=request.headers.get('X-CSRF-Token','')
  if not token or not secrets.compare_digest(token,session.get('csrf','')): return jsonify(error='Ошибка безопасности. Обновите страницу.'),403
  return f(*a,**kw)
 return inner

def valid_url(v):
 if not v:return True
 if not isinstance(v,str) or any(c.isspace() or ord(c)<32 for c in v):return False
 try:
  u=urllib.parse.urlsplit(v);return u.scheme in ('http','https') and bool(u.netloc) and not u.username and not u.password
 except ValueError:return False

def validate(p):
 if not isinstance(p,dict):return 'Некорректная запись'
 if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',str(p.get('slug',''))) or len(p['slug'])>80:return 'Адрес: только латинские буквы, цифры и дефис'
 for name in ('title','summary','category'):
  if not isinstance(p.get(name),dict):return 'Заполните языковые поля'
  for lang in ('ru','en'):
   v=p[name].get(lang,'')
   if not isinstance(v,str) or len(v)>2000:return 'Некорректное текстовое поле'
   if p.get('published') and not v.strip():return f'Для публикации заполните {name} на двух языках'
 if not valid_url(p.get('url','')):return 'Ссылка должна начинаться с http:// или https://'
 if p.get('feature','') not in ('','connect','book'):return 'Некорректный тип'
 if p.get('kind','project') not in ('project','news'):return 'Некорректный формат публикации'
 if p.get('kind')=='news' and p.get('feature'):return 'Специальный раздел доступен только для проектов'
 related=p.get('related_id')
 if related not in (None,'') and (isinstance(related,bool) or not isinstance(related,int) or related<=0 or p.get('kind')!='news'):return 'Некорректный связанный проект'
 if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(p.get('background',''))):return 'Выберите цвет фона'
 if not isinstance(p.get('blur'),(int,float)) or not 0<=p['blur']<=60:return 'Некорректное размытие'
 def media_ok(s):return not s or bool(re.fullmatch(r'/media/[a-f0-9]{32}\.(?:png|jpg|gif|webp|mp4|webm)',s)) or s=='/static/sera.webp'
 if not media_ok(p.get('cover','')) or not media_ok(p.get('background_image','')) or any(str(p.get(k,'')).endswith(('.mp4','.webm')) for k in ('cover','background_image')):return 'Для обложки и фона выберите изображение'
 if not media_ok(p.get('feature_image','')) or str(p.get('feature_image','')).endswith(('.mp4','.webm')):return 'Для отдельного раздела выберите изображение'
 if p.get('cover_fit') not in (None,'','contain','cover'):return 'Некорректный режим изображения на холсте'
 if not isinstance(p.get('blocks'),list) or len(p['blocks'])>40:return 'Слишком много элементов'
 for b in p['blocks']:
  if not isinstance(b,dict) or b.get('type') not in ('text','image_left','image_right','image','video'):return 'Неизвестный элемент'
  if not media_ok(b.get('media','')):return 'Некорректный файл элемента'
  if b.get('media') and ((b['type']=='video' and not b['media'].endswith(('.mp4','.webm'))) or (b['type'] in ('image','image_left','image_right') and b['media'].endswith(('.mp4','.webm')))):return 'Неверный тип файла элемента'
  for key in ('heading','text','alt'):
   if not isinstance(b.get(key),dict) or any(not isinstance(b[key].get(l,''),str) or len(b[key].get(l,''))>12000 for l in ('ru','en')):return 'Некорректное поле элемента'
  if p.get('published'):
   if b['type'] in ('image','image_left','image_right') and b.get('media') and not all(b['alt'].get(l,'').strip() for l in ('ru','en')):return 'Для опубликованного изображения добавьте описание на двух языках'
   for k in ('heading','text','alt'):
    vals=[bool(b[k].get(l,'').strip()) for l in ('ru','en')]
    if vals[0]!=vals[1]:return 'Заполните каждое текстовое поле элемента на двух языках'
 return None

@app.after_request
def headers(resp):
 if request.path.startswith(('/admin','/enter','/api/admin','/api/spotify')): resp.headers['Cache-Control']='no-store'
 if request.path.startswith(('/admin','/enter','/api/')): resp.headers['X-Robots-Tag']='noindex, nofollow'
 resp.headers['X-Content-Type-Options']='nosniff';resp.headers['Referrer-Policy']='strict-origin-when-cross-origin';resp.headers['X-Frame-Options']='SAMEORIGIN'
 resp.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data: https://*.google-analytics.com https://*.googletagmanager.com https://mc.yandex.ru https://yandex.ru; style-src 'self' 'unsafe-inline'; script-src 'self' https://www.googletagmanager.com https://mc.yandex.ru; connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com https://mc.yandex.ru https://*.mc.yandex.ru; frame-src https://open.spotify.com https://mc.yandex.ru; media-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
 return resp

SITE_URL=os.environ.get('SITE_URL','https://acoulbot.space').rstrip('/')
if not re.fullmatch(r'https?://[A-Za-z0-9.:-]+', SITE_URL): raise RuntimeError('Invalid SITE_URL')
def lang_ok(lang):
 if lang not in ('ru','en'): abort(404)
 return lang
def analytics_id(key, pattern):
 v=os.environ.get(key,'').strip()
 return v if re.fullmatch(pattern,v) else ''
def render_public(template,lang='ru',section='',title=None,description=None,og_image=None,**kw):
 lang=lang_ok(lang)
 content=site_content()
 def copy(key):return site_copy(content,key,lang)
 titles={'ru':'acoulbot — Andy Coulbot | Творчество и технологии','en':'acoulbot — Andy Coulbot | Creative practice & technology'}
 desc={'ru':'Andy Coulbot — фотограф, дизайнер, автор и архитектор-оператор нейросетей. Проекты, истории и эксперименты acoulbot.','en':'Andy Coulbot is a photographer, designer, writer and AI architect-operator. Explore projects, stories and experiments by acoulbot.'}
 canonical=SITE_URL+'/'+lang+'/'+section
 seo_key={'':'home','news':'news','about':'about','privacy':'privacy'}.get(section)
 if seo_key: title=copy('seo_'+seo_key+'_title');description=copy('seo_'+seo_key+'_desc')
 visual=content.get('visual',{});about_photos=content.get('about_photos',{});contacts={'telegram':'https://t.me/aclbt','email':'acoulbot@gmail.com','connect':'http://trioz.ru/connect'};contacts.update(content.get('contacts',{}));same_as=[contacts[k] for k in ('telegram','connect') if contacts.get(k)]
 return render_template(template,lang=lang,site_url=SITE_URL,section=section,canonical=canonical,seo_title=title or titles[lang],seo_desc=description or desc[lang],og_image=SITE_URL+(og_image or '/static/og-default.png'),ga_id=analytics_id('GA_MEASUREMENT_ID',r'G-[A-Z0-9]{4,20}'),ym_id=analytics_id('YANDEX_METRIKA_ID',r'[0-9]{1,20}'),google_verification=os.environ.get('GOOGLE_SITE_VERIFICATION',''),yandex_verification=os.environ.get('YANDEX_SITE_VERIFICATION',''),featured_sections={p.get('feature') for p in projects(True) if p.get('feature')},copy=copy,visual=visual,about_photos=about_photos,contacts=contacts,same_as=same_as,**kw)
@app.get('/')
def home_root():return home('ru')
@app.get('/<lang>/')
def home(lang):
 lang_ok(lang);ps=projects(True);featured={p['feature']:p for p in ps if p.get('feature')}
 work=[p for p in ps if p.get('kind','project')=='project']
 news=sorted((p for p in ps if p.get('kind')=='news'),key=lambda p:p.get('published_at',0),reverse=True)
 return render_public('index.html',lang,projects=work,news=news,featured=featured,playlist=setting('playlist'))
@app.get('/project/<slug>')
def legacy_detail(slug):return redirect('/ru/project/'+slug,code=301)
@app.get('/<lang>/project/<slug>')
def detail(lang,slug):
 lang_ok(lang);p=next((x for x in projects(True) if x['slug']==slug),None)
 if not p:abort(404)
 related=next((x for x in projects(True) if x['id']==p.get('related_id') and x.get('kind')=='project'),None)
 return render_public('project.html',lang,section='project/'+p['slug'],title=p['title'][lang]+' — Andy Coulbot | acoulbot',description=p['summary'][lang],og_image=p.get('cover') or None,p=p,related=related,preview=False)
@app.get('/<lang>/preview/<int:pid>')
def preview(lang,pid):
 lang_ok(lang)
 if not logged():return redirect('/enter')
 p=next((x for x in projects() if x['id']==pid),None)
 if not p:abort(404)
 r=app.make_response(render_public('project.html',lang,section='preview/'+str(pid),title=(p['title'].get(lang) or 'Preview')+' — acoulbot',description=p['summary'].get(lang) or '',p=p,related=None,preview=True))
 r.headers['X-Robots-Tag']='noindex, nofollow';r.headers['Cache-Control']='no-store';return r
@app.get('/<lang>/news')
def news_page(lang):
 lang_ok(lang);news=sorted((p for p in projects(True) if p.get('kind')=='news'),key=lambda p:p.get('published_at',0),reverse=True)
 title='Новости — Andy Coulbot | acoulbot' if lang=='ru' else 'News — Andy Coulbot | acoulbot'
 return render_public('news.html',lang,section='news',title=title,description=('Новости, заметки и обновления проектов Andy Coulbot.' if lang=='ru' else 'News, notes and project updates from Andy Coulbot.'),news=news)
@app.get('/<lang>/about')
def about(lang):
 title='Обо мне — Andy Coulbot | acoulbot' if lang=='ru' else 'About — Andy Coulbot | acoulbot'
 return render_public('about.html',lang,section='about',title=title,description=('История и деятельность Энди Кулбота: фотография, дизайн, технологии, книга и Connect.' if lang=='ru' else 'About Andy Coulbot: photography, design, technology, the novel and Connect.'))
@app.get('/<lang>/privacy')
def privacy(lang):
 title='Конфиденциальность — acoulbot' if lang=='ru' else 'Privacy — acoulbot'
 return render_public('privacy.html',lang,section='privacy',title=title,description=('Как acoulbot использует cookie, аналитику и Spotify.' if lang=='ru' else 'How acoulbot uses cookies, analytics and Spotify.'))
@app.get('/robots.txt')
def robots():return Response('User-agent: *\nAllow: /\nDisallow: /enter\nDisallow: /admin\nDisallow: /api/\nDisallow: /ru/preview/\nDisallow: /en/preview/\nSitemap: '+SITE_URL+'/sitemap.xml\n',mimetype='text/plain')
@app.get('/sitemap.xml')
def sitemap():
 ns='http://www.sitemaps.org/schemas/sitemap/0.9';xh='http://www.w3.org/1999/xhtml';ET.register_namespace('',ns);ET.register_namespace('xhtml',xh)
 root=ET.Element('{%s}urlset'%ns);paths=['','news','about','privacy']+['project/'+p['slug'] for p in projects(True)]
 for path in paths:
  for lang in ('ru','en'):
   url=ET.SubElement(root,'{%s}url'%ns);ET.SubElement(url,'{%s}loc'%ns).text=SITE_URL+'/'+lang+'/'+path
   for alt in ('ru','en'):ET.SubElement(url,'{%s}link'%xh,{'rel':'alternate','hreflang':alt,'href':SITE_URL+'/'+alt+'/'+path})
 return Response(ET.tostring(root,encoding='utf-8',xml_declaration=True),mimetype='application/xml')
@app.get('/<lang>/feed.xml')
def feed(lang):
 lang_ok(lang);rss=ET.Element('rss',{'version':'2.0'});ch=ET.SubElement(rss,'channel')
 for key,value in [('title','acoulbot — '+('Новости' if lang=='ru' else 'News')),('link',SITE_URL+'/'+lang+'/#news'),('description','Andy Coulbot / acoulbot')]:ET.SubElement(ch,key).text=value
 for p in sorted((p for p in projects(True) if p.get('kind')=='news'),key=lambda p:p.get('published_at',0),reverse=True):
  item=ET.SubElement(ch,'item');url=SITE_URL+'/'+lang+'/project/'+p['slug']
  for key,value in [('title',p['title'][lang]),('link',url),('guid',url),('description',p['summary'][lang]),('pubDate',formatdate(p.get('published_at') or p['updated'],usegmt=True))]:ET.SubElement(item,key).text=value
 return Response(ET.tostring(rss,encoding='utf-8',xml_declaration=True),mimetype='application/rss+xml')
@app.errorhandler(404)
def not_found(e):
 lang='en' if request.path.startswith('/en/') else 'ru'
 response=app.make_response(render_public('404.html',lang,section='404',title='404 — acoulbot'))
 response.status_code=404;response.headers['X-Robots-Tag']='noindex';return response
@app.get('/media/<name>')
def media(name):
 if not re.fullmatch(r'[a-f0-9]{32}\.(png|jpg|gif|webp|mp4|webm)',name):abort(404)
 return send_from_directory(UPLOADS,name,conditional=True)

attempts={};lock=threading.Lock()
@app.route('/enter',methods=['GET','POST'])
def enter():
 if request.method=='GET':
  if logged():return redirect('/admin')
  session['login_csrf']=secrets.token_urlsafe(32);return render_template('login.html',csrf=session['login_csrf'],configured=bool(setting('password_hash')))
 token=request.form.get('csrf','')
 if not token or not secrets.compare_digest(token,session.get('login_csrf','')):abort(403)
 ip=request.remote_addr or 'unknown';now=time.time()
 with lock:
  arr=[v for v in attempts.get(ip,[]) if now-v<900]; attempts[ip]=arr
  if len(arr)>=8:return render_template('login.html',csrf=token,error='Слишком много попыток. Попробуйте через 15 минут.',configured=True),429
 ph=setting('password_hash')
 if ph and check_password_hash(ph,request.form.get('password','')):
  with lock:attempts.pop(ip,None)
  session.clear();session.permanent=True;session['admin']=True;session['csrf']=secrets.token_urlsafe(32)
  return redirect('/admin')
 with lock:attempts[ip].append(now)
 return render_template('login.html',csrf=token,error='Неверный пароль или администратор ещё не настроен.',configured=bool(ph)),401
@app.get('/admin')
def admin():
 if not logged():return redirect('/enter')
 return render_template('admin.html',csrf=session['csrf'],spotify_configured=bool(os.environ.get('SPOTIFY_CLIENT_ID') and os.environ.get('SPOTIFY_CLIENT_SECRET') and os.environ.get('SPOTIFY_REDIRECT_URI')),spotify_connected=bool(setting('spotify_refresh')))
@app.post('/api/admin/logout')
@admin_required
@csrf_required
def logout():session.clear();return jsonify(ok=True)
@app.get('/api/admin/projects')
@admin_required
def list_projects():return jsonify(projects())
@app.post('/api/admin/projects')
@admin_required
@csrf_required
def save_project():
 p=request.get_json(silent=True)
 err=validate(p)
 if err:return jsonify(error=err),400
 p={k:p.get(k) for k in ('slug','title','category','summary','url','feature','cover','feature_image','cover_fit','background','background_image','blur','published','blocks','kind','related_id')}
 p['kind']=p.get('kind') or 'project'
 p['feature_image']=p.get('feature_image') or ''
 p['cover_fit']=p.get('cover_fit') or 'contain'
 try:
  with conn() as db:
   if p.get('related_id'):
    target=db.execute('SELECT data FROM projects WHERE id=?',(p['related_id'],)).fetchone()
    if not target or p['related_id']==request.json.get('id'):return jsonify(error='Связанный проект не найден'),400
    target_data=json.loads(target['data'])
    if target_data.get('kind','news' if target_data.get('slug')=='journal' and target_data.get('category',{}).get('ru')=='ШАБЛОН НОВОСТИ' else 'project')!='project':return jsonify(error='Связь допускается только с проектом'),400
   if p['feature']:
    for row in db.execute('SELECT id,data FROM projects').fetchall():
     old=json.loads(row['data'])
     if old.get('feature')==p['feature'] and row['id']!=request.json.get('id'):return jsonify(error='Этот раздел уже назначен другому проекту'),400
   pid=request.json.get('id')
   if pid:
    row=db.execute('SELECT data,updated FROM projects WHERE id=?',(pid,)).fetchone()
    if row:
     previous=json.loads(row['data']); p['published_at']=previous.get('published_at') or (row['updated'] if previous.get('published') else (int(time.time()) if p['published'] else None))
   elif p['published']: p['published_at']=int(time.time())
   if pid:
    if db.execute('UPDATE projects SET slug=?,data=?,updated=? WHERE id=?',(p['slug'],json.dumps(p,ensure_ascii=False),int(time.time()),pid)).rowcount==0:return jsonify(error='Не найдено'),404
   else:pid=db.execute('INSERT INTO projects(slug,data,updated) VALUES(?,?,?)',(p['slug'],json.dumps(p,ensure_ascii=False),int(time.time()))).lastrowid
  return jsonify(ok=True,id=pid)
 except sqlite3.IntegrityError:return jsonify(error='Этот адрес уже используется'),400
@app.delete('/api/admin/projects/<int:pid>')
@admin_required
@csrf_required
def delete_project(pid):
 with conn() as db: db.execute('DELETE FROM projects WHERE id=?',(pid,))
 return jsonify(ok=True)
@app.post('/api/admin/upload')
@admin_required
@csrf_required
def upload():
 f=request.files.get('file')
 if not f:return jsonify(error='Выберите файл'),400
 data=f.stream.read(32);typ=None
 if data.startswith(b'\x89PNG\r\n\x1a\n'):typ='png'
 elif data.startswith(b'\xff\xd8\xff'):typ='jpg'
 elif data.startswith((b'GIF87a',b'GIF89a')):typ='gif'
 elif data[:4]==b'RIFF' and data[8:12]==b'WEBP':typ='webp'
 elif len(data)>12 and data[4:8]==b'ftyp':typ='mp4'
 elif data.startswith(b'\x1a\x45\xdf\xa3'):typ='webm'
 if not typ:return jsonify(error='Поддерживаются PNG, JPG, GIF, WebP, MP4 и WebM'),400
 name=secrets.token_hex(16)+'.'+typ
 try:
  with (UPLOADS/name).open('xb') as out:
   out.write(data);shutil.copyfileobj(f.stream,out,1024*1024)
 except Exception:
  (UPLOADS/name).unlink(missing_ok=True);raise
 return jsonify(url='/media/'+name)
@app.errorhandler(RequestEntityTooLarge)
def too_large(e):return jsonify(error='Файл слишком большой: максимум 150 МБ на запрос'),413
@app.get('/api/admin/site')
@admin_required
def get_site_content():
 data=site_content();custom=data.get('copy',{})
 fields=[dict(f,ru=custom.get(f['key'],{}).get('ru',f['ru']),en=custom.get(f['key'],{}).get('en',f['en'])) for f in FIELDS]
 return jsonify(fields=fields,visual=data.get('visual',{'enabled':True,'captions':False,'photos':[]}),about_photos=data.get('about_photos',{'enabled':True,'captions':False,'photos':[]}),contacts=data.get('contacts',{'telegram':'https://t.me/aclbt','email':'acoulbot@gmail.com','connect':'http://trioz.ru/connect'}))

@app.post('/api/admin/site/<part>')
@admin_required
@csrf_required
def set_site_content(part):
 value=request.get_json(silent=True)
 if part=='copy':
  if not isinstance(value,dict) or not value or len(value)>len(FIELDS):return jsonify(error='Некорректные данные'),400
  for k,v in value.items():
   if k not in BY_KEY or not isinstance(v,dict):return jsonify(error='Неизвестное поле'),400
   for lang in ('ru','en'):
    text=v.get(lang)
    if not isinstance(text,str) or len(text)>6000 or (not text.strip() and not BY_KEY[k].get('optional')):return jsonify(error='Заполните каждое поле на двух языках'),400
   if BY_KEY[k].get('optional') and bool(v['ru'].strip())!=bool(v['en'].strip()):return jsonify(error='Заметку нужно заполнить на двух языках или оставить пустой'),400
  save_site_part(part,value);return jsonify(ok=True)
 if part=='contacts':
  if not isinstance(value,dict) or set(value.keys())!={'telegram','email','connect'}:return jsonify(error='Некорректные контакты'),400
  if any(not isinstance(v,str) or len(v)>500 for v in value.values()):return jsonify(error='Некорректные контакты'),400
  if any(value[k] and not valid_url(value[k]) for k in ('telegram','connect')):return jsonify(error='Ссылки должны начинаться с http:// или https://'),400
  if value['email'] and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',value['email']):return jsonify(error='Укажите корректную почту'),400
  save_site_part(part,value);return jsonify(ok=True)
 if part not in ('visual','about_photos') or not isinstance(value,dict):return jsonify(error='Неизвестный раздел'),400
 if type(value.get('enabled')) is not bool or type(value.get('captions')) is not bool or not isinstance(value.get('photos'),list) or len(value['photos'])>60:return jsonify(error='Некорректные настройки'),400
 normalized=[]
 for im in value['photos']:
  if not isinstance(im,dict) or not isinstance(im.get('src'),str) or not re.fullmatch(r'/media/[a-f0-9]{32}\.(png|jpg|gif|webp)',im['src']) or not (UPLOADS/im['src'].split('/')[-1]).is_file():return jsonify(error='Загрузите изображение на сервер'),400
  for k in ('alt','caption'):
   if not isinstance(im.get(k),dict) or any(not isinstance(im[k].get(l),str) or len(im[k][l])>1000 for l in ('ru','en')):return jsonify(error='Некорректное описание фотографии'),400
   if k=='alt' and any(not im[k][l].strip() for l in ('ru','en')):return jsonify(error='Для каждой фотографии укажите alt на двух языках'),400
   if k=='caption' and bool(im[k]['ru'].strip())!=bool(im[k]['en'].strip()):return jsonify(error='Подпись заполните на двух языках или оставьте пустой'),400
  for k in ('focus_x','focus_y'):
   if type(im.get(k)) is not int or not 0<=im[k]<=100:return jsonify(error='Некорректная точка кадрирования'),400
  normalized.append({k:im[k] for k in ('src','alt','caption','focus_x','focus_y')})
 save_site_part(part,{'enabled':value['enabled'],'captions':value['captions'],'photos':normalized});return jsonify(ok=True)

@app.route('/api/admin/settings',methods=['GET','POST'])
@admin_required
def settings():
 if request.method=='GET':return jsonify(playlist=setting('playlist'),spotify_connected=bool(setting('spotify_refresh')))
 if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','')):abort(403)
 data=request.get_json(silent=True) or {};url=data.get('playlist','').strip()
 if url and not re.fullmatch(r'https://open\.spotify\.com/playlist/[A-Za-z0-9]+(?:\?[^\s]*)?',url):return jsonify(error='Укажите ссылку на плейлист Spotify'),400
 put_setting('playlist',url);return jsonify(ok=True)

# Spotify: owner authenticates once. Tokens remain on the server, never in templates.
def spotify_config():return [os.environ.get(k,'') for k in ('SPOTIFY_CLIENT_ID','SPOTIFY_CLIENT_SECRET','SPOTIFY_REDIRECT_URI')]
def token_request(params):
 cid,secret,_=spotify_config();auth=base64.b64encode((cid+':'+secret).encode()).decode()
 req=urllib.request.Request('https://accounts.spotify.com/api/token',data=urllib.parse.urlencode(params).encode(),headers={'Authorization':'Basic '+auth,'Content-Type':'application/x-www-form-urlencoded'})
 with urllib.request.urlopen(req,timeout=8) as res:return json.load(res)
@app.post('/api/admin/spotify/start')
@admin_required
@csrf_required
def spotify_start():
 cid,sec,uri=spotify_config()
 if not all((cid,sec,uri)):return jsonify(error='Настройте Spotify в .env и перезапустите сервер'),400
 state=secrets.token_urlsafe(32);session['spotify_state']=state
 q=urllib.parse.urlencode({'client_id':cid,'response_type':'code','redirect_uri':uri,'scope':'user-read-currently-playing','state':state})
 return jsonify(url='https://accounts.spotify.com/authorize?'+q)
@app.get('/api/spotify/callback')
def spotify_callback():
 state=session.pop('spotify_state','')
 if not logged() or not state or not secrets.compare_digest(state,request.args.get('state','')):abort(403)
 if not request.args.get('code'):return redirect('/admin?spotify=error')
 try:
  result=token_request({'grant_type':'authorization_code','code':request.args['code'],'redirect_uri':spotify_config()[2]})
  put_setting('spotify_refresh',result['refresh_token']);return redirect('/admin?spotify=ok')
 except Exception:return redirect('/admin?spotify=error')
@app.post('/api/admin/spotify/disconnect')
@admin_required
@csrf_required
def spotify_disconnect():put_setting('spotify_refresh',''); spotify_cache.update(at=0,data=None);return jsonify(ok=True)
spotify_cache={'at':0,'data':None};spotify_lock=threading.Lock()
@app.get('/api/spotify/now')
def spotify_now():
 with spotify_lock:
  if time.time()-spotify_cache['at']<30:return jsonify(spotify_cache['data'])
  result=None;refresh=setting('spotify_refresh')
  if refresh and all(spotify_config()):
   try:
    tok=token_request({'grant_type':'refresh_token','refresh_token':refresh})
    if tok.get('refresh_token'):put_setting('spotify_refresh',tok['refresh_token'])
    req=urllib.request.Request('https://api.spotify.com/v1/me/player/currently-playing',headers={'Authorization':'Bearer '+tok['access_token']})
    with urllib.request.urlopen(req,timeout=6) as response:
     if response.status==200:
      obj=json.load(response);item=obj.get('item') or {}
      if obj.get('is_playing') and item.get('name') and item.get('type')=='track':
       link=(item.get('external_urls') or {}).get('spotify','')
       if not link.startswith('https://open.spotify.com/'):link='https://open.spotify.com/'
       result={'name':item['name'],'artists':', '.join(a.get('name','') for a in item.get('artists',[])),'url':link}
   except Exception:pass
  spotify_cache.update(at=time.time(),data=result);return jsonify(result)

init_db()
try:
 os.chmod(DATA,0o700); os.chmod(DB,0o600)
except OSError: pass
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='set-password':
  import getpass
  p=getpass.getpass('Новый пароль администратора (не менее 12 символов): ');q=getpass.getpass('Повторите пароль: ')
  if p!=q or len(p)<12:sys.exit('Пароли не совпадают или пароль слишком короткий.')
  put_setting('password_hash',generate_password_hash(p,method='scrypt'));print('Пароль сохранён. Вход: /enter');sys.exit(0)
 app.run(host=os.environ.get('HOST','127.0.0.1'),port=int(os.environ.get('PORT','3011')),debug=False)
