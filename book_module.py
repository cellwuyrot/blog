"""Confrontation: private authoring and public, spoiler-filtered reading.
All persistent state lives in the existing settings table (SQLite or PostgreSQL).
"""
import base64, copy, hashlib, html, json, re, secrets
from pathlib import Path
from flask import request, jsonify, abort, Response, redirect, send_file
from markupsafe import Markup

ID = re.compile(r'^[a-f0-9]{16}$')
IMAGE = re.compile(r'^[a-f0-9]{32}\.(?:jpg|png|webp|gif)$')
MAX_BOOK = 16 * 1024 * 1024

def empty_book():
 return {'revision':0,'title':{'ru':'Конфронтация','en':'Confrontation'},'summary':{'ru':'','en':''},'cover':'','chapters':[],'characters':[],'places':[]}

def empty_scene():
 return {'cast':[],'relations':[]}

def normalise_book(b):
 # Old books remain intact; new fields are added in memory, then saved normally.
 for c in b.get('chapters',[]):
  for p in c.get('parts',[]):
   p.setdefault('scene',empty_scene())
   p.setdefault('scene_live',{'ru':None,'en':None})
 return b

def get_book(s):
 try:
  b=json.loads(s['setting']('confrontation_v1','{}'))
  if isinstance(b,dict) and isinstance(b.get('revision'),int):return normalise_book(b)
 except (ValueError,TypeError):pass
 return empty_book()

def get_seo(s):
 try:
  o=json.loads(s['setting']('seo_overrides_v1','{}'))
  return o if isinstance(o,dict) else {}
 except (ValueError,TypeError):return {}

def validate_book(b):
 if not isinstance(b,dict) or type(b.get('revision')) is not int: return 'Некорректная версия документа'
 if len(json.dumps(b,ensure_ascii=False).encode()) > MAX_BOOK: return 'Превышен размер книги: 16 МБ; разделите материалы или экспортируйте досье'
 def loc(v,limit=5000):return isinstance(v,dict) and all(isinstance(v.get(l),str) and len(v[l])<=limit for l in ('ru','en'))
 def photo(v):return isinstance(v,str) and (not v or bool(IMAGE.fullmatch(v)))
 if not loc(b.get('title'),300) or not b['title']['ru'].strip() or not loc(b.get('summary'),5000) or not photo(b.get('cover','')):return 'Проверьте название, аннотацию и обложку'
 if any(not isinstance(b.get(k),list) for k in ('chapters','characters','places')):return 'Неверная структура книги'
 if any(not isinstance(c,dict) or not isinstance(c.get('parts'),list) for c in b['chapters']):return 'Некорректные главы'
 if len(b['chapters'])>500 or sum(len(c['parts']) for c in b['chapters'])>3000 or sum(len(b[k]) for k in ('characters','places'))>3000:return 'Превышено ограничение количества записей'
 ids=set(); part_ids=set(); chapter_numbers=set()
 def identifier(v):
  if not isinstance(v,str) or not ID.fullmatch(v) or v in ids:return False
  ids.add(v);return True
 for ch in b['chapters']:
  if not isinstance(ch,dict) or not identifier(ch.get('id')) or type(ch.get('number')) is not int or not 1<=ch['number']<=9999 or not loc(ch.get('title'),300) or not photo(ch.get('cover','')) or not isinstance(ch.get('parts'),list):return 'Некорректная глава'
  if ch['number'] in chapter_numbers:return 'Номера глав не должны повторяться'
  chapter_numbers.add(ch['number'])
  nums=set()
  for part in ch['parts']:
   if not isinstance(part,dict) or not identifier(part.get('id')) or type(part.get('number')) is not int or not 1<=part['number']<=9999 or part['number'] in nums:return 'Некорректная часть или повтор номера'
   nums.add(part['number']);part_ids.add(part['id'])
   for group in ('draft','live'):
    if not isinstance(part.get(group),dict):return 'Некорректные версии части'
    for lang in ('ru','en'):
     v=part[group].get(lang)
     if group=='live' and v is None:continue
     if not isinstance(v,dict) or any(not isinstance(v.get(k),str) or len(v[k])>2_000_000 for k in ('title','body','description')) or type(v.get('index')) is not bool:return 'Проверьте текст и настройки части'
     if group=='live' and not v['body'].strip():return 'Нельзя опубликовать пустую часть'
 for kind in ('characters','places'):
  for ent in b[kind]:
   if not isinstance(ent,dict) or not identifier(ent.get('id')) or not loc(ent.get('name'),300) or not photo(ent.get('portrait','')) or type(ent.get('portrait_public')) is not bool or type(ent.get('published')) is not bool or not isinstance(ent.get('after',''),str) or (ent.get('after','') and ent['after'] not in part_ids) or not isinstance(ent.get('private'),dict) or not isinstance(ent.get('facts'),list) or not isinstance(ent.get('relations'),list):return 'Некорректное досье'
   if len(ent['facts'])>1000 or len(ent['relations'])>1000:return 'Слишком много сведений'
   if ent['published'] and not ent['name']['ru'].strip():return 'Укажите русское имя перед публикацией'
   for fact in ent['facts']+ent['relations']:
    if not isinstance(fact,dict) or not identifier(fact.get('id')) or not loc(fact.get('label'),300) or not loc(fact.get('text'),10000) or type(fact.get('public')) is not bool or not isinstance(fact.get('after'),str) or (fact['after'] and fact['after'] not in part_ids):return 'Проверьте информацию и привязку к части'
    if 'target' in fact and (not isinstance(fact['target'],str) or (fact['target'] and not ID.fullmatch(fact['target']))):return 'Некорректная связь'
 # Scene context is a separate author-approved snapshot for each published language.
 character_ids={e['id'] for e in b['characters']}
 for ch in b['chapters']:
  for part in ch['parts']:
   scene=part.get('scene',empty_scene()); live=part.get('scene_live',{'ru':None,'en':None})
   if not isinstance(live,dict):return 'Некорректные версии персонажей части'
   def check_scene(v):
    if not isinstance(v,dict) or not isinstance(v.get('cast'),list) or not isinstance(v.get('relations'),list) or len(v['cast'])>100 or len(v['relations'])>300:return False
    selected=set()
    for c in v['cast']:
     if not isinstance(c,dict) or not isinstance(c.get('entity'),str) or c.get('entity') not in character_ids or c['entity'] in selected or not loc(c.get('note'),5000):return False
     selected.add(c['entity'])
    for r in v['relations']:
     if not isinstance(r,dict) or not isinstance(r.get('id'),str) or not ID.fullmatch(r['id']) or not isinstance(r.get('source'),str) or not isinstance(r.get('target'),str) or r.get('source') not in selected or r.get('target') not in selected or r['source']==r['target'] or not loc(r.get('label'),300) or not loc(r.get('text'),5000):return False
    return True
   if not check_scene(scene) or any(live.get(l) is not None and not check_scene(live[l]) for l in ('ru','en')):return 'Проверьте персонажей и связи части'
 return None

