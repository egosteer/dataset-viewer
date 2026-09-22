<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { motion, AnimatePresence, LayoutGroup, useReducedMotion } from 'motion-v'
import EpisodeDetail from './components/EpisodeDetail.vue'
import { datasetGet as get } from './catalog/client.js'
const catalog=ref(null), task=ref(''), taskSearch=ref(''), split=ref(''), page=ref(1)
const list=ref({items:[],total:0}), selected=ref(null), loading=ref(true), pending=ref(null), error=ref(''), detailError=ref('')
const sharedEpisodeId=ref(null)
const availableOnly=ref(true), dark=ref(localStorage.getItem('egosteer-browser-theme')==='dark')
const reduced=useReducedMotion()
const transition=computed(()=>({type:'tween',duration:reduced.value?0:.46,ease:[.22,1,.36,1]}))
const tasks=computed(()=>(catalog.value?.tasks||[]).filter(t=>(!availableOnly.value||t.ready_count>0)&&t.task_name.toLowerCase().includes(taskSearch.value.toLowerCase())))
const pageCount=computed(()=>Math.max(1,Math.ceil(list.value.total/12)))
const selectedIndex=computed(()=>list.value.items.findIndex(r=>r.episode_index===selected.value?.episode_index))
const number=n=>new Intl.NumberFormat('en').format(n||0)
const id=n=>String(n).padStart(6,'0')
const stamp=n=>`${Math.floor((n||0)/60)}:${String(Math.floor((n||0)%60)).padStart(2,'0')}`
const details=new Map(), prefetches=new Map(), imageFailures=ref(new Set())
let listAbort, selectionVersion=0, opener, focusTimer, overviewScroll=0
async function initialize(){error.value='';try{catalog.value=await get('/api/catalog');await loadList()}catch(e){error.value=e.message;loading.value=false}}
async function loadList(){
  clearTimeout(focusTimer);listAbort?.abort();selectionVersion++;selected.value=null;pending.value=null;detailError.value=''
  const controller=new AbortController();listAbort=controller;loading.value=true;error.value=''
  try{list.value=await get('/api/episodes?'+new URLSearchParams({task:task.value,split:split.value,page:String(page.value)}),controller.signal)}catch(e){if(e.name!=='AbortError')error.value=e.message}finally{if(!controller.signal.aborted)loading.value=false}
}
function fetchDetail(eid){
  if(details.has(eid))return Promise.resolve(details.get(eid))
  if(prefetches.has(eid))return prefetches.get(eid)
  const promise=get('/api/episodes/'+eid).then(r=>{details.set(eid,r);return r}).finally(()=>prefetches.delete(eid))
  prefetches.set(eid,promise);return promise
}
function prime(eid){fetchDetail(eid).catch(()=>{})}
async function openEpisode(eid,event){
  if(selected.value?.episode_index===eid)return
  clearTimeout(focusTimer)
  const entering=!selected.value
  const version=++selectionVersion;pending.value=eid;detailError.value=''
  if(!selected.value){opener=event?.currentTarget;overviewScroll=window.scrollY}
  try{
    const record=await fetchDetail(eid)
    if(version!==selectionVersion)return
    if(entering)sharedEpisodeId.value=eid
    selected.value=record
    await nextTick()
    // Let the shared-element transform finish before any focus/scroll adjustment.
    focusTimer=setTimeout(()=>{
      if(version!==selectionVersion)return
      revealSelectedEpisode()
      const button=document.querySelector('.back-button')
      if(document.activeElement===document.body)button?.focus({preventScroll:true})
      const detail=document.querySelector('.detail-panel')
      if(detail && detail.getBoundingClientRect().top<0)detail.scrollIntoView({behavior:reduced.value?'instant':'smooth',block:'start'})
    },entering&&!reduced.value?500:0)
  }catch(e){if(version===selectionVersion)detailError.value=e.message}
  finally{if(version===selectionVersion)pending.value=null}
}
function revealSelectedEpisode(){
  const rail=document.querySelector('.is-detail .collection')
  const card=rail?.querySelector('.chosen')
  if(!rail||!card)return
  const outer=rail.getBoundingClientRect(),inner=card.getBoundingClientRect()
  rail.scrollTo({
    top:rail.scrollTop+inner.top-outer.top-(rail.clientHeight-inner.height)/2,
    left:rail.scrollLeft+inner.left-outer.left-(rail.clientWidth-inner.width)/2,
    behavior:reduced.value?'instant':'smooth'
  })
}
function closeDetail(){
  selectionVersion++;pending.value=null;selected.value=null;detailError.value='';clearTimeout(focusTimer)
  focusTimer=setTimeout(()=>{opener?.focus({preventScroll:true});window.scrollTo({top:overviewScroll,behavior:reduced.value?'instant':'smooth'})},reduced.value?0:470)
}
function step(delta){const target=list.value.items[selectedIndex.value+delta];if(target)openEpisode(target.episode_index)}
function chooseTask(name){if(task.value===name){if(selected.value)closeDetail();return}task.value=name}
function changePage(delta){page.value+=delta;loadList()}
function keydown(e){if(e.key==='Escape'&&selected.value){e.preventDefault();closeDetail()}}
function imageFailed(eid){imageFailures.value=new Set([...imageFailures.value,eid])}
watch([task,split],()=>{page.value=1;loadList()})
watch(dark,v=>{document.documentElement.classList.toggle('dark',v);localStorage.setItem('egosteer-browser-theme',v?'dark':'light')},{immediate:true})
onMounted(()=>{initialize();window.addEventListener('keydown',keydown)})
onBeforeUnmount(()=>{listAbort?.abort();selectionVersion++;clearTimeout(focusTimer);window.removeEventListener('keydown',keydown)})
</script>

