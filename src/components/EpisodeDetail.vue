<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { motion } from 'motion-v'
const props = defineProps({ episode:Object, entryId:Number, transition:Object, reduced:Boolean, canPrevious:Boolean, canNext:Boolean })
const emit = defineEmits(['previous','next','close'])
const head=ref(null), chest=ref(null), mountedMedia=ref(false), headReady=ref(false), chestReady=ref(false)
const playing=ref(false), time=ref(0), speed=ref('1'), error=ref(''), direction=ref('next')
let mediaTimer, playVersion=0
// Temporarily show English only. Restore the language ref and controls below to re-enable Chinese.
// const language=ref('en')
// const annotations=computed(()=>props.episode.annotations[language.value] || [])
const annotations=computed(()=>props.episode.annotations.en || [])
const stamp=n=>`${Math.floor((n||0)/60)}:${String(Math.floor((n||0)%60)).padStart(2,'0')}`
function pause(){playVersion++;playing.value=false;head.value?.pause();chest.value?.pause()}
async function play(){
  if(playing.value){pause();return}
  const h=head.value,c=chest.value
  if(!h||!c)return
  const version=++playVersion
  error.value=''
  if(h.ended)seek(0)
  c.currentTime=h.currentTime
  try{await Promise.all([h.play(),c.play()]);if(version!==playVersion){h.pause();c.pause();return}playing.value=true}
  catch{if(version===playVersion){pause();error.value='Unable to play this episode. Please try again.'}}
}
function seek(value){time.value=Number(value);for(const v of [head.value,chest.value])if(v?.readyState>=1)v.currentTime=Math.min(time.value,v.duration)}
function tick(){if(!head.value)return;time.value=head.value.currentTime;if(playing.value&&chest.value&&Math.abs(chest.value.currentTime-time.value)>.15)chest.value.currentTime=time.value}
function failed(){pause();error.value='A camera could not be loaded.'}
function retry(){error.value='';head.value?.load();chest.value?.load()}
function loaded(camera){if(camera==='head')headReady.value=true;else chestReady.value=true;for(const v of [head.value,chest.value])if(v)v.playbackRate=Number(speed.value)}
watch(()=>props.episode.episode_index,async(eid,previous)=>{
  direction.value=previous!==undefined && eid<previous?'previous':'next'
  pause();clearTimeout(mediaTimer);mountedMedia.value=false;headReady.value=false;chestReady.value=false;time.value=0;error.value=''
  // Animate lightweight cached posters first, then mount only these two videos.
  mediaTimer=setTimeout(async()=>{mountedMedia.value=true;await nextTick();for(const v of [head.value,chest.value])if(v)v.playbackRate=Number(speed.value)},props.reduced?0:previous===undefined?440:280)
},{immediate:true})
watch(speed,()=>{for(const v of [head.value,chest.value])if(v)v.playbackRate=Number(speed.value)})
onBeforeUnmount(()=>{pause();clearTimeout(mediaTimer)})
</script>

<template>
  <div class="detail-topline">
    <div class="episode-identity">Episode <strong>{{String(episode.episode_index).padStart(6,'0')}}</strong></div>
    <div class="detail-meta"><span>{{episode.split}}</span><span>{{episode.num_frames}} frames</span><span>{{episode.fps}} fps</span></div>
  </div>
  <div class="video-stage">
    <button class="video-step previous" :disabled="!canPrevious" aria-label="Previous episode" @click="emit('previous')">‹</button>
    <div class="videos">
      <motion.figure :layoutId="'preview-'+entryId" :transition="transition" :style="{borderRadius:'10px'}" class="camera head-camera">
        <Transition :name="'camera-'+direction"><div :key="episode.episode_index" class="camera-slide"><img :src="episode.thumbnails.head" alt="Head camera preview" class="video-poster">
        <video v-if="mountedMedia" :key="episode.episode_index" ref="head" :src="episode.videos.head" :poster="episode.thumbnails.head" :class="{ready:headReady}" playsinline muted preload="auto" @loadeddata="loaded('head')" @timeupdate="tick" @ended="pause" @error="failed" aria-label="Head camera video"></video>
        </div></Transition>
        <figcaption>Head</figcaption>
      </motion.figure>
      <motion.figure class="camera" :initial="{opacity:0}" :animate="{opacity:1}" :transition="{duration:reduced?0:.25,delay:reduced?0:.14}">
        <Transition :name="'camera-'+direction"><div :key="episode.episode_index" class="camera-slide"><img :src="episode.thumbnails.chest" alt="Chest camera preview" class="video-poster">
        <video v-if="mountedMedia" :key="episode.episode_index" ref="chest" :src="episode.videos.chest" :poster="episode.thumbnails.chest" :class="{ready:chestReady}" playsinline muted preload="auto" @loadeddata="loaded('chest')" @ended="pause" @error="failed" aria-label="Chest camera video"></video>
        </div></Transition>
        <figcaption>Chest</figcaption>
      </motion.figure>
    </div>
    <button class="video-step next" :disabled="!canNext" aria-label="Next episode" @click="emit('next')">›</button>
  </div>
  <div class="player">
    <button class="play-button" :disabled="!headReady||!chestReady" @click="play" :aria-label="playing?'Pause both videos':'Play both videos'">{{playing?'Ⅱ':'▶'}}</button>
    <button class="restart" @click="seek(0)" aria-label="Restart both videos">↺</button>
    <span class="time">{{stamp(time)}} <span>/ {{stamp(episode.duration_seconds)}}</span></span>
    <input class="seek" type="range" min="0" :max="episode.duration_seconds" step="0.033333" :value="time" @input="seek($event.target.value)" aria-label="Seek both videos">
    <select v-model="speed" aria-label="Playback speed"><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option></select>
  </div>
  <div v-if="error" class="media-error" role="alert">{{error}} <button @click="retry">Retry</button></div>
  <section class="annotations">
    <div class="annotation-heading">
      <h2>Annotations</h2>
      <!-- Temporarily disabled: English/Chinese annotation switch.
      <div class="language-switch" aria-label="Annotation language">
        <button :class="{active:language==='en'}" @click="language='en'" :aria-pressed="language==='en'">English</button>
        <button :class="{active:language==='zh'}" @click="language='zh'" :aria-pressed="language==='zh'">中文</button>
      </div>
      -->
    </div>
    <div class="annotation-track"><Transition :name="'annotation-'+direction"><ol :key="episode.episode_index" lang="en"><li v-for="(text,i) in annotations" :key="i"><span>{{String(i+1).padStart(2,'0')}}</span><p>{{text}}</p></li><li v-if="!annotations.length" class="muted"><p>No English annotations available.</p></li></ol></Transition></div>
    <p class="annotation-footnote">Original English annotations.</p>
  </section>
</template>
