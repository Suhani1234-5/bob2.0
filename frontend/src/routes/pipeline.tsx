import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import {
  Activity, ArrowRight, ArrowUpRight, BookOpenCheck, Check, CheckCircle2,
  ChevronDown, Circle, Clock3, Code2, FileCode2, LoaderCircle,
  MoreHorizontal, Search, Shield, Sparkles, Terminal, ListChecks,
} from 'lucide-react'

export const Route = createFileRoute('/pipeline')({ component: Pipeline })

const stages = [
  { title: 'Requirements', icon: BookOpenCheck, state: 'complete', agent: 'Context agent', detail: 'Acceptance criteria extracted from PR description and issue #31.' },
  { title: 'Investigation', icon: Search, state: 'complete', agent: 'Investigator', detail: '3 candidate claims linked to changed code.' },
  { title: 'Reproduction', icon: Terminal, state: 'running', agent: 'Reproducer', detail: 'Executing generated coupon expiry scenarios…' },
  { title: 'Fix review', icon: Shield, state: 'queued', agent: 'Adversarial verifier', detail: 'Waiting for reproduction evidence.' },
  { title: 'Regression', icon: ListChecks, state: 'queued', agent: 'Regression agent', detail: '47 existing tests queued.' },
]

const activity = [
  { time: '14:54:38', icon: Check, color: 'green', text: 'Requirements mapped', meta: 'Context agent · 4 acceptance criteria' },
  { time: '14:54:35', icon: Check, color: 'green', text: '3 candidate findings identified', meta: 'Investigator · 6 files inspected' },
  { time: '14:54:31', icon: LoaderCircle, color: 'violet', text: 'Running reproduction tests', meta: 'Reproducer · coupon expiry scenarios', live: true },
]

const tests = [
  { name: 'expired_coupon_rejected', type: 'Reproduction', state: 'running', duration: '—' },
  { name: 'active_coupon_accepted', type: 'Reproduction', state: 'passed', duration: '0.12s' },
  { name: 'timezone_boundary_expiry', type: 'Adversarial', state: 'queued', duration: '—' },
  { name: 'checkout_regression_suite', type: 'Regression', state: 'queued', duration: '—' },
]

const changedFilesDefault = [
  { filename: 'src/services/coupon.service.ts', status: 'modified', additions: 18, deletions: 3 },
  { filename: 'tests/coupon.spec.ts', status: 'modified', additions: 12, deletions: 0 },
  { filename: 'src/routes/checkout.ts', status: 'modified', additions: 4, deletions: 1 },
]

function StatusPill({ state }: { state: string }) {
  const labels: Record<string, string> = { complete: 'COMPLETE', running: 'RUNNING', queued: 'QUEUED', passed: 'PASS' }
  return <span className={`status-pill ${state}`}><span className="status-dot" />{labels[state] ?? state.toUpperCase()}</span>
}

