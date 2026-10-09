import os, tempfile, asyncio
os.environ['SAOCB_DB_PATH']=tempfile.mktemp(prefix='saocb-',suffix='.db')
os.environ.pop('SAOCB_API_SECRET',None)
import httpx
from saocb_app import app

async def main():
    tr=httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=tr,base_url='http://saocb.local') as c:
        checks=[]
        async def ck(method,path,**kw):
            r=await c.request(method,path,**kw)
            assert r.status_code==200,(path,r.status_code,r.text)
            j=r.json(); assert j.get('status')==200,(path,j)
            checks.append(path); return j
        await ck('GET','/api')
        reg=await ck('POST','/api/user/register',json={'user_id':'stable-test'})
        assert reg['result']['user_id']=='stable-test'
        await ck('POST','/api/tutorial/start',json={'user_id':'stable-test'})
        await ck('POST','/api/tutorial/step',json={'user_id':'stable-test','step':1})
        await ck('POST','/api/quest/start-tutorial',json={'user_id':'stable-test','quest_id':1})
        user=await ck('GET','/api/user/stable-test')
        assert user['result']['character'], user
        assert user['result']['party'], user
        print('SAO-CB smoke test OK:',len(checks),'critical calls')
        for x in checks: print('  OK',x)
asyncio.run(main())