<template>
  <header class="nav"><div class="nav-inner"><a class="brand" href="https://egosteer.github.io">EgoSteer</a><span class="brand-sub">Dataset browser</span><nav><a href="https://egosteer.github.io">Project ↗</a><a href="https://huggingface.co/datasets/EgoSteer/EgoSteer-RealWorld">Dataset ↗</a><button class="theme" @click="dark=!dark" :aria-label="dark?'Use light theme':'Use dark theme'">{{dark?'☀':'☾'}}</button></nav></div></header>
  <main class="browser-layout">
    <aside class="sidebar">
      <div class="sidebar-heading"><h2>Tasks</h2><span>{{tasks.length}}</span></div>
      <div class="search-wrap"><span>⌕</span><input v-model="taskSearch" type="search" placeholder="Find a task…" aria-label="Find a task"></div>
      <label class="split-filter"><span>Split</span><select v-model="split" aria-label="Dataset split"><option value="">All splits</option><option value="train">Train</option><option value="val">Validation</option></select></label>
      <label class="available"><input v-model="availableOnly" type="checkbox"> Available episodes only</label>
      <button class="task all-task" :class="{active:!task}" @click="chooseTask('')"><span>All tasks</span><span class="count">{{number(catalog?.progress.ready_episodes)}}</span></button>
      <div class="task-list"><button v-for="t in tasks" :key="t.task_name" class="task" :class="{active:task===t.task_name}" @click="chooseTask(t.task_name)"><span>{{t.task_name}}</span><span class="count">{{t.ready_count}}</span></button><p v-if="!tasks.length" class="muted empty-task">No matching tasks.</p></div>
      <div class="sidebar-foot"><p v-if="catalog?.progress.preview">Local preview · {{number(catalog.progress.ready_episodes)}} episodes</p><p v-else>{{number(catalog?.progress.ready_episodes)}} playable episodes</p><span>{{number(catalog?.progress.total_episodes)}} total · {{catalog?.tasks.length}} tasks</span></div>
    </aside>
    <section class="workspace" aria-label="Episode browser">
      <div class="workspace-heading"><div><h1>{{task || 'All episodes'}}</h1><p v-if="!selected">{{number(list.total)}} episodes <span>· Head camera previews</span></p><p v-else-if="!task">{{selected.task_name}}</p></div><button v-if="selected" class="back-button" @click="closeDetail"><span>↗</span> All previews</button></div>
      <div v-if="error" class="state" role="alert"><h2>Unable to load the dataset</h2><p>{{error}}</p><button @click="initialize">Try again</button></div>
      <div v-else-if="loading" class="state" role="status"><div class="spinner"></div><p>Loading episodes…</p></div>
      <div v-else-if="!list.items.length" class="state"><h2>No playable episodes</h2><p>Try another task or change the split filter.</p><button @click="split='';task=''">Clear filters</button></div>
      <template v-else>
        <div v-if="detailError" role="alert" class="media-error">{{detailError}}</div>
        <LayoutGroup id="episode-explorer">
          <div class="explorer" :class="{'is-detail':selected}">
            <motion.div layout layoutScroll class="collection" :transition="transition" aria-label="Episode previews">
              <motion.button v-for="r in list.items" :key="r.episode_index" layout :transition="transition" class="episode-card" :class="{chosen:selected?.episode_index===r.episode_index,pending:pending===r.episode_index}" :aria-label="'Open episode '+id(r.episode_index)" :aria-pressed="selected?.episode_index===r.episode_index" :aria-busy="pending===r.episode_index" @pointerenter="prime(r.episode_index)" @focus="prime(r.episode_index)" @click="openEpisode(r.episode_index,$event)">
                <div class="card-preview"><img v-if="selected && r.episode_index===sharedEpisodeId" class="thumbnail-underlay" :src="r.thumbnails.head" alt="">
                <motion.div :layoutId="'preview-'+r.episode_index" :transition="transition" class="thumbnail" :style="{borderRadius:'10px'}">
                  <img v-if="!imageFailures.has(r.episode_index)" :src="r.thumbnails.head" :alt="r.task_name+' — head camera'" :loading="selected?'eager':'lazy'" decoding="async" width="640" height="480" @error="imageFailed(r.episode_index)">
                  <span v-else class="preview-unavailable">Preview unavailable</span>
                  <span class="duration">{{stamp(r.duration_seconds)}}</span>
                  <span class="open-indicator">↗</span>
                </motion.div></div>
                <div class="card-copy"><div class="card-title"><strong>{{id(r.episode_index)}}</strong><span>{{r.split}}</span></div><p>{{task ? r.instruction : r.task_name}}</p></div>
              </motion.button>
            </motion.div>
            <AnimatePresence>
              <motion.article v-if="selected" key="detail" class="detail-panel" :initial="{opacity:0}" :animate="{opacity:1}" :exit="{opacity:0}" :transition="{duration:reduced?0:.18}" aria-label="Episode detail">
                <EpisodeDetail :episode="selected" :entryId="sharedEpisodeId" :transition="transition" :reduced="!!reduced" :canPrevious="selectedIndex>0" :canNext="selectedIndex<list.items.length-1" @previous="step(-1)" @next="step(1)" @close="closeDetail" />
              </motion.article>
            </AnimatePresence>
          </div>
        </LayoutGroup>
        <div v-if="pageCount>1" class="pagination"><button :disabled="page<=1" @click="changePage(-1)" aria-label="Previous page">←</button><span>{{page}} / {{pageCount}}</span><button :disabled="page>=pageCount" @click="changePage(1)" aria-label="Next page">→</button></div>
      </template>
    </section>
  </main>
</template>