export default function Pipeline() {
  const [selectedStage, setSelectedStage] = useState(2)
  const [showFiles, setShowFiles] = useState(false)
  const active = stages[selectedStage] ?? stages[0]!

  return (
    <div className="workspace">
      <section className="page-heading">
        <div>
          <div className="eyebrow"><Activity size={13} /> VERIFICATION / AGENTS</div>
          <h1>Pipeline overview</h1>
          <p>Live agent activity for this verification run.</p>
        </div>
        <div className="heading-actions">
          <span className="run-badge"><span className="live-dot" /> Verification running</span>
          <button className="more-action"><MoreHorizontal size={17} /></button>
        </div>
      </section>

      <section className="panel pipeline-panel">
        <div className="panel-header">
          <div>
            <div className="panel-title">
              <span className="section-glyph"><Activity size={15} /></span>
              Verification pipeline
              <span className="run-badge compact"><span className="live-dot" />RUNNING</span>
            </div>
            <p className="panel-subtitle">Agents work in sequence, with independent evidence at each stage.</p>
          </div>
          <button className="subtle-button" onClick={() => setSelectedStage(2)}>
            <Activity size={14} /> View activity
          </button>
        </div>

        <div className="pipeline-track">
          {stages.map((stage, index) => {
            const Icon = stage.icon
            return (
              <div className={`pipeline-step ${stage.state} ${selectedStage === index ? 'selected' : ''}`} key={stage.title}>
                <button className="step-button" onClick={() => setSelectedStage(index)} aria-label={`Inspect ${stage.title}`}>
                  <div className="step-icon">
                    <Icon size={17} />
                    {stage.state === 'complete' && <span className="step-check"><Check size={9} /></span>}
                    {stage.state === 'running' && <span className="step-orbit" />}
                  </div>
                  <div className="step-copy">
                    <span className="step-title">{stage.title}</span>
                    <span className="step-agent">{stage.agent}</span>
                  </div>
                  <StatusPill state={stage.state} />
                </button>
                {index < stages.length - 1 && (
                  <div className={`connector ${stage.state === 'complete' ? 'complete' : ''}`}><span /></div>
                )}
              </div>
            )
          })}
        </div>

        <div className="stage-detail">
          <div className={`stage-detail-icon ${active.state}`}><Sparkles size={15} /></div>
          <div>
            <b>{active.agent}</b>
            <p>{active.detail}</p>
          </div>
          <button>Agent details <ArrowUpRight size={13} /></button>
        </div>
      </section>

      <div className="lower-grid">
        <section className="panel activity-panel">
          <div className="panel-header compact-header">
            <div>
              <div className="panel-title"><span className="section-glyph"><Clock3 size={15} /></span>Live activity</div>
              <p className="panel-subtitle">Latest events from this verification run.</p>
            </div>
            <button className="icon-button small-icon" aria-label="Activity options"><MoreHorizontal size={17} /></button>
          </div>
          <div className="activity-list">
            {activity.map((item) => {
              const Icon = item.icon
              return (
                <div className="activity-item" key={item.time}>
                  <time>{item.time}</time>
                  <div className={`activity-icon ${item.color}`}><Icon size={13} className={item.live ? 'spin' : ''} /></div>
                  <div className="activity-copy">
                    <b>{item.text}{item.live && <span className="now-label">NOW</span>}</b>
                    <small>{item.meta}</small>
                  </div>
                </div>
              )
            })}
          </div>
          <button className="text-link">Open proof trail <ArrowRight size={13} /></button>
        </section>

        <section className="panel tests-panel">
          <div className="panel-header compact-header">
            <div>
              <div className="panel-title"><span className="section-glyph"><Terminal size={15} /></span>Test executions<span className="table-count">4 scenarios</span></div>
              <p className="panel-subtitle">Generated and regression checks.</p>
            </div>
            <button className="text-link">All tests <ArrowRight size={13} /></button>
          </div>
          <div className="test-table">
            <div className="test-head"><span>TEST</span><span>TYPE</span><span>RESULT</span></div>
            {tests.map(test => (
              <div className="test-row" key={test.name}>
                <span className="test-name"><Code2 size={13} />{test.name}</span>
                <span className="test-type">{test.type}</span>
                <span className={`test-result ${test.state}`}>
                  {test.state === 'passed' ? <CheckCircle2 size={13} /> : test.state === 'running' ? <LoaderCircle className="spin" size={13} /> : <Circle size={12} />}
                  {' '}{test.state === 'passed' ? test.duration : test.state === 'running' ? 'Running' : 'Queued'}
                </span>
              </div>
            ))}
          </div>
          <div className="test-summary">
            <span><span className="mini-dot green" />48 passed</span>
            <span><span className="mini-dot amber" />1 running</span>
            <span><span className="mini-dot muted-dot" />6 queued</span>
            <button onClick={() => setShowFiles(!showFiles)}>{showFiles ? 'Hide changed files' : 'Changed files'}<ChevronDown size={12} /></button>
          </div>
          {showFiles && (
            <div className="changed-files">
              {changedFilesDefault.map(file => (
                <div className="file-row" key={file.filename}>
                  <FileCode2 size={13} />
                  <code>{file.filename}</code>
                  <span className="file-add">+{file.additions}</span>
                  <span className="file-del">−{file.deletions}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}