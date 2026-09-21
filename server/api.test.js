import {test} from 'node:test'
import assert from 'node:assert/strict'
import {mkdtemp, mkdir, writeFile, rm} from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {createDatasetApp} from './api.js'

test('ready-only pagination, independent languages, private-field filtering and video ranges',async t=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'egosteer-test-'))
 const rows=Array.from({length:15},(_,i)=>({episode_index:i,task_name:i<13?'Task A':'Task B',split:i%2?'val':'train',num_frames:30,fps:30,duration_seconds:1,rrd_path:'/private/source',annotation_sources:[{secret:'private'}],videos:{head:`assets/episodes/${String(i).padStart(6,'0')}/head.mp4`,chest:`assets/episodes/${String(i).padStart(6,'0')}/chest.mp4`},annotations:{en:['one','two'],zh:i===0?['中文']:[]}}))
 await writeFile(path.join(dir,'index.ready.jsonl'),rows.map(JSON.stringify).reverse().join('\n'))
 await writeFile(path.join(dir,'index.jsonl'),JSON.stringify({...rows[0],episode_index:999}))
 await writeFile(path.join(dir,'tasks.json'),JSON.stringify([{task_name:'Task A',episode_count:20},{task_name:'Task B',episode_count:2}]))
 await writeFile(path.join(dir,'progress.json'),JSON.stringify({total_episodes:22,status:'running'}))
 await mkdir(path.join(dir,'assets/episodes/000000'),{recursive:true})
 await writeFile(path.join(dir,'assets/episodes/000000/head.mp4'),'0123456789')
 const server=createDatasetApp(dir).listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r))
 t.after(async()=>{await new Promise(r=>server.close(r));await rm(dir,{recursive:true,force:true})})
 const base=`http://127.0.0.1:${server.address().port}`
 const get=async url=>(await fetch(base+url)).json()
 assert.equal((await get('/api/catalog')).tasks[0].ready_count,13)
 const first=await get('/api/episodes');assert.equal(first.total,15);assert.equal(first.items.length,12);assert.equal(first.items[0].episode_index,0)
 assert.equal((await get('/api/episodes?page=2')).items.length,3)
 assert.equal((await get('/api/episodes?task=Task%20B&split=train')).total,1)
 assert.equal((await get('/api/episodes?q='+encodeURIComponent('中文'))).total,1)
 assert.equal((await fetch(base+'/api/episodes/999')).status,404)
 const detail=await get('/api/episodes/0');assert.equal(detail.annotations.en.length,2);assert.equal(detail.annotations.zh.length,1);assert.equal(detail.rrd_path,undefined);assert.equal(detail.annotation_sources,undefined)
 const range=await fetch(base+'/dataset/assets/episodes/000000/head.mp4',{headers:{Range:'bytes=2-5'}});assert.equal(range.status,206);assert.equal(await range.text(),'2345');assert.match(range.headers.get('content-type'),/video\/mp4/)
 assert.equal((await fetch(base+'/dataset/assets/missing.mp4')).status,404)
 await writeFile(path.join(dir,'index.ready.jsonl'),rows.slice(0,1).map(JSON.stringify).join('\n'))
 assert.equal((await get('/api/episodes')).total,1)
})
