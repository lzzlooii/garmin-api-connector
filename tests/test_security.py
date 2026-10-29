import asyncio,base64,importlib.util,inspect,json,logging,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from types import SimpleNamespace
from garmin_mcp import client,official,server,web
from requests import Session

async def request(path='/',method='GET',body=b'',headers=None,scheme='https',ip='203.0.113.9'):
    out=[];sent=False
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':scheme,'path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','headers':[(b'host',b'example.test')]+[(k.lower().encode(),v.encode()) for k,v in (headers or {}).items()],'client':(ip,50000),'server':('example.test',443)}
    async def receive():
        nonlocal sent
        if not sent:sent=True;return {'type':'http.request','body':body,'more_body':False}
        await asyncio.sleep(3600)
    async def send(m):out.append(m)
    await web.app(scope,receive,send)
    status=next(x['status'] for x in out if x['type']=='http.response.start')
    heads=dict(next(x['headers'] for x in out if x['type']=='http.response.start'))
    content=b''.join(x.get('body',b'') for x in out if x['type']=='http.response.body')
    return status,heads,content

class Security(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'GARMIN_MCP_DATA':self.tmp.name,'GARMIN_REGION':'cn','ADMIN_PASSWORD':'test-admin-password-1234','ALLOWED_HOSTS':'example.test','PUBLIC_URL':'https://example.test'},clear=False);self.env.start();os.environ.pop('GARMIN_PERSONAL_API_KEY',None);os.environ.pop('ALLOW_URL_SECRET',None);server.reset_client();web._fails.clear()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def test_private_files(self):
  d=client.data_dir();d.chmod(0o755);f=d/'personal_api_key';f.write_text('old');f.chmod(0o644);official.save_key('DUMMYKEY-123456789');self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o600);self.assertEqual(stat.S_IMODE(d.stat().st_mode),0o700);self.assertEqual(official.get_key(),'DUMMYKEY-123456789')
 def test_symlink_write_rejected(self):
  target=Path(self.tmp.name)/'outside';target.write_text('keep');f=client.data_dir()/'personal_api_key';f.symlink_to(target)
  with self.assertRaises(RuntimeError):official.save_key('dummy')
  self.assertEqual(target.read_text(),'keep')
 def test_symlink_read_rejected(self):
  target=Path(self.tmp.name)/'outside';target.write_text('dummy');(client.data_dir()/'personal_api_key').symlink_to(target)
  with self.assertRaises(OSError):official.get_key()
 def test_config_temp_symlink_no_effect(self):
  t=Path(self.tmp.name)/'elsewhere';t.write_text('keep');(client.data_dir()/'config.tmp').symlink_to(t);client.save_config(region='cn');self.assertEqual(t.read_text(),'keep')
 def test_config_and_cache_private(self):
  c=client.load_config();self.assertEqual(len(c['secret']),43)
  a=official.PrivateAuthenticator(bearer_token_cache_file=client.data_dir()/'official_token.json');a._write_cached_token('fp',SimpleNamespace(access_token='DUMMYTOKEN',expires_at=9999999999));self.assertEqual(stat.S_IMODE((client.data_dir()/'official_token.json').stat().st_mode),0o600)
 def test_outbound_allowlist(self):
  s=official.GarminSession(official.BASE_URLS['cn'])
  for url in ['http://personal.connectapi.garmin.cn/x','https://evil.example/x','https://personal.connectapi.garmin.cn.evil.example/x','https://user@personal.connectapi.garmin.cn/x']:
   with self.assertRaises(official.OfficialError):s.get(url)
 def test_no_redirect_following(self):
  s=official.GarminSession(official.BASE_URLS['cn']);resp=Mock(status_code=302)
  with patch.object(Session,'request',return_value=resp) as f:
   with self.assertRaises(official.OfficialError):s.get(official.BASE_URLS['cn']+'/x')
   self.assertFalse(f.call_args.kwargs['allow_redirects'])
 def test_sdk_uses_allowed_host(self):
  with patch.dict(os.environ,{'GARMIN_PERSONAL_API_BASE_URL':'https://evil.example'}):
   o=official.OfficialSource('DUMMY',region_='cn');self.assertEqual(o._auth.base_url,official.BASE_URLS['cn']);self.assertIsInstance(o._auth._session,official.GarminSession)
 def test_raw_sdk_error_not_exposed(self):
  o=official.OfficialSource('DUMMY')
  from garmin_personal_api.errors import GarminPersonalApiError
  with patch.object(o,'_get_client',side_effect=GarminPersonalApiError('DUMMY_SECRET_LONG_TOKEN_HERE')):
   with self.assertRaises(official.OfficialError) as ctx:o.call(lambda c:None)
   self.assertNotIn('DUMMY_SECRET',str(ctx.exception))
 def test_log_auth_redaction(self):
  for auth in ['Bearer DUMMY_SECRET','ApiKey DUMMY_SECRET','/k/DUMMY_SECRET/mcp']:
   record=web._redacting_record('test',logging.INFO,__file__,1,'%s',(auth,),None);self.assertNotIn('DUMMY_SECRET',record.getMessage())
 def test_remote_http_blocked(self):self.assertEqual(asyncio.run(request(scheme='http'))[0],400)
 def test_host_header_blocked(self):
  with patch.object(web,'_allowed_host',return_value=False):self.assertEqual(asyncio.run(request())[0],400)
 def test_unauthenticated_mcp(self):self.assertEqual(asyncio.run(request('/mcp'))[0],401)
 def test_url_secret_disabled(self):
  secret=client.load_config()['secret'];self.assertEqual(asyncio.run(request('/k/'+secret+'/mcp'))[0],401)
 def test_correct_bearer_passes(self):
  async def fake(scope,receive,send):await web.JSONResponse({'passed':True})(scope,receive,send)
  with patch.object(web.app,'_mcp',side_effect=fake):
   result=asyncio.run(request('/mcp',headers={'Authorization':'Bearer '+client.load_config()['secret']}));self.assertEqual(result[0],200)
 def test_mcp_key_rotation(self):
  old=client.load_config()['secret'];client.save_config(secret=client.new_secret());self.assertEqual(asyncio.run(request('/mcp',headers={'Authorization':'Bearer '+old}))[0],401)
 def test_admin_wrong_password_and_csrf(self):
  for origin in ['https://evil.test','null','']:
   result=asyncio.run(request('/login','POST',b'password=test-admin-password-1234',headers={'origin':origin,'content-type':'application/x-www-form-urlencoded'}));self.assertEqual(result[0],403)
  result=asyncio.run(request('/login','POST',b'password=wrong',headers={'origin':'https://example.test','content-type':'application/x-www-form-urlencoded'}));self.assertEqual(result[0],401)
 def test_admin_login_cookie_and_logout(self):
  result=asyncio.run(request('/login','POST',b'password=test-admin-password-1234',headers={'origin':'https://example.test','content-type':'application/x-www-form-urlencoded'}));self.assertEqual(result[0],303);cookie=result[1][b'set-cookie'].decode();self.assertIn('Secure',cookie);self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=strict',cookie);raw=cookie.split(';')[0]
  result=asyncio.run(request('/',headers={'cookie':raw}));self.assertEqual(result[0],200);self.assertIn(b'no-store',result[1][b'cache-control']);self.assertEqual(result[1][b'referrer-policy'],b'no-referrer')
  result=asyncio.run(request('/logout','POST',headers={'cookie':raw,'origin':'https://example.test'}));self.assertEqual(result[0],303)
  result=asyncio.run(request('/',headers={'cookie':raw}));self.assertNotIn('已配置密钥'.encode(),result[2])
 def test_login_throttle(self):
  for _ in range(5):asyncio.run(request('/login','POST',b'password=wrong',headers={'origin':'https://example.test','content-type':'application/x-www-form-urlencoded'}))
  result=asyncio.run(request('/login','POST',b'password=test-admin-password-1234',headers={'origin':'https://example.test','content-type':'application/x-www-form-urlencoded'}));self.assertIn('尝试次数过多'.encode(),result[2])
 def test_tools_unchanged(self):
  tools=asyncio.run(server.mcp.list_tools());expected=json.loads((Path(__file__).resolve().parents[1]/'OFFICIAL-API-MAPPING.json').read_text())['dedicated_data_methods'];self.assertEqual(set(x.name for x in tools),set(expected));self.assertEqual(len(tools),24)

if __name__=='__main__':unittest.main(verbosity=2)
