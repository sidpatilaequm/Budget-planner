// Shared helpers: number formatting, budget maths and the API client.

export const MONTHS = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']
export const MONTH_FULL = ['April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March']
export const INST = [
  { label: 'Inst. I', from: 0, to: 4 },
  { label: 'Inst. II', from: 4, to: 8 },
  { label: 'Inst. III', from: 8, to: 12 },
]
export const SECTION_NAMES = { expense: 'Expenses', income: 'Income' }

export const sum = (a) => a.reduce((s, v) => s + (+v || 0), 0)
export const r2 = (n) => Math.round((+n || 0) * 100) / 100
export const instOf = (m, j) => sum(m.slice(INST[j].from, INST[j].to))
export const fyNice = (start) => `${start}–${String(start + 1).slice(2)}`

export function fmt(n) {
  return r2(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })
}
export function fmtIn(v) {
  return v === null || v === undefined || v === '' || +v === 0 ? '' : fmt(v)
}
export function money(n) {
  return (n < 0 ? '−' : '') + '₹\u202F' + fmt(Math.abs(Math.round(n)))
}
export function compact(n) {
  const a = Math.abs(n), s = n < 0 ? '−' : ''
  if (a >= 1e7) return `${s}₹\u202F${(a / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `${s}₹\u202F${(a / 1e5).toFixed(2)} L`
  return `${s}₹\u202F${Math.round(a).toLocaleString('en-IN')}`
}
export function pctText(p) {
  if (p === null || p === undefined) return '–'
  return `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p)}%`
}

// Accepts "1,20,000", "₹500", "=1200*12" or "1200*12".
export function parseNum(s) {
  if (s === null || s === undefined) return 0
  s = String(s).trim().replace(/[,₹\s]/g, '')
  if (!s) return 0
  if (s[0] === '=') s = s.slice(1)
  if (/^[-+]?\d*\.?\d+$/.test(s)) return +s
  if (/^[\d+\-*/().%]+$/.test(s)) {
    try {
      // eslint-disable-next-line no-new-func
      const v = Function('"use strict";return (' + s.replace(/%/g, '/100') + ')')()
      return Number.isFinite(v) ? r2(v) : 0
    } catch { return 0 }
  }
  return 0
}
export function parseOpt(s) {
  s = String(s ?? '').trim()
  return s === '' ? null : parseNum(s)
}
export function pctVal(s) {
  s = String(s ?? '').trim().replace('−', '-')
  if (s === '' || s === '-') return null
  const v = parseFloat(s)
  return Number.isFinite(v) ? v : null
}

// Splits a yearly amount into 12 whole-rupee months; the rounding remainder goes to the last paying month.
export function spread(total, pattern, once = 0, existing = null) {
  let w
  if (pattern === 'inst3') w = MONTHS.map((_, k) => (k === 0 || k === 4 || k === 8 ? 1 : 0))
  else if (pattern === 'quarterly') w = MONTHS.map((_, k) => (k % 3 === 0 ? 1 : 0))
  else if (pattern === 'once') w = MONTHS.map((_, k) => (k === +once ? 1 : 0))
  else if (pattern === 'keep') {
    const e = (existing || []).map((v) => +v || 0)
    w = sum(e) !== 0 ? e : Array(12).fill(1)
  } else w = Array(12).fill(1)
  const ws = sum(w), T = Math.round(total)
  const out = w.map((x) => Math.round((T * x) / ws))
  let last = 11
  while (last > 0 && !w[last]) last--
  out[last] += T - sum(out)
  return out
}


// Returns the current month index in an April-to-March financial year.
export function currentFyMonth(yearStart) {
  const calendarMonth = new Date().getMonth()
  return calendarMonth >= 3 ? calendarMonth - 3 : calendarMonth + 9
}

// Downloads an authenticated API response as a file.
export async function downloadFile(path, filename) {
  const res = await api(path, { raw: true })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 2000)
  }
}

// ---------- API client ----------
const TOKEN_KEY = 'budget-planner.token'
let token = sessionStorage.getItem(TOKEN_KEY)
let onUnauthorized = () => {}

export const getToken = () => token
export function setToken(t) {
  token = t
  if (t) sessionStorage.setItem(TOKEN_KEY, t)
  else sessionStorage.removeItem(TOKEN_KEY)
}
export function setUnauthorizedHandler(fn) { onUnauthorized = fn }

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

export async function api(path, { method = 'GET', body, form, raw } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  let res
  try {
    res = await fetch(path, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, 'The server could not be reached. Check your connection and try again.')
  }
  if (!res.ok) {
    let msg = 'Something went wrong. Try again.'
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') msg = j.detail
      else if (Array.isArray(j.detail) && j.detail[0]?.msg) msg = j.detail[0].msg
    } catch { /* not JSON */ }
    if (res.status === 401 && token) onUnauthorized(msg)
    throw new ApiError(res.status, msg)
  }
  return raw ? res : res.json()
}