def save_state(s,key,value,revision):
 with s['conn']() as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
  try: old=json.loads(row[0]) if row else {}
  except (ValueError,TypeError):old={}
  current=old.get('revision',0) if isinstance(old,dict) else 0
  if revision!=current:return None
  value['revision']=current+1
  db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value,ensure_ascii=False)))
  return value['revision']

def parts(b,lang=None):
 return [(c,p) for c in sorted(b['chapters'],key=lambda x:x['number']) for p in sorted(c['parts'],key=lambda x:x['number']) if lang is None or p['live'].get(lang)]

def text_html(text):
 # Very small allowlisted formatter. Never interpret HTML supplied by the author.
 def inline(line):
  escaped=html.escape(line,quote=True)
  escaped=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',escaped)
  escaped=re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)',r'<em>\1</em>',escaped)
  return escaped
 return Markup('\n'.join('<p>'+ '<br>'.join(inline(l) for l in p.split('\n')) +'</p>' for p in re.split(r'\n\s*\n',text.strip()) if p.strip()))

def visible_world(b,lang,through):
 published=parts(b,lang);pos=next((i for i,(_,p) in enumerate(published) if p['id']==through),-1) if through else -1
 visible_ids={p['id'] for _,p in published[:pos+1]}
 eligible=[(kind,ent) for kind in ('characters','places') for ent in b[kind] if ent['published'] and ent['name'][lang] and (not ent.get('after') or ent['after'] in visible_ids)]
 names={ent['id']:ent['name'][lang] for kind,ent in eligible}; order={p['id']:i for i,(_,p) in enumerate(published)}
 cards=[]
 for kind,ent in eligible:
  facts=[{'label':f['label'][lang],'text':f['text'][lang]} for f in ent['facts'] if f['public'] and (not f['after'] or f['after'] in visible_ids) and f['text'][lang]]
  # For a linked person/place, display the latest approved state up to the checkpoint.
  latest={}
  for f in ent['relations']:
   if not f['public'] or (f['after'] and f['after'] not in visible_ids):continue
   target=f.get('target','')
   if target and target not in names:continue
   label=f['label'][lang]; text=f['text'][lang]
   if not (label or text or target):continue
   group=target or f['id'];rank=order.get(f['after'],-1)
   if group not in latest or rank>=latest[group][0]:
    latest[group]=(rank,{'label':(names[target]+(' · '+label if label else '')) if target else label,'text':text})
  cards.append({'id':ent['id'],'kind':kind,'name':ent['name'][lang],'portrait':ent['portrait'] if ent['portrait_public'] else '', 'facts':facts,'relations':[v[1] for v in latest.values()]})
 return cards

