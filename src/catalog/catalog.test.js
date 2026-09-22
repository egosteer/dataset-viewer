import { test } from 'node:test'
import assert from 'node:assert/strict'
import { publicEpisode, createCatalog, readJsonLines } from './catalog.js'
import { loadCatalog } from './load.js'
import { gzipSync } from 'node:zlib'

const base = 'https://ego-steer-1351596430.cos.ap-shanghai.myqcloud.com/previews/'
const episode = id => ({ episode_index:id, task_name:id<13?'Task A':'Task B',
  task_name_original:'Original', split:id%2?'val':'train',num_frames:30,fps:30,duration_seconds:1,
  videos:{head:base+`assets/episodes/${id}/head.mp4`,chest:base+`assets/episodes/${id}/chest.mp4`},
  thumbnails:{head:base+`assets/episodes/${id}/head.jpg`,chest:base+`assets/episodes/${id}/chest.jpg`},
  annotations:{en:['one','two'],zh:id===0?['中文']:[]},rrd_path:'/private',annotation_sources:['private'] })

test('static COS catalog preserves absolute media and filters/paginates without a server', () => {
  const query = createCatalog(Array.from({length:15},(_,i)=>publicEpisode(episode(i))).reverse())
  assert.equal(query('/api/catalog').tasks[0].ready_count,13)
  const page = query('/api/episodes?page=2')
  assert.equal(page.total,15);assert.equal(page.items.length,3);assert.equal(page.items[0].episode_index,12)
  assert.equal(query('/api/episodes?task=Task%20B&split=train').total,1)
  assert.equal(query('/api/episodes?q='+encodeURIComponent('中文')).total,1)
  const detail = query('/api/episodes/0')
  assert.equal(detail.videos.head,episode(0).videos.head)
  assert.equal(detail.thumbnails.head,episode(0).thumbnails.head)
  assert.equal(detail.annotations.en.length,2);assert.equal(detail.annotations.zh.length,1)
  assert.equal(detail.rrd_path,undefined);assert.equal(detail.annotation_sources,undefined)
  assert.throws(()=>query('/api/episodes/999'),/not found/)
  assert.throws(()=>createCatalog([detail,detail]),/Duplicate/)
})

test('public records reject local or non-HTTPS media', () => {
  for (const value of ['/dataset/assets/head.mp4','javascript:alert(1)','http://example.com/head.mp4']) {
    const row=episode(0);row.videos.head=value
    assert.throws(()=>publicEpisode(row))
  }
})

test('stream parsing handles UTF-8 split across chunks and a final line without newline', async () => {
  const input=JSON.stringify(episode(0))+'\n'+JSON.stringify(episode(1))
  const bytes=new TextEncoder().encode(input)
  const response=new Response(new ReadableStream({start(controller){
    for(const byte of bytes)controller.enqueue(new Uint8Array([byte]))
    controller.close()
  }}))
  const rows=[];await readJsonLines(response,r=>rows.push(publicEpisode(r)))
  assert.equal(rows.length,2);assert.equal(rows[0].annotations.zh[0],'中文')
})

test('healthy COS index takes priority over the bundled snapshot', async () => {
  const calls=[]
  const query=await loadCatalog('remote','fallback',async url=>{
    calls.push(url);return new Response(JSON.stringify(episode(7))+'\n')
  })
  assert.deepEqual(calls,['remote'])
  assert.equal(query('/api/episodes/7').videos.head,episode(7).videos.head)
})

test('403, network, malformed and empty COS responses fall back to compressed static index', async () => {
  for (const mode of ['403','network','invalid','empty']) {
    const query=await loadCatalog('remote','fallback',async url=>{
      if(url==='fallback')return new Response(gzipSync(JSON.stringify(episode(0))+'\n'))
      if(mode==='network')throw new TypeError('Failed to fetch')
      return new Response(mode==='invalid'?'bad json':'',{status:mode==='403'?403:200})
    })
    assert.equal(query('/api/catalog').progress.ready_episodes,1)
    assert.equal(query('/api/episodes/0').annotations.zh[0],'中文')
    assert.equal(query('/api/episodes/0').thumbnails.head,episode(0).thumbnails.head)
  }
})

test('a stalled COS request times out and loads the bundled catalog', async () => {
  const query=await loadCatalog('remote','fallback',async (url,{signal})=>{
    if(url==='fallback')return new Response(gzipSync(JSON.stringify(episode(0))+'\n'))
    return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('timeout')),{once:true}))
  },5)
  assert.equal(query('/api/catalog').progress.ready_episodes,1)
  await assert.rejects(()=>loadCatalog('remote','fallback',async()=>new Response('',{status:403})),/Neither/)
})
