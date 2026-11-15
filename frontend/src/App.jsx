import { useEffect, useRef, useState } from 'react'
import YouTube from 'react-youtube'
import {
  Check, Clock, FileText, GraduationCap, Hash, Loader2, MessageSquareText,
  NotebookPen, Play, ScrollText, Search, Send, Sparkles, Users, X, Youtube,
} from 'lucide-react'

// Production build (served by the backend) -> same-origin "/api"; dev -> backend dev server.
const API = import.meta.env.PROD ? '' : (import.meta.env.VITE_API_URL || 'http://localhost:8000')

const TABS = [
  ['summary', 'Summary', FileText],
  ['chat', 'Chat', MessageSquareText],
  ['chapters', 'Chapters', Clock],
  ['notes', 'Notes', NotebookPen],
  ['quiz', 'Quiz', GraduationCap],
  ['keywords', 'Keywords', Hash],
  ['entities', 'Entities', Users],
  ['transcript', 'Transcript', ScrollText],
]

// ---------- helpers ----------
async function api(path, options = {}) {
  const res = await fetch(API + path, options)
  let body = {}
  try { body = await res.json() } catch { /* no json body */ }
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`)
  return body
}

const post = (path, payload) =>
  api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })

function fmt(seconds) {
  const t = Math.max(0, Math.floor(seconds || 0))
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = t % 60
  const pad = (n) => String(n).padStart(2, '0')
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

function parseTs(str) {
  const p = str.split(':').map(Number)
  return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1]
}

// Render inline text: **bold** and clickable MM:SS / H:MM:SS timestamps.
function renderInline(text, onSeek) {
  return String(text).split(/(\*\*[^*]+\*\*|\d{1,2}:\d{2}(?::\d{2})?)/g).map((tok, i) => {
    if (/^\*\*[\s\S]+\*\*$/.test(tok)) return <strong key={i}>{tok.slice(2, -2)}</strong>
    if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(tok))
      return <button type="button" className="ts" key={i} onClick={() => onSeek(parseTs(tok))}>{tok}</button>
    return <span key={i}>{tok}</span>
  })
}

function Markdown({ text, onSeek }) {
  const lines = String(text || '').split('\n')
  const blocks = []
  let list = null
  const flush = () => { if (list) { blocks.push(<ul key={`ul${blocks.length}`}>{list}</ul>); list = null } }
  lines.forEach((raw, idx) => {
    const line = raw.trimEnd()
    if (!line.trim()) { flush(); return }
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    const li = line.match(/^\s*[-*]\s+(.*)$/)
    const nli = line.match(/^\s*\d+\.\s+(.*)$/)
    if (h) {
      flush()
      const Tag = h[1].length <= 2 ? 'h3' : 'h4'
      blocks.push(<Tag key={idx}>{renderInline(h[2], onSeek)}</Tag>)
    } else if (li || nli) {
      list = list || []
      list.push(<li key={`li${idx}`}>{renderInline((li ? li[1] : nli[1]), onSeek)}</li>)
    } else {
      flush()
      blocks.push(<p key={idx}>{renderInline(line.replace(/^#+\s*/, ''), onSeek)}</p>)
    }
  })
  flush()
  return <div className="prose">{blocks}</div>
}

// ---------- app ----------
export default function App() {
  const [url, setUrl] = useState('')
  const [doc, setDoc] = useState(null)
  const [active, setActive] = useState('summary')
  const [loading, setLoading] = useState('')
  const [error, setError] = useState('')
  const [results, setResults] = useState({})
  const [history, setHistory] = useState([])
  const [question, setQuestion] = useState('')
  const [health, setHealth] = useState(null)
  const playerRef = useRef(null)

  useEffect(() => { api('/api/health').then(setHealth).catch(() => {}) }, [])

  const seek = (seconds) => {
    const p = playerRef.current
    if (p) { p.seekTo(seconds, true); p.playVideo && p.playVideo() }
  }

  async function processVideo(e) {
    e && e.preventDefault()
    if (!url.trim()) return
    setLoading('process'); setError('')
    try {
      const d = await post('/api/process', { url: url.trim() })
      setDoc(d); setResults({}); setHistory([]); setActive('summary')
      generate('summary', d.doc_id)
    } catch (err) { setError(err.message) } finally { setLoading('') }
  }

  async function generate(tab, id) {
    id = id || (doc && doc.doc_id)
    if (!id) return
    setLoading(tab); setError('')
    try {
      if (tab === 'transcript') {
        const b = await api(`/api/transcript/${id}`)
        setResults((r) => ({ ...r, transcript: b.segments }))
      } else {
        const payload = { doc_id: id }
        if (tab === 'quiz') payload.num_questions = 5
        const b = await post(`/api/${tab}`, payload)
        setResults((r) => ({ ...r, [tab]: b[tab] }))
      }
    } catch (err) { setError(err.message) } finally { setLoading('') }
  }

  async function ask(e) {
    e.preventDefault()
    const q = question.trim()
    if (!q || !doc) return
    setQuestion(''); setLoading('chat'); setError('')
    try {
      const b = await post('/api/ask', { doc_id: doc.doc_id, question: q })
      setHistory((h) => [...h, { question: q, answer: b.answer, sources: b.sources }])
    } catch (err) { setError(err.message) } finally { setLoading('') }
  }

  // auto-load transcript (cheap, no LLM) when its tab is opened
  useEffect(() => {
    if (doc && active === 'transcript' && !results.transcript && loading !== 'transcript') generate('transcript')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, doc])

  function reset() {
    setDoc(null); setResults({}); setHistory([]); setError(''); setUrl(''); setActive('summary')
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" onClick={reset}><b><Youtube /></b>Clip<em>Mind</em></div>
        <form className="urlbar" onSubmit={processVideo}>
          <Youtube className="ic" />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste a YouTube lecture URL…"
          />
          <button disabled={loading === 'process' || !url.trim()}>
            {loading === 'process' ? <Loader2 className="spin" /> : <Sparkles />}
            {loading === 'process' ? 'Processing…' : 'Analyze'}
          </button>
        </form>
        {health && (
          <span className="pill" title={health.llm_key_configured ? 'LLM key configured' : 'No LLM key set'}>
            <i className={health.llm_key_configured ? 'ok' : 'bad'} />{health.llm_model}
          </span>
        )}
      </header>

      {health && !health.llm_key_configured && (
        <div className="warn">No LLM API key configured. Add <code>GEMINI_API_KEY</code> to <code>backend/.env</code> to enable AI features.</div>
      )}

      {!doc ? (
        <Landing loading={loading === 'process'} error={error} onPick={(u) => setUrl(u)} />
      ) : (
        <main className="workspace">
          <section className="left">
            <div className="player">
              <YouTube
                videoId={doc.video_id}
                opts={{ width: '100%', height: '100%', playerVars: { modestbranding: 1, rel: 0 } }}
                onReady={(e) => { playerRef.current = e.target }}
                iframeClassName="yt-iframe"
                className="yt"
              />
            </div>
            <div className="meta">
              <h1>{doc.title}</h1>
              <p>{doc.channel}</p>
              <div className="tags">
                <span><Clock />{fmt(doc.duration)}</span>
                <span>{doc.num_chunks} chunks</span>
                <span className={doc.source === 'captions' ? 'src' : 'src whisper'}>
                  {doc.source === 'captions' ? 'YouTube captions' : 'Whisper transcript'}
                </span>
              </div>
            </div>
          </section>

          <section className="right">
            <nav className="tabs">
              {TABS.map(([id, label, Icon]) => (
                <button key={id} className={active === id ? 'on' : ''} onClick={() => { setActive(id); setError('') }}>
                  <Icon />{label}
                </button>
              ))}
            </nav>

            {error && <div className="error"><X />{error}</div>}

            <div className="content">
              <Content
                active={active}
                data={results[active]}
                busy={loading === active}
                generate={() => generate(active)}
                seek={seek}
                history={history}
                question={question}
                setQuestion={setQuestion}
                ask={ask}
                chatBusy={loading === 'chat'}
              />
            </div>
          </section>
        </main>
      )}
    </div>
  )
}

function Landing({ loading, error, onPick }) {
  const samples = [
    ['3Blue1Brown · Neural networks', 'https://www.youtube.com/watch?v=aircAruvnKk'],
    ['Andrej Karpathy · Intro to LLMs', 'https://www.youtube.com/watch?v=zjkBMFhNj_g'],
  ]
  return (
    <section className="landing">
      <label><Sparkles />YOUR AI STUDY COMPANION</label>
      <h1>Turn any lecture into<br /><em>answers, notes & quizzes.</em></h1>
      <p>Paste a YouTube link. ClipMind transcribes it, then lets you chat with the video, jump to any moment, and study smarter.</p>
      {loading && <div className="loadingBig"><Loader2 className="spin" />Transcribing & indexing the video… (videos without captions take longer)</div>}
      {error && <div className="error"><X />{error}</div>}
      <div className="samples">
        <small>Try one:</small>
        {samples.map(([label, u]) => <button key={u} onClick={() => onPick(u)}>{label}</button>)}
      </div>
      <div className="features">
        <Feature icon={MessageSquareText} title="Chat with timestamps" text="Ask anything; answers link straight to the moment in the video." />
        <Feature icon={Clock} title="Auto chapters" text="The lecture, split into clickable sections automatically." />
        <Feature icon={GraduationCap} title="Notes & quizzes" text="Exam-ready notes and self-test MCQs in one click." />
      </div>
    </section>
  )
}

const Feature = ({ icon: Icon, title, text }) => (
  <article><b><Icon /></b><h3>{title}</h3><p>{text}</p></article>
)

function Content({ active, data, busy, generate, seek, history, question, setQuestion, ask, chatBusy }) {
  if (active === 'chat') return <Chat history={history} question={question} setQuestion={setQuestion} ask={ask} busy={chatBusy} seek={seek} />
  if (active === 'transcript') return <Transcript segments={data} busy={busy} seek={seek} />

  if (busy && !data) return <Panel><div className="center"><Loader2 className="spin big" /><p>Generating…</p></div></Panel>
  if (!data) return (
    <Panel>
      <div className="empty">
        <b><Sparkles /></b>
        <h2>Ready when you are</h2>
        <p>ClipMind will analyze the video and build this for you.</p>
        <button className="primary" onClick={generate} disabled={busy}>{busy ? 'Analyzing…' : 'Generate'}</button>
      </div>
    </Panel>
  )

  if (active === 'summary') return <Panel><Markdown text={data} onSeek={seek} /></Panel>
  if (active === 'notes') return <Panel><Markdown text={data} onSeek={seek} /></Panel>
  if (active === 'chapters') return <Chapters chapters={data} seek={seek} />
  if (active === 'keywords') return (
    <Panel>
      <div className="chips">{data.map((k, i) => <span key={k + i}><b>{String(i + 1).padStart(2, '0')}</b>{k}</span>)}</div>
    </Panel>
  )
  if (active === 'quiz') return <Quiz quiz={data} />
  if (active === 'entities') {
    const groups = data.reduce((all, e) => ({ ...all, [e.type]: [...(all[e.type] || []), e.text] }), {})
    return (
      <Panel>
        <div className="entities">
          {Object.entries(groups).map(([type, items]) => (
            <section key={type}><b>{type}</b><div>{items.map((it) => <span key={it}>{it}</span>)}</div></section>
          ))}
        </div>
      </Panel>
    )
  }
  return null
}

const Panel = ({ children }) => <div className="panel">{children}</div>

function Chapters({ chapters, seek }) {
  if (!chapters.length) return <Panel><p className="muted">No chapters were detected.</p></Panel>
  return (
    <Panel>
      <ol className="chapters">
        {chapters.map((c, i) => (
          <li key={i}>
            <button onClick={() => seek(c.start)}><span className="time"><Play />{fmt(c.start)}</span><span>{c.title}</span></button>
          </li>
        ))}
      </ol>
    </Panel>
  )
}

function Chat({ history, question, setQuestion, ask, busy, seek }) {
  return (
    <div className="panel chat">
      <div className="turns">
        {!history.length && !busy && (
          <div className="empty"><b><MessageSquareText /></b><h2>Ask the video anything</h2><p>Definitions, explanations, "what did they say about X" — answers cite the exact timestamp.</p></div>
        )}
        {history.map((turn, i) => (
          <article key={i}>
            <div className="you"><small>YOU</small><p>{turn.question}</p></div>
            <div className="ai">
              <b><Sparkles /></b>
              <div>
                <Markdown text={turn.answer} onSeek={seek} />
                {turn.sources && turn.sources.length > 0 && (
                  <details>
                    <summary>{turn.sources.length} source passages</summary>
                    {turn.sources.map((s) => (
                      <blockquote key={s.chunk_id}>
                        <button className="ts" onClick={() => seek(s.start)}>{fmt(s.start)}</button>
                        {s.text}
                      </blockquote>
                    ))}
                  </details>
                )}
              </div>
            </div>
          </article>
        ))}
        {busy && <div className="ai"><b><Sparkles /></b><div className="typing"><Loader2 className="spin" />Thinking…</div></div>}
      </div>
      <form onSubmit={ask}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask anything about this video…" />
        <button disabled={busy || !question.trim()}><Send /></button>
      </form>
    </div>
  )
}

function Quiz({ quiz }) {
  const [picked, setPicked] = useState({})
  if (!quiz.length) return <Panel><p className="muted">No quiz could be generated.</p></Panel>
  const answered = Object.keys(picked).length
  const correct = quiz.reduce((n, q, i) => n + (picked[i] === q.answer ? 1 : 0), 0)
  return (
    <Panel>
      <div className="quizhead">
        <h2>{quiz.length} questions</h2>
        {answered > 0 && <span className="score">Score: {correct}/{answered}</span>}
      </div>
      <div className="quiz">
        {quiz.map((q, i) => {
          const chosen = picked[i]
          const done = chosen !== undefined
          return (
            <div className="quiz-q" key={i}>
              <h4>{i + 1}. {q.question}</h4>
              <div className="options">
                {q.options.map((opt, oi) => {
                  let cls = 'opt'
                  if (done) {
                    if (oi === q.answer) cls += ' right'
                    else if (oi === chosen) cls += ' wrong'
                  }
                  return (
                    <button key={oi} className={cls} disabled={done} onClick={() => setPicked((p) => ({ ...p, [i]: oi }))}>
                      <span>{String.fromCharCode(65 + oi)}</span>{opt}
                      {done && oi === q.answer && <Check className="mk" />}
                      {done && oi === chosen && oi !== q.answer && <X className="mk" />}
                    </button>
                  )
                })}
              </div>
              {done && q.explanation && <p className="explain">{q.explanation}</p>}
            </div>
          )
        })}
      </div>
    </Panel>
  )
}

function Transcript({ segments, busy, seek }) {
  const [q, setQ] = useState('')
  if (busy && !segments) return <Panel><div className="center"><Loader2 className="spin big" /><p>Loading transcript…</p></div></Panel>
  if (!segments) return <Panel><p className="muted">Transcript not loaded.</p></Panel>
  const filtered = q.trim()
    ? segments.filter((s) => s.text.toLowerCase().includes(q.toLowerCase()))
    : segments
  return (
    <div className="panel">
      <div className="tsearch"><Search /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the transcript…" /></div>
      <div className="transcript">
        {filtered.map((s, i) => (
          <div className="line" key={i}>
            <button className="ts" onClick={() => seek(s.start)}>{fmt(s.start)}</button>
            <p>{s.text}</p>
          </div>
        ))}
        {!filtered.length && <p className="muted">No matching lines.</p>}
      </div>
    </div>
  )
}