def scene_for_reader(b,lang,part,previous):
 # Only the approved snapshot of this exact part, and only previously revealed
 # characters, can reach the reader. Draft and private dossiers never leave here.
 scene=part.get('scene_live',{}).get(lang)
 if not scene:return {'cast':[],'relations':[],'through':previous}
 allowed={c['id']:c for c in visible_world(b,lang,previous) if c['kind']=='characters'}
 cast=[{'id':item['entity'],'name':allowed[item['entity']]['name'],
        'note':item['note'][lang],'portrait':allowed[item['entity']]['portrait']}
       for item in scene['cast'] if item['entity'] in allowed]
 names={c['id']:c['name'] for c in cast}
 relations=[{'source':names[r['source']],'target':names[r['target']],
             'label':r['label'][lang],'text':r['text'][lang]}
            for r in scene['relations'] if r['source'] in names and r['target'] in names and (r['label'][lang] or r['text'][lang])]
 return {'cast':cast,'relations':relations,'through':previous}

def register(app,s):
 DATA=Path(s['DATA']); book_media=DATA/'book-media';book_media.mkdir(mode=0o700,exist_ok=True)
 def require_lang(lang):return s['lang_ok'](lang)
 def csrf():return s['csrf_required']
 @app.get('/api/admin/book')
 @s['admin_required']
 def admin_book_read():return jsonify(get_book(s))
 @app.post('/api/admin/book')
 @s['admin_required']
 @s['csrf_required']
 def admin_book_write():
  b=request.get_json(silent=True); err=validate_book(b)
  if err:return jsonify(error=err),400
  rev=save_state(s,'confrontation_v1',b,b['revision'])
  if rev is None:return jsonify(error='Данные изменились в другой вкладке. Скопируйте несохранённый текст и обновите страницу.'),409
  return jsonify(ok=True,revision=rev)
 @app.post('/api/admin/book/image')
 @s['admin_required']
 @s['csrf_required']
 def book_image_upload():
  f=request.files.get('file')
  if not f:return jsonify(error='Выберите изображение'),400
  data=f.stream.read(10*1024*1024+1)
  if len(data)>10*1024*1024:return jsonify(error='Максимум 10 МБ'),400
  if data.startswith(b'\xff\xd8\xff'):ext='jpg'
  elif data.startswith(b'\x89PNG\r\n\x1a\n'):ext='png'
  elif data.startswith((b'GIF87a',b'GIF89a')):ext='gif'
  elif data[:4]==b'RIFF' and data[8:12]==b'WEBP':ext='webp'
  else:return jsonify(error='Поддерживаются JPG, PNG, GIF и WebP'),400
  name=secrets.token_hex(16)+'.'+ext
  with (book_media/name).open('xb') as out:out.write(data)
  return jsonify(name=name)
 @app.get('/book-media/<name>')
 def show_book_image(name):
  if not IMAGE.fullmatch(name):abort(404)
  b=get_book(s); allowed=name==b['cover'] or any(name==c.get('cover') and any(p['live'].get(l) for p in c['parts'] for l in ('ru','en')) for c in b['chapters'])
  # Portrait is served publicly only if explicitly approved; author-only assets require login.
  timeline=[p['id'] for c,p in parts(b) if any(p['live'].get(l) for l in ('ru','en'))]
  through=request.args.get('through','');pos=timeline.index(through) if through in timeline else -1
  seen=set(timeline[:pos+1]);gated=False
  for k in ('characters','places'):
   for e in b[k]:
    if e['published'] and e['portrait_public'] and e['portrait']==name and (not e.get('after') or e['after'] in seen):
     allowed=True;gated=bool(e.get('after'))
  if not allowed and not s['logged']():abort(404)
  path=book_media/name
  if not path.is_file():abort(404)
  r=send_file(path,conditional=True);r.headers['Cache-Control']='private, no-store' if (not allowed or gated) else 'public, max-age=3600'
  if gated:r.headers['X-Robots-Tag']='noindex'
  return r
 @app.post('/api/admin/book/preview')
 @s['admin_required']
 @s['csrf_required']
 def book_preview():
  v=request.get_json(silent=True) or {}
  title=v.get('title',''); body=v.get('body',''); lang=v.get('lang','ru')
  if lang not in ('ru','en') or not isinstance(title,str) or not isinstance(body,str) or len(body)>2_000_000 or len(title)>1000:return jsonify(error='Некорректный текст'),400
  r=app.make_response(s['render_template']('book_preview.html',lang=lang,title=title,body=text_html(body)))
  r.headers['X-Robots-Tag']='noindex, nofollow';r.headers['Cache-Control']='private, no-store';return r
 @app.get('/api/admin/book/export')
 @s['admin_required']
 def book_export():
  # Entire structure, including private work, is only available to the signed-in author.
  r=jsonify(get_book(s));r.headers['Content-Disposition']='attachment; filename="confrontation-backup.json"';return r
 @app.get('/api/admin/seo')
 @s['admin_required']
 def seo_read():
  b=get_book(s); live=parts(b,'ru'); missing=sum(1 for c,p in live if not p['live']['ru']['description'].strip()); pending=sum(1 for c,p in live if not p['live']['en'])
  return jsonify(overrides=get_seo(s), pages=seo_pages(s,b), checks={'site_url':s['SITE_URL'],'sitemap':s['SITE_URL']+'/sitemap.xml','ru_parts_without_description':missing,'pending_translations':pending})
 @app.post('/api/admin/seo')
 @s['admin_required']
 @s['csrf_required']
 def seo_write():
  data=request.get_json(silent=True)
  if not isinstance(data,dict) or len(data)>10000:return jsonify(error='Некорректные настройки'),400
  allowed={p['key'] for p in seo_pages(s,get_book(s))} | set(get_seo(s))
  for k,v in data.items():
   if k not in allowed or not isinstance(v,dict) or set(v)!={'title','description','index'} or any(not isinstance(v[x],str) or len(v[x])>2000 for x in ('title','description')) or type(v['index']) is not bool:return jsonify(error='Некорректные настройки страницы'),400
  s['put_setting']('seo_overrides_v1',json.dumps(data,ensure_ascii=False));return jsonify(ok=True)
 @app.get('/<lang>/book')
 def book_home(lang):
  require_lang(lang);b=get_book(s); available=[c for c in b['chapters'] if any(p['live'].get(lang) for p in c['parts'])]
  allparts=parts(b,lang)
  return s['render_public']('book_home.html',lang,section='book',title=b['title'][lang]+' — Andy Coulbot',description=b['summary'][lang] or (('Книга «'+b['title'][lang]+'» Энди Кулбота: опубликованные части и мир книги.') if lang=='ru' else (b['title'][lang]+' by Andy Coulbot: published parts and the world of the book.')),book=b,chapters=available,first=allparts[0] if allparts else None,book_view=True,available_langs=['ru','en'])
 @app.get('/<lang>/book/<cid>/<pid>')
 def book_part(lang,cid,pid):
  require_lang(lang);b=get_book(s);allparts=parts(b);match=next(((c,p) for c,p in allparts if c['id']==cid and p['id']==pid),None)
  if not match or not any(match[1]['live'].get(l) for l in ('ru','en')):abort(404)
  c,p=match; v=p['live'].get(lang); seo=get_seo(s); available=[l for l in ('ru','en') if p['live'].get(l) and p['live'][l]['index'] and seo.get(l+'/book/'+cid+'/'+pid,{}).get('index') is not False]
  if not v:
   response=app.make_response(s['render_public']('book_wait.html',lang,section='book/'+cid+'/'+pid,title='Translation pending — '+b['title'][lang],book=b,book_view=True,available_langs=available,seo_robots='noindex, nosnippet'))
   response.headers['X-Robots-Tag']='noindex, nosnippet';return response
  published=parts(b,lang);idx=next(i for i,x in enumerate(published) if x[1]['id']==pid)
  previous=published[idx-1][1]['id'] if idx else ''; scene=scene_for_reader(b,lang,p,previous)
  title=(v['title'] or (('Глава ' if lang=='ru' else 'Chapter ')+str(c['number'])+' · '+('часть ' if lang=='ru' else 'part ')+str(p['number'])))+' — '+b['title'][lang]+' — Andy Coulbot'
  return s['render_public']('book_part.html',lang,section='book/'+cid+'/'+pid,title=title,description=v['description'] or ((('Глава '+str(c['number'])+', часть '+str(p['number'])+' книги «'+b['title'][lang]+'».') if lang=='ru' else ('Chapter '+str(c['number'])+', part '+str(p['number'])+' of '+b['title'][lang]+'.'))),book=b,chapter=c,part=p,version=v,scene=scene,part_html=text_html(v['body']),has_relation_change=any(e['published'] and any(f['public'] and f['after']==pid for f in e['relations']) for kind in ('characters','places') for e in b[kind]),prev=published[idx-1] if idx else None,next=published[idx+1] if idx+1<len(published) else None,book_view=True,available_langs=available,seo_robots=('nosnippet' if v['index'] else 'noindex, nosnippet'))
 @app.get('/<lang>/book/world')
 def book_world(lang):
  require_lang(lang);b=get_book(s);published=parts(b,lang);through=request.args.get('through','');pos=next((i for i,(_,p) in enumerate(published) if p['id']==through),-1) if through else -1
  visible_ids={p['id'] for _,p in published[:pos+1]}
  cards=visible_world(b,lang,through)
  response=app.make_response(s['render_public']('book_world.html',lang,section='book/world',title=('Мир книги' if lang=='ru' else 'The world')+' — '+b['title'][lang],description=(('Персонажи, места и связи книги «'+b['title'][lang]+'».') if lang=='ru' else ('People, places and connections in '+b['title'][lang]+'.')),book=b,cards=cards,through=through,book_view=True,available_langs=['ru','en'],seo_robots='noindex' if through else ''))
  if through:response.headers['X-Robots-Tag']='noindex';response.headers['Cache-Control']='private, no-store'
  return response

 @app.get('/<lang>/book/world/<eid>')
 def book_world_entry(lang,eid):
  require_lang(lang);b=get_book(s);through=request.args.get('through','')
  card=next((x for x in visible_world(b,lang,through) if x['id']==eid),None)
  if not card:abort(404)
  ent=next((e for kind in ('characters','places') for e in b[kind] if e['id']==eid),None)
  seo=get_seo(s);available=[l for l in ('ru','en') if ent['name'][l] and seo.get(l+'/book/world/'+eid,{}).get('index') is not False]
  r=app.make_response(s['render_public']('book_world_entry.html',lang,section='book/world/'+eid,title=card['name']+' — '+b['title'][lang],description=(next((f['text'] for f in card['facts'] if f['text']), '')[:250] or ((card['name']+' — '+('персонаж' if card['kind']=='characters' else 'место')+' книги «'+b['title'][lang]+'».') if lang=='ru' else (card['name']+' — '+('a character' if card['kind']=='characters' else 'a place')+' in '+b['title'][lang]+'.'))),book=b,card=card,through=through,book_view=True,available_langs=available,seo_robots='noindex' if through else ''))
  if through:r.headers['X-Robots-Tag']='noindex';r.headers['Cache-Control']='private, no-store'
  return r

def seo_pages(s,b):
 result=[]
 paths=['','about','news','privacy']+['project/'+p['slug'] for p in s['projects'](True) if not (p['slug']=='sera' and p.get('feature')=='book')]+['book','book/world']
 for path in paths:
  for lang in ('ru','en'):result.append({'key':lang+'/'+path,'url':s['SITE_URL']+'/'+lang+'/'+path,'label':('/'+lang+'/'+path)})
 for kind in ('characters','places'):
  for e in b[kind]:
   if e['published']:
    for lang in ('ru','en'):
     if e['name'][lang]:
      path='book/world/'+e['id'];result.append({'key':lang+'/'+path,'url':s['SITE_URL']+'/'+lang+'/'+path,'label':('/'+lang+'/'+path+' · '+e['name'][lang]+(' · после части' if e.get('after') else ''))})
 for c,p in parts(b):
  for lang in ('ru','en'):
   if p['live'].get(lang):
    path='book/'+c['id']+'/'+p['id'];result.append({'key':lang+'/'+path,'url':s['SITE_URL']+'/'+lang+'/'+path,'label':('/'+lang+'/'+path)})
 return result

def book_sitemap(b):
 paths=['book','book/world']
 paths += ['book/'+c['id']+'/'+p['id'] for c,p in parts(b)]
 for path in paths:
  if path.startswith('book/') and path!='book/world':
   _,cid,pid=path.split('/');p=next(p for c,p in parts(b) if p['id']==pid and c['id']==cid)
   langs=[l for l in ('ru','en') if p['live'].get(l) and p['live'][l]['index']]
  else:langs=['ru','en']
  if langs:yield path,langs
 for kind in ('characters','places'):
  for e in b[kind]:
   if e['published'] and not e.get('after'):
    langs=[l for l in ('ru','en') if e['name'][l]]
    if langs:yield 'book/world/'+e['id'],langs
